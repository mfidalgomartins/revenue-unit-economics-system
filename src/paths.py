"""Canonical project root shared by every pipeline stage.

Stages keep their own directory constants (tests monkeypatch them per
module), but the root itself is resolved in exactly one place.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
