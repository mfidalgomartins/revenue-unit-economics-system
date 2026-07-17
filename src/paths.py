"""Canonical project and data paths shared by pipeline stages."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from src.data_contracts import RAW_CONTRACT_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_active_bundle(path: Path) -> Path:
    pointer_candidates = (path / "current.json", path / "v1" / "current.json")
    pointer_path = next(
        (candidate for candidate in pointer_candidates if candidate.is_file()), None
    )
    if pointer_path is None:
        return path.resolve()
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid raw-data bundle pointer at {pointer_path}") from exc
    if not isinstance(pointer, dict):
        raise RuntimeError(f"invalid raw-data bundle pointer at {pointer_path}")
    if pointer.get("contract_version") != RAW_CONTRACT_VERSION:
        raise RuntimeError(f"incompatible raw-data contract at {pointer_path}")
    relative = Path(str(pointer.get("bundle", "")))
    if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] != "bundles":
        raise RuntimeError(f"unsafe raw-data bundle pointer at {pointer_path}")
    target = (pointer_path.parent / relative).resolve()
    if (
        not target.is_relative_to(pointer_path.parent.resolve())
        or not (target / "manifest.json").is_file()
    ):
        raise RuntimeError(f"incomplete raw-data bundle referenced by {pointer_path}")
    return target


def resolve_raw_data_dir(environment: Mapping[str, str] | None = None) -> Path:
    """Resolve the governed raw-data directory relative to the project root."""
    values = os.environ if environment is None else environment
    configured = values.get("RAW_DATA_DIR", "").strip()
    path = Path(configured).expanduser() if configured else PROJECT_ROOT / "data" / "raw"
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return _resolve_active_bundle(path)


RAW_DATA_DIR = resolve_raw_data_dir()
