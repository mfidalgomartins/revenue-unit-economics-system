"""SQLite persistence for pipeline and stage execution state."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


class RunStore:
    """Transactional execution history with one connection per operation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    pipeline_name TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed'))
                );
                CREATE TABLE IF NOT EXISTS stage_runs (
                    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
                    stage_name TEXT NOT NULL,
                    attempt INTEGER NOT NULL CHECK (attempt > 0),
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_seconds REAL,
                    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
                    error_type TEXT,
                    PRIMARY KEY (run_id, stage_name, attempt)
                );
                CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at
                    ON pipeline_runs(started_at);
                CREATE INDEX IF NOT EXISTS idx_stage_runs_status
                    ON stage_runs(status, stage_name);
                """
            )

    def start_run(self, run_id: str, started_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pipeline_runs VALUES (?, ?, ?, NULL, 'running')",
                (run_id, "revenue_analytics", started_at.isoformat()),
            )

    def finish_run(self, run_id: str, finished_at: datetime, status: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE pipeline_runs SET finished_at = ?, status = ? WHERE run_id = ?",
                (finished_at.isoformat(), status, run_id),
            )

    def start_stage(
        self,
        run_id: str,
        stage_name: str,
        attempt: int,
        started_at: datetime,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO stage_runs
                    (run_id, stage_name, attempt, started_at, status)
                VALUES (?, ?, ?, ?, 'running')
                """,
                (run_id, stage_name, attempt, started_at.isoformat()),
            )

    def finish_stage(
        self,
        run_id: str,
        stage_name: str,
        attempt: int,
        finished_at: datetime,
        duration_seconds: float,
        status: str,
        error_type: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE stage_runs
                SET finished_at = ?, duration_seconds = ?, status = ?, error_type = ?
                WHERE run_id = ? AND stage_name = ? AND attempt = ?
                """,
                (
                    finished_at.isoformat(),
                    duration_seconds,
                    status,
                    error_type,
                    run_id,
                    stage_name,
                    attempt,
                ),
            )
