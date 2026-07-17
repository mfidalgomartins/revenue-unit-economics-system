"""Validated, atomic publication of normalized source bundles."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import uuid
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from src.ingestion.adapters import ExtractionResult
from src.ingestion.contracts import CONTRACT_VERSION, NORMALIZED_CONTRACTS, ContractViolation


def _version_root(output_root: Path) -> Path:
    return output_root / f"v{CONTRACT_VERSION.split('.')[0]}"


@contextmanager
def _publication_lock(version_root: Path) -> Iterator[None]:
    """Serialize merge and activation without adding mutable lock files."""
    descriptor = os.open(version_root, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def resolve_current_bundle(output_root: Path) -> Path | None:
    """Return the active immutable bundle, including the pre-pointer legacy layout."""
    version_root = _version_root(output_root)
    pointer_path = version_root / "current.json"
    if not pointer_path.exists():
        legacy_manifest = version_root / "manifest.json"
        return version_root if legacy_manifest.exists() else None

    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractViolation(f"invalid active bundle pointer: {type(exc).__name__}") from exc
    if not isinstance(pointer, dict):
        raise ContractViolation("invalid active bundle pointer: expected an object")
    if pointer.get("contract_version") != CONTRACT_VERSION:
        raise ContractViolation("active bundle pointer has an incompatible contract version")

    relative = Path(str(pointer.get("bundle", "")))
    if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] != "bundles":
        raise ContractViolation("active bundle pointer contains an unsafe bundle path")
    target = version_root / relative
    if not (target / "manifest.json").is_file():
        raise ContractViolation("active bundle pointer references an incomplete bundle")
    return target


def verify_bundle(bundle: Path) -> dict[str, object]:
    """Verify manifest identity, table coverage, row counts, and file digests."""
    manifest_path = bundle / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractViolation(f"invalid bundle manifest: {type(exc).__name__}") from exc
    if not isinstance(manifest, dict):
        raise ContractViolation("invalid bundle manifest: expected an object")
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise ContractViolation("bundle manifest has an incompatible contract version")
    if manifest.get("bundle_id") != bundle.name:
        raise ContractViolation("bundle manifest identity does not match its directory")
    table_entries = manifest.get("tables")
    if not isinstance(table_entries, list) or not all(
        isinstance(entry, dict) for entry in table_entries
    ):
        raise ContractViolation("bundle manifest tables must be an object list")
    entries = {str(entry.get("table", "")): entry for entry in table_entries}
    if set(entries) != set(NORMALIZED_CONTRACTS) or len(entries) != len(table_entries):
        raise ContractViolation("bundle manifest table coverage does not match the contract")
    for table_name, entry in entries.items():
        path = bundle / f"{table_name}.csv"
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ContractViolation(f"bundle table is unavailable: {path.name}") from exc
        observed_digest = hashlib.sha256(content).hexdigest()
        if observed_digest != entry.get("sha256"):
            raise ContractViolation(f"bundle table digest mismatch: {path.name}")
        try:
            observed_rows = len(pd.read_csv(path))
        except (OSError, UnicodeError, pd.errors.ParserError) as exc:
            raise ContractViolation(f"bundle table is unreadable: {path.name}") from exc
        if observed_rows != entry.get("rows"):
            raise ContractViolation(f"bundle table row count mismatch: {path.name}")
    return manifest


def _validate_bundle(results: Iterable[ExtractionResult]) -> dict[str, ExtractionResult]:
    result_list = list(results)
    counts = Counter(result.table_name for result in result_list)
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    by_table = {result.table_name: result for result in result_list}
    expected = set(NORMALIZED_CONTRACTS)
    missing = sorted(expected - set(by_table))
    extra = sorted(set(by_table) - expected)
    if missing or extra or duplicates:
        raise ContractViolation(
            f"normalized bundle mismatch: missing={missing}, extra={extra}, duplicates={duplicates}"
        )
    return by_table


def _serialize_tables(
    by_table: dict[str, ExtractionResult],
    active_bundle: Path | None,
    *,
    merge_existing: bool,
) -> tuple[dict[str, str], list[dict[str, object]]]:
    validated: dict[str, pd.DataFrame] = {}
    for table_name in sorted(NORMALIZED_CONTRACTS):
        result = by_table[table_name]
        if result.contract_version != CONTRACT_VERSION:
            raise ContractViolation(
                f"{table_name} contract version {result.contract_version!r} "
                f"does not match {CONTRACT_VERSION!r}"
            )
        contract = NORMALIZED_CONTRACTS[table_name]
        frame = result.frame
        existing_path = active_bundle / f"{table_name}.csv" if active_bundle else None
        if merge_existing and existing_path and existing_path.exists():
            existing = contract.validate(pd.read_csv(existing_path), allow_empty=True)
            delta = contract.validate(frame, allow_empty=True)
            if delta.empty:
                combined = existing
            elif existing.empty:
                combined = delta
            else:
                combined = pd.concat([existing, delta], ignore_index=True)
            combined = combined.drop_duplicates(list(contract.primary_key), keep="last")
            frame = combined[list(contract.columns)]
        validated[table_name] = contract.validate(frame)

    customer_ids = set(validated["customers"]["customer_id"].astype(str))
    orphan_counts = {
        table_name: len(set(validated[table_name]["customer_id"].astype(str)) - customer_ids)
        for table_name in (
            "transactions",
            "marketing_touchpoints",
            "marketing_experiments",
        )
    }
    if any(orphan_counts.values()):
        raise ContractViolation(
            "normalized tables reference unknown customer IDs: "
            + ", ".join(f"{name}={count}" for name, count in orphan_counts.items())
        )

    contents: dict[str, str] = {}
    manifest_tables: list[dict[str, object]] = []
    for table_name in sorted(validated):
        output = validated[table_name].copy()
        for column in NORMALIZED_CONTRACTS[table_name].date_columns:
            output[column] = pd.to_datetime(output[column]).dt.strftime("%Y-%m-%d")
        content = output.to_csv(index=False, lineterminator="\n")
        contents[f"{table_name}.csv"] = content
        result = by_table[table_name]
        manifest_tables.append(
            {
                "table": table_name,
                "rows": len(output),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "source": result.source_name,
                "source_api_version": result.source_api_version,
                "extracted_at": result.extracted_at.isoformat(),
            }
        )
    return contents, manifest_tables


def _write_bundle(target: Path, contents: dict[str, str], manifest_content: str) -> None:
    target.mkdir()
    try:
        for filename, content in contents.items():
            (target / filename).write_text(content, encoding="utf-8")
        (target / "manifest.json").write_text(manifest_content, encoding="utf-8")
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def _activate_bundle(version_root: Path, target: Path) -> None:
    pointer = {
        "bundle": target.relative_to(version_root).as_posix(),
        "contract_version": CONTRACT_VERSION,
    }
    pointer_path = version_root / "current.json"
    pending_path = version_root / f".current-{uuid.uuid4().hex}.json"
    try:
        pending_path.write_text(
            json.dumps(pointer, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(pending_path, pointer_path)
    finally:
        pending_path.unlink(missing_ok=True)


def publish_normalized_bundle(
    results: Iterable[ExtractionResult],
    output_root: Path,
    *,
    merge_existing: bool = True,
) -> Path:
    """Validate a complete bundle and atomically activate an immutable snapshot."""
    by_table = _validate_bundle(results)
    version_root = _version_root(output_root)
    version_root.mkdir(parents=True, exist_ok=True)
    with _publication_lock(version_root):
        active_bundle = resolve_current_bundle(output_root)
        if active_bundle is not None and active_bundle.parent.name == "bundles":
            verify_bundle(active_bundle)
        contents, manifest_tables = _serialize_tables(
            by_table,
            active_bundle,
            merge_existing=merge_existing,
        )
        manifest_base = {
            "contract_version": CONTRACT_VERSION,
            "tables": manifest_tables,
        }
        identity_payload = json.dumps(
            manifest_base,
            sort_keys=True,
            separators=(",", ":"),
        )
        bundle_id = hashlib.sha256(identity_payload.encode("utf-8")).hexdigest()[:20]
        manifest = {"bundle_id": bundle_id, **manifest_base}
        manifest_content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

        bundles_root = version_root / "bundles"
        bundles_root.mkdir(exist_ok=True)
        target = bundles_root / bundle_id
        created = False
        if target.exists():
            expected_files = {**contents, "manifest.json": manifest_content}
            if any(
                not (target / filename).is_file()
                or (target / filename).read_text(encoding="utf-8") != content
                for filename, content in expected_files.items()
            ):
                raise RuntimeError(f"bundle identity collision or incomplete bundle: {bundle_id}")
        else:
            _write_bundle(target, contents, manifest_content)
            created = True

        try:
            _activate_bundle(version_root, target)
        except Exception:
            if created:
                shutil.rmtree(target, ignore_errors=True)
            raise
        return target
