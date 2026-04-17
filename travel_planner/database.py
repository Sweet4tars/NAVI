from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from .schemas import JobRecord, SourceStatus, TripPlanResult, TripRequest


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class JobRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    source_status_json TEXT NOT NULL DEFAULT '{}',
                    checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS source_status (
                    source TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    checked_at TEXT NOT NULL
                );
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "checkpoint_json" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN checkpoint_json TEXT NOT NULL DEFAULT '{}'")

    def create_job(self, request: TripRequest) -> JobRecord:
        job_id = str(uuid.uuid4())
        timestamp = now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (job_id, status, request_json, created_at, updated_at, progress)
                VALUES (?, 'collecting', ?, ?, ?, 0)
                """,
                (job_id, request.model_dump_json(), timestamp, timestamp),
            )
        return self.get_job(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        result: TripPlanResult | None = None,
        warnings: list[str] | None = None,
        source_statuses: dict[str, SourceStatus] | None = None,
        checkpoint: dict | None = None,
        error: str | None = None,
    ) -> None:
        updates: list[str] = ["updated_at = ?"]
        params: list[object] = [now_iso()]
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if result is not None:
            updates.append("result_json = ?")
            params.append(result.model_dump_json())
        if warnings is not None:
            updates.append("warnings_json = ?")
            params.append(json.dumps(warnings, ensure_ascii=False))
        if source_statuses is not None:
            updates.append("source_status_json = ?")
            params.append(json.dumps({k: v.model_dump(mode="json") for k, v in source_statuses.items()}, ensure_ascii=False))
        if checkpoint is not None:
            updates.append("checkpoint_json = ?")
            params.append(json.dumps(checkpoint, ensure_ascii=False))
        if error is not None:
            updates.append("error = ?")
            params.append(error)
        params.append(job_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?", params)

    def get_job(self, job_id: str) -> JobRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._row_to_job(row)

    def _row_to_job(self, row: sqlite3.Row) -> JobRecord:
        source_payload = json.loads(row["source_status_json"] or "{}")
        result_payload = row["result_json"]
        checkpoint_payload = json.loads(row["checkpoint_json"] or "{}")
        return JobRecord(
            job_id=row["job_id"],
            status=row["status"],
            request=TripRequest.model_validate_json(row["request_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            progress=row["progress"],
            result=TripPlanResult.model_validate_json(result_payload) if result_payload else None,
            warnings=json.loads(row["warnings_json"] or "[]"),
            source_statuses={key: SourceStatus.model_validate(value) for key, value in source_payload.items()},
            error=row["error"],
            checkpoint=checkpoint_payload,
        )

    def upsert_source_status(self, status: SourceStatus) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_status (source, state, detail, checked_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    state = excluded.state,
                    detail = excluded.detail,
                    checked_at = excluded.checked_at
                """,
                (
                    status.source,
                    status.state,
                    status.detail,
                    status.checked_at.isoformat(timespec="seconds"),
                ),
            )

    def list_source_statuses(self) -> list[SourceStatus]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM source_status ORDER BY source ASC").fetchall()
        return [
            SourceStatus(
                source=row["source"],
                state=row["state"],
                detail=row["detail"],
                checked_at=datetime.fromisoformat(row["checked_at"]),
            )
            for row in rows
        ]
