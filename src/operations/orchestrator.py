"""Dependency-aware sequential orchestrator with retries, SLAs, and alerts."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from src.operations.alerts import AlertSink, JsonLogAlertSink, SignedWebhookAlertSink
from src.operations.pipeline_spec import (
    StageSpec,
    build_pipeline_stages,
    resolve_pipeline_profile,
    validate_stage_graph,
)
from src.operations.run_store import RunStore
from src.paths import PROJECT_ROOT


def _utc_now() -> datetime:
    return datetime.now(UTC)


PROCESS_TERMINATION_GRACE_SECONDS = 5.0


class StageTimeoutError(TimeoutError):
    """Raised after a timed-out stage and its process group are terminated."""


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=PROCESS_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait()


def _run_module(module: str, timeout_seconds: float) -> None:
    environment = os.environ.copy()
    if "visualization" in module:
        environment["MPLBACKEND"] = "Agg"
        environment["MPLCONFIGDIR"] = str(PROJECT_ROOT / ".cache" / "matplotlib")
    command = [sys.executable, "-m", module]
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        start_new_session=True,
    )
    try:
        return_code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        raise StageTimeoutError(
            f"stage module {module!r} exceeded {timeout_seconds:g} seconds"
        ) from exc
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


class PipelineOrchestrator:
    """Execute a validated stage graph and persist each attempt."""

    def __init__(
        self,
        stages: tuple[StageSpec, ...],
        store: RunStore,
        alert_sinks: Sequence[AlertSink],
        *,
        runner: Callable[[str, float], None] = _run_module,
        now: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        validate_stage_graph(stages)
        self.stages = stages
        self.store = store
        self.alert_sinks = alert_sinks
        self.runner = runner
        self.now = now
        self.monotonic = monotonic
        self.sleep = sleep

    def _emit(self, event: dict[str, object]) -> None:
        for sink in self.alert_sinks:
            try:
                sink.send(event)
            except Exception as exc:
                self._report_alert_error("alert_delivery_failed", sink, exc, event)

    @staticmethod
    def _report_alert_error(
        diagnostic_event: str,
        sink: AlertSink,
        error: Exception,
        source_event: dict[str, object] | None = None,
    ) -> None:
        diagnostic = {
            "event": diagnostic_event,
            "sink_type": type(sink).__name__,
            "error_type": type(error).__name__,
        }
        if source_event is not None:
            diagnostic["source_event"] = str(source_event.get("event", "unknown"))
        print(json.dumps(diagnostic, sort_keys=True, separators=(",", ":")), file=sys.stderr)

    def _close_alert_sinks(self) -> None:
        for sink in self.alert_sinks:
            close = getattr(sink, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except Exception as exc:
                self._report_alert_error("alert_sink_close_failed", sink, exc)

    def run(self) -> str:
        run_id = str(uuid.uuid4())
        run_started = self.now()
        self.store.start_run(run_id, run_started)
        try:
            self._emit({"event": "pipeline_started", "run_id": run_id})
            try:
                for stage in self.stages:
                    self._run_stage(run_id, stage)
            except Exception as exc:
                self.store.finish_run(run_id, self.now(), "failed")
                self._emit(
                    {
                        "event": "pipeline_failed",
                        "run_id": run_id,
                        "error_type": type(exc).__name__,
                    }
                )
                raise
            self.store.finish_run(run_id, self.now(), "succeeded")
            self._emit({"event": "pipeline_succeeded", "run_id": run_id})
            return run_id
        finally:
            self._close_alert_sinks()

    def _run_stage(self, run_id: str, stage: StageSpec) -> None:
        for attempt in range(1, stage.max_attempts + 1):
            started_at = self.now()
            started_clock = self.monotonic()
            self.store.start_stage(run_id, stage.name, attempt, started_at)
            try:
                self.runner(stage.module, stage.effective_timeout_seconds)
            except Exception as exc:
                duration = self.monotonic() - started_clock
                self.store.finish_stage(
                    run_id,
                    stage.name,
                    attempt,
                    self.now(),
                    duration,
                    "failed",
                    type(exc).__name__,
                )
                if attempt == stage.max_attempts:
                    self._emit(
                        {
                            "event": "stage_failed",
                            "run_id": run_id,
                            "stage": stage.name,
                            "attempt": attempt,
                            "error_type": type(exc).__name__,
                        }
                    )
                    raise
                self._emit(
                    {
                        "event": "stage_retry",
                        "run_id": run_id,
                        "stage": stage.name,
                        "attempt": attempt,
                    }
                )
                self.sleep(min(2.0 ** (attempt - 1), 8.0))
                continue

            duration = self.monotonic() - started_clock
            self.store.finish_stage(
                run_id,
                stage.name,
                attempt,
                self.now(),
                duration,
                "succeeded",
            )
            if duration > stage.sla_seconds:
                self._emit(
                    {
                        "event": "stage_sla_breach",
                        "run_id": run_id,
                        "stage": stage.name,
                        "duration_seconds": round(duration, 3),
                        "sla_seconds": stage.sla_seconds,
                    }
                )
            return


def build_alert_sinks() -> list[AlertSink]:
    sinks: list[AlertSink] = [JsonLogAlertSink()]
    webhook_url = os.getenv("ALERT_WEBHOOK_URL")
    signing_secret = os.getenv("ALERT_WEBHOOK_SIGNING_SECRET")
    if bool(webhook_url) != bool(signing_secret):
        raise RuntimeError(
            "ALERT_WEBHOOK_URL and ALERT_WEBHOOK_SIGNING_SECRET must be configured together"
        )
    if webhook_url and signing_secret:
        sinks.append(SignedWebhookAlertSink(webhook_url, signing_secret))
    return sinks


def run() -> None:
    profile = resolve_pipeline_profile()
    state_path = Path(
        os.getenv(
            "PIPELINE_STATE_PATH",
            str(PROJECT_ROOT / "outputs" / "operations" / "pipeline_runs.sqlite"),
        )
    )
    orchestrator = PipelineOrchestrator(
        build_pipeline_stages(profile),
        RunStore(state_path),
        build_alert_sinks(),
    )
    run_id = orchestrator.run()
    print(f"Orchestrated pipeline completed: run_id={run_id}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
