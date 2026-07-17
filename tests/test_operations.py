"""Operational graph, state, retry, alert, and lineage tests."""

from __future__ import annotations

import json
import signal
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import src.operations.orchestrator as orchestrator_module
import src.operations.publish_governance as publish_governance
import src.warehouse.run_dbt as warehouse
from src.data_contracts import RAW_SCHEMAS
from src.operations.alerts import JsonLogAlertSink, SignedWebhookAlertSink
from src.operations.orchestrator import PipelineOrchestrator
from src.operations.pipeline_spec import (
    PIPELINE_STAGES,
    PipelineProfile,
    StageSpec,
    build_pipeline_stages,
    validate_stage_graph,
)
from src.operations.publish_governance import build_pipeline_lineage, load_and_validate_slas
from src.operations.run_store import RunStore
from src.paths import PROJECT_ROOT
from src.warehouse.run_dbt import build_lineage_graph


class CaptureSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def send(self, event: object) -> None:
        self.events.append(dict(event))  # type: ignore[arg-type]


class FailingSink:
    def __init__(self) -> None:
        self.closed = False

    def send(self, event: object) -> None:
        del event
        raise RuntimeError("alert transport unavailable")

    def close(self) -> None:
        self.closed = True


def test_pipeline_stage_graph_is_valid_and_rejects_bad_specs() -> None:
    validate_stage_graph()
    assert PIPELINE_STAGES[-1].name == "validate_outputs"

    duplicate = (
        StageSpec("same", "module.one", (), 1),
        StageSpec("same", "module.two", (), 1),
    )
    with pytest.raises(ValueError, match="unique"):
        validate_stage_graph(duplicate)
    with pytest.raises(ValueError, match="unknown"):
        validate_stage_graph((StageSpec("one", "module", ("missing",), 1),))
    with pytest.raises(ValueError, match="have not completed"):
        validate_stage_graph(
            (
                StageSpec("one", "module", ("two",), 1),
                StageSpec("two", "module", (), 1),
            )
        )
    with pytest.raises(ValueError, match="invalid operational"):
        validate_stage_graph((StageSpec("one", "module", (), 0),))


def test_pipeline_profiles_share_one_graph_without_regenerating_external_data() -> None:
    synthetic = build_pipeline_stages(PipelineProfile.SYNTHETIC)
    external = build_pipeline_stages(PipelineProfile.EXTERNAL)

    assert synthetic == PIPELINE_STAGES
    assert synthetic[0].name == "generate_raw"
    assert external[0].name == "validate_raw"
    assert external[0].dependencies == ()
    assert [stage.name for stage in external] == [
        stage.name for stage in synthetic if stage.name != "generate_raw"
    ]
    with pytest.raises(ValueError, match="pipeline profile"):
        build_pipeline_stages("production-ish")


def test_synthetic_profile_rejects_an_external_raw_directory() -> None:
    with pytest.raises(RuntimeError, match="unset RAW_DATA_DIR"):
        orchestrator_module.resolve_pipeline_profile(
            {"PIPELINE_PROFILE": "synthetic", "RAW_DATA_DIR": "data/staging"}
        )


def test_dbt_staging_models_cover_the_complete_source_contract() -> None:
    staging_dir = PROJECT_ROOT / "warehouse" / "models" / "staging"
    missing = [
        table_name
        for table_name in RAW_SCHEMAS
        if not (staging_dir / f"stg_{table_name}.sql").is_file()
    ]

    assert missing == []


def test_run_store_persists_transactional_history(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite"
    store = RunStore(path)
    started = datetime(2026, 1, 1, tzinfo=UTC)
    store.start_run("run-1", started)
    store.start_stage("run-1", "stage", 1, started)
    store.finish_stage("run-1", "stage", 1, started + timedelta(seconds=2), 2.0, "succeeded")
    store.finish_run("run-1", started + timedelta(seconds=3), "succeeded")

    with sqlite3.connect(path) as connection:
        assert connection.execute("select status from pipeline_runs").fetchone() == ("succeeded",)
        assert connection.execute("select duration_seconds from stage_runs").fetchone() == (2.0,)


def test_orchestrator_retries_alerts_sla_and_succeeds(tmp_path: Path) -> None:
    attempts = 0

    observed_timeouts: list[float] = []

    def runner(_: str, timeout_seconds: float) -> None:
        nonlocal attempts
        observed_timeouts.append(timeout_seconds)
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")

    monotonic_values = iter([0.0, 1.0, 2.0, 5.0])
    sink = CaptureSink()
    stage = StageSpec("stage", "module", (), 2.0, max_attempts=2)
    orchestrator = PipelineOrchestrator(
        (stage,),
        RunStore(tmp_path / "runs.sqlite"),
        [sink],
        runner=runner,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        monotonic=lambda: next(monotonic_values),
        sleep=lambda _: None,
    )

    run_id = orchestrator.run()

    assert run_id
    event_names = [event["event"] for event in sink.events]
    assert event_names == [
        "pipeline_started",
        "stage_retry",
        "stage_sla_breach",
        "pipeline_succeeded",
    ]
    assert observed_timeouts == [4.0, 4.0]


def test_orchestrator_persists_and_alerts_terminal_failure(tmp_path: Path) -> None:
    sink = CaptureSink()
    orchestrator = PipelineOrchestrator(
        (StageSpec("stage", "module", (), 1),),
        RunStore(tmp_path / "runs.sqlite"),
        [sink],
        runner=lambda _module, _timeout: (_ for _ in ()).throw(ValueError("bad")),
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        monotonic=iter([0.0, 0.2]).__next__,
    )
    with pytest.raises(ValueError, match="bad"):
        orchestrator.run()
    assert [event["event"] for event in sink.events][-2:] == ["stage_failed", "pipeline_failed"]


def test_alert_delivery_is_best_effort_and_sinks_are_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failing_sink = FailingSink()
    capture_sink = CaptureSink()
    orchestrator = PipelineOrchestrator(
        (StageSpec("stage", "module", (), 1),),
        RunStore(tmp_path / "runs.sqlite"),
        [failing_sink, capture_sink],
        runner=lambda _module, _timeout: None,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        monotonic=iter([0.0, 0.2]).__next__,
    )

    orchestrator.run()

    assert [event["event"] for event in capture_sink.events] == [
        "pipeline_started",
        "pipeline_succeeded",
    ]
    assert failing_sink.closed
    assert "alert_delivery_failed" in capsys.readouterr().err


def test_alert_failure_does_not_mask_pipeline_failure(tmp_path: Path) -> None:
    state_path = tmp_path / "runs.sqlite"
    failing_sink = FailingSink()
    capture_sink = CaptureSink()
    orchestrator = PipelineOrchestrator(
        (StageSpec("stage", "module", (), 1),),
        RunStore(state_path),
        [failing_sink, capture_sink],
        runner=lambda _module, _timeout: (_ for _ in ()).throw(
            ValueError("source contract failed")
        ),
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        monotonic=iter([0.0, 0.2]).__next__,
    )

    with pytest.raises(ValueError, match="source contract failed"):
        orchestrator.run()

    with sqlite3.connect(state_path) as connection:
        assert connection.execute("select status from pipeline_runs").fetchone() == ("failed",)
    assert [event["event"] for event in capture_sink.events][-2:] == [
        "stage_failed",
        "pipeline_failed",
    ]
    assert failing_sink.closed


def test_orchestrator_entrypoint_uses_external_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured_stages: list[StageSpec] = []

    class CaptureOrchestrator:
        def __init__(
            self,
            stages: tuple[StageSpec, ...],
            store: RunStore,
            alert_sinks: object,
        ) -> None:
            del store, alert_sinks
            captured_stages.extend(stages)

        def run(self) -> str:
            return "run-1"

    monkeypatch.setenv("PIPELINE_PROFILE", "external")
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("PIPELINE_STATE_PATH", str(tmp_path / "runs.sqlite"))
    monkeypatch.setattr(orchestrator_module, "PipelineOrchestrator", CaptureOrchestrator)
    monkeypatch.setattr(orchestrator_module, "build_alert_sinks", lambda: [])

    orchestrator_module.run()

    assert captured_stages[0].name == "validate_raw"
    assert all(stage.name != "generate_raw" for stage in captured_stages)


def test_alert_sinks_emit_json_and_signed_webhook(capsys: pytest.CaptureFixture[str]) -> None:
    JsonLogAlertSink().send({"event": "test", "value": 1})
    assert capsys.readouterr().out == '{"event":"test","value":1}\n'

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"accepted": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sink = SignedWebhookAlertSink("https://alerts.test/events", "secret", client=client)
    sink.send({"event": "failed", "run_id": "1"})
    assert requests[0].headers["X-Revenue-Signature-256"].startswith("sha256=")
    assert json.loads(requests[0].content)["event"] == "failed"
    with pytest.raises(ValueError, match="HTTPS"):
        SignedWebhookAlertSink("http://alerts.test", "secret")


def test_operational_governance_and_dbt_lineage_are_deterministic() -> None:
    slas = load_and_validate_slas()
    lineage = build_pipeline_lineage()

    assert slas["schema_version"] == "1.0.0"
    assert lineage["profile"] == "synthetic"
    assert len(lineage["nodes"]) == len(PIPELINE_STAGES)
    assert {edge["to"] for edge in lineage["edges"]} >= {"validate_outputs"}

    manifest = {
        "sources": {
            "source.raw.customers": {
                "resource_type": "source",
                "name": "customers",
                "package_name": "revenue_analytics",
                "schema": "raw",
                "meta": {"owner": "data"},
                "depends_on": {"nodes": []},
            }
        },
        "nodes": {
            "model.revenue_analytics.dim_customers": {
                "resource_type": "model",
                "name": "dim_customers",
                "package_name": "revenue_analytics",
                "schema": "core",
                "meta": {"owner": "analytics", "sla_hours": 24},
                "depends_on": {"nodes": ["source.raw.customers"]},
            }
        },
        "exposures": {},
    }
    graph = build_lineage_graph(manifest)
    assert graph["edges"] == [
        {"from": "source.raw.customers", "to": "model.revenue_analytics.dim_customers"}
    ]


def test_operational_lineage_reflects_external_profile() -> None:
    lineage = build_pipeline_lineage(PipelineProfile.EXTERNAL)

    assert lineage["profile"] == "external"
    assert all(node["id"] != "generate_raw" for node in lineage["nodes"])


def test_module_runner_terminates_timed_out_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits = 0
    signals: list[tuple[int, signal.Signals]] = []

    class FakeProcess:
        pid = 4321

        def wait(self, timeout: float | None = None) -> int:
            nonlocal waits
            waits += 1
            if waits == 1:
                raise subprocess.TimeoutExpired(["python", "-m", "module"], timeout)
            return 0

    monkeypatch.setattr(
        orchestrator_module.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess()
    )
    monkeypatch.setattr(
        orchestrator_module.os,
        "killpg",
        lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )

    with pytest.raises(orchestrator_module.StageTimeoutError, match="module"):
        orchestrator_module._run_module("module", 1.0)

    assert signals == [(4321, signal.SIGTERM)]


def test_process_group_termination_escalates_after_grace_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits = 0
    signals: list[signal.Signals] = []

    class StubbornProcess:
        pid = 9876

        def wait(self, timeout: float | None = None) -> int:
            nonlocal waits
            waits += 1
            if timeout is not None:
                raise subprocess.TimeoutExpired("stage", timeout)
            return -signal.SIGKILL

    monkeypatch.setattr(
        orchestrator_module.os,
        "killpg",
        lambda _pid, sent_signal: signals.append(sent_signal),
    )

    orchestrator_module._terminate_process_group(StubbornProcess())  # type: ignore[arg-type]

    assert waits == 2
    assert signals == [signal.SIGTERM, signal.SIGKILL]


def test_module_runner_propagates_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailedProcess:
        pid = 1234

        def wait(self, timeout: float | None = None) -> int:
            assert timeout == 3.0
            return 7

    monkeypatch.setattr(
        orchestrator_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FailedProcess(),
    )

    with pytest.raises(subprocess.CalledProcessError) as error:
        orchestrator_module._run_module("module", 3.0)

    assert error.value.returncode == 7


def test_publish_governance_writes_valid_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(publish_governance, "OUTPUT_DIR", tmp_path)
    publish_governance.run()
    assert json.loads((tmp_path / "operational_slas.json").read_text())["schema_version"] == "1.0.0"
    assert json.loads((tmp_path / "pipeline_lineage.json").read_text())["nodes"]


def test_warehouse_runner_builds_command_and_publishes_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "dbt"
    executable.touch()
    calls: list[tuple[list[str], Path, dict[str, str], bool]] = []

    def capture(command: list[str], *, cwd: Path, env: dict[str, str], check: bool) -> None:
        calls.append((command, cwd, env, check))

    monkeypatch.setattr(warehouse, "_dbt_executable", lambda: executable)
    monkeypatch.setattr(warehouse.subprocess, "run", capture)
    warehouse.run_dbt_build(full_refresh=True)
    assert calls[0][0][-1] == "--full-refresh"
    assert calls[0][2]["RAW_DATA_DIR"].endswith("data/raw")
    assert calls[0][3]

    project = tmp_path / "project"
    target = project / "target"
    target.mkdir(parents=True)
    (target / "manifest.json").write_text(
        json.dumps({"sources": {}, "nodes": {}, "exposures": {}}), encoding="utf-8"
    )
    lineage_path = tmp_path / "lineage.json"
    monkeypatch.setattr(warehouse, "DBT_PROJECT_DIR", project)
    monkeypatch.setattr(warehouse, "LINEAGE_PATH", lineage_path)
    warehouse.publish_lineage()
    assert json.loads(lineage_path.read_text())["schema_version"] == "1.0.0"


def test_orchestrator_alert_configuration_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("ALERT_WEBHOOK_SIGNING_SECRET", raising=False)
    assert len(orchestrator_module.build_alert_sinks()) == 1
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://alerts.test")
    with pytest.raises(RuntimeError, match="configured together"):
        orchestrator_module.build_alert_sinks()
