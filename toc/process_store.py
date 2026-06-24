from __future__ import annotations

import json
import os
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover - optional until DB use is enabled.
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS toc_process_runs (
    job_id text PRIMARY KEY,
    run_id text NOT NULL UNIQUE,
    title text NOT NULL,
    source text NOT NULL DEFAULT '',
    run_path text NOT NULL,
    create_mode text NOT NULL DEFAULT 'normal',
    status text NOT NULL DEFAULT 'running',
    current_process_number integer NOT NULL DEFAULT 0,
    stop_target_number integer NOT NULL DEFAULT 680,
    pid integer,
    message text,
    error text,
    error_code text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
ALTER TABLE toc_process_runs ADD COLUMN IF NOT EXISTS current_process_number integer NOT NULL DEFAULT 0;
ALTER TABLE toc_process_runs ADD COLUMN IF NOT EXISTS stop_target_number integer NOT NULL DEFAULT 680;
ALTER TABLE toc_process_runs DROP COLUMN IF EXISTS current_process;
ALTER TABLE toc_process_runs DROP COLUMN IF EXISTS stop_target;
CREATE INDEX IF NOT EXISTS idx_toc_process_runs_run_id ON toc_process_runs (run_id);
CREATE INDEX IF NOT EXISTS idx_toc_process_runs_status ON toc_process_runs (status);
CREATE INDEX IF NOT EXISTS idx_toc_process_runs_current_process_number ON toc_process_runs (current_process_number);
CREATE INDEX IF NOT EXISTS idx_toc_process_runs_updated_at ON toc_process_runs (updated_at DESC);
"""


TERMINAL_STATUSES = {"completed", "failed", "paused"}


@dataclass(frozen=True)
class ProcessRecord:
    job_id: str
    run_id: str
    title: str
    source: str
    run_path: str
    create_mode: str
    status: str
    current_process_number: int
    stop_target_number: int
    pid: int | None
    message: str | None
    error: str | None
    error_code: str | None
    metadata: dict[str, Any]
    created_at: str | None
    updated_at: str | None
    completed_at: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ProcessRecord:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return cls(
            job_id=str(row.get("job_id") or ""),
            run_id=str(row.get("run_id") or ""),
            title=str(row.get("title") or ""),
            source=str(row.get("source") or ""),
            run_path=str(row.get("run_path") or ""),
            create_mode=str(row.get("create_mode") or "normal"),
            status=str(row.get("status") or "running"),
            current_process_number=_process_number(row.get("current_process_number")),
            stop_target_number=_process_number(row.get("stop_target_number"), default=680),
            pid=row.get("pid"),
            message=row.get("message"),
            error=row.get("error"),
            error_code=row.get("error_code"),
            metadata=metadata,
            created_at=_iso(row.get("created_at")),
            updated_at=_iso(row.get("updated_at")),
            completed_at=_iso(row.get("completed_at")),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "jobId": self.job_id,
            "runId": self.run_id,
            "title": self.title,
            "source": self.source,
            "path": self.run_path,
            "createMode": self.create_mode,
            "status": self.status,
            "currentProcess": _process_label(self.current_process_number),
            "currentProcessNumber": self.current_process_number,
            "stopTarget": _process_label(self.stop_target_number),
            "stopTargetNumber": self.stop_target_number,
            "pid": self.pid,
            "message": self.message,
            "error": self.error,
            "errorCode": self.error_code,
            "metadata": self.metadata,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "completedAt": self.completed_at,
        }


def enabled() -> bool:
    return bool(os.environ.get("DATABASE_URL", "").strip()) and psycopg is not None


def unavailable_reason() -> str | None:
    if not os.environ.get("DATABASE_URL", "").strip():
        return "DATABASE_URL is not set"
    if psycopg is None:
        return "psycopg is not installed"
    return None


def create_process_run(
    *,
    job_id: str,
    run_id: str,
    title: str,
    source: str,
    run_path: str,
    create_mode: str,
    stop_target_number: int,
    current_process_number: int = 0,
    status: str = "running",
    pid: int | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProcessRecord | None:
    if not enabled():
        return None
    ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO toc_process_runs (
                job_id, run_id, title, source, run_path, create_mode, status,
                current_process_number, stop_target_number, pid, message, metadata
            )
            VALUES (
                %(job_id)s, %(run_id)s, %(title)s, %(source)s, %(run_path)s,
                %(create_mode)s, %(status)s, %(current_process_number)s, %(stop_target_number)s,
                %(pid)s, %(message)s, %(metadata)s::jsonb
            )
            ON CONFLICT (run_id) DO UPDATE SET
                job_id = EXCLUDED.job_id,
                title = EXCLUDED.title,
                source = EXCLUDED.source,
                run_path = EXCLUDED.run_path,
                create_mode = EXCLUDED.create_mode,
                status = EXCLUDED.status,
                current_process_number = EXCLUDED.current_process_number,
                stop_target_number = EXCLUDED.stop_target_number,
                pid = EXCLUDED.pid,
                message = EXCLUDED.message,
                error = NULL,
                error_code = NULL,
                metadata = EXCLUDED.metadata,
                updated_at = now(),
                completed_at = NULL
            RETURNING *
            """,
            {
                "job_id": job_id,
                "run_id": run_id,
                "title": title,
                "source": source,
                "run_path": run_path,
                "create_mode": create_mode,
                "status": status,
                "current_process_number": int(current_process_number),
                "stop_target_number": int(stop_target_number),
                "pid": pid,
                "message": message,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False),
            },
        ).fetchone()
        conn.commit()
    return ProcessRecord.from_row(dict(row)) if row else None


def update_process_run(
    *,
    job_id: str | None = None,
    run_id: str | None = None,
    patch: dict[str, Any],
) -> ProcessRecord | None:
    if not enabled():
        return None
    if not job_id and not run_id:
        raise ValueError("job_id or run_id is required")
    ensure_schema()
    fields: dict[str, str] = {
        "status": "status",
        "message": "message",
        "error": "error",
        "errorCode": "error_code",
        "currentProcessNumber": "current_process_number",
        "stopTargetNumber": "stop_target_number",
        "pid": "pid",
        "metadata": "metadata",
    }
    assignments: list[str] = []
    params: dict[str, Any] = {"job_id": job_id, "run_id": run_id}
    for api_key, column in fields.items():
        if api_key not in patch:
            continue
        if api_key == "metadata":
            assignments.append(f"{column} = %({column})s::jsonb")
            params[column] = json.dumps(patch[api_key] or {}, ensure_ascii=False)
        else:
            assignments.append(f"{column} = %({column})s")
            params[column] = patch[api_key]
    if not assignments:
        return get_process_run(job_id=job_id, run_id=run_id)
    completed_value = "now()" if str(patch.get("status") or "").lower() in TERMINAL_STATUSES else "completed_at"
    where = "job_id = %(job_id)s" if job_id else "run_id = %(run_id)s"
    sql = f"""
        UPDATE toc_process_runs
        SET {", ".join(assignments)}, updated_at = now(), completed_at = {completed_value}
        WHERE {where}
        RETURNING *
    """
    with _connect() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return ProcessRecord.from_row(dict(row)) if row else None


def get_process_run(*, job_id: str | None = None, run_id: str | None = None) -> ProcessRecord | None:
    if not enabled():
        return None
    if not job_id and not run_id:
        raise ValueError("job_id or run_id is required")
    ensure_schema()
    where = "job_id = %(job_id)s" if job_id else "run_id = %(run_id)s"
    with _connect() as conn:
        row = conn.execute(f"SELECT * FROM toc_process_runs WHERE {where}", {"job_id": job_id, "run_id": run_id}).fetchone()
    return ProcessRecord.from_row(dict(row)) if row else None


def ensure_schema() -> None:
    if not enabled():
        reason = unavailable_reason()
        raise RuntimeError(f"process DB is unavailable: {reason}")
    with _connect() as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(SCHEMA_SQL)
        conn.commit()


def _connect() -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed")
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=2)


def _process_number(value: Any, *, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    if text.startswith("p"):
        text = text[1:]
    try:
        return int(text)
    except ValueError:
        return default


def _process_label(value: int) -> str:
    return f"p{max(0, int(value)):03d}"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        current = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return current.isoformat()
    return str(value)
