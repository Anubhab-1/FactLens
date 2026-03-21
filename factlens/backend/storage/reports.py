from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


REPORTS_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "reports.db"
LEGACY_REPORTS_DIR = Path(__file__).resolve().parents[1] / "data" / "reports"
_WRITE_LOCK = threading.Lock()
_MIGRATED_DATABASES: set[str] = set()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_db_dir() -> None:
    REPORTS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    _ensure_db_dir()
    connection = sqlite3.connect(REPORTS_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            input_mode TEXT NOT NULL,
            input_value TEXT NOT NULL,
            owner_session_id TEXT NOT NULL DEFAULT '',
            share_token TEXT NOT NULL DEFAULT '',
            is_pinned INTEGER NOT NULL DEFAULT 0,
            is_archived INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reports_created_at
        ON reports(created_at DESC)
        """
    )
    _ensure_column(connection, "is_pinned", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "is_archived", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "owner_session_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "share_token", "TEXT NOT NULL DEFAULT ''")
    connection.commit()


def _ensure_column(connection: sqlite3.Connection, column_name: str, column_sql: str) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(reports)").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE reports ADD COLUMN {column_name} {column_sql}")


def _payload_from_row(row: sqlite3.Row) -> dict:
    payload = json.loads(row["payload_json"])
    payload["id"] = payload.get("id") or row["report_id"]
    payload["owner_session_id"] = payload.get("owner_session_id", row["owner_session_id"])
    payload["share_token"] = payload.get("share_token", row["share_token"])
    payload["is_pinned"] = bool(payload.get("is_pinned", row["is_pinned"]))
    payload["is_archived"] = bool(payload.get("is_archived", row["is_archived"]))
    return payload


def _report_is_accessible(
    report: dict,
    *,
    owner_session_id: Optional[str],
    share_token: Optional[str],
    allow_legacy_public_reports: bool,
) -> bool:
    report_owner = str(report.get("owner_session_id") or "").strip()
    report_share_token = str(report.get("share_token") or "").strip()

    if share_token and report_share_token and secrets.compare_digest(report_share_token, share_token):
        return True
    if owner_session_id and report_owner and secrets.compare_digest(report_owner, owner_session_id):
        return True
    if allow_legacy_public_reports and not report_owner:
        return True
    return False


def _legacy_report_paths() -> list[Path]:
    if not LEGACY_REPORTS_DIR.exists():
        return []
    return sorted(LEGACY_REPORTS_DIR.glob("*.json"))


def _import_legacy_json_reports(connection: sqlite3.Connection) -> None:
    db_key = str(REPORTS_DB_PATH.resolve())
    if db_key in _MIGRATED_DATABASES:
        return

    legacy_paths = _legacy_report_paths()
    if not legacy_paths:
        _MIGRATED_DATABASES.add(db_key)
        return

    for path in legacy_paths:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        report_id = payload.get("id") or path.stem
        payload["id"] = report_id
        payload["owner_session_id"] = str(payload.get("owner_session_id", "") or "")
        payload["share_token"] = str(payload.get("share_token", "") or secrets.token_urlsafe(8))
        payload["is_pinned"] = bool(payload.get("is_pinned", False))
        payload["is_archived"] = bool(payload.get("is_archived", False))
        connection.execute(
            """
            INSERT OR IGNORE INTO reports (
                report_id,
                status,
                created_at,
                updated_at,
                completed_at,
                input_mode,
                input_value,
                owner_session_id,
                share_token,
                is_pinned,
                is_archived,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                payload.get("status", "done"),
                payload.get("created_at") or _utc_now(),
                payload.get("updated_at") or payload.get("created_at") or _utc_now(),
                payload.get("completed_at"),
                payload.get("input_mode", "text"),
                payload.get("input_value", ""),
                payload.get("owner_session_id", ""),
                payload.get("share_token", ""),
                1 if payload.get("is_pinned") else 0,
                1 if payload.get("is_archived") else 0,
                json.dumps(payload, ensure_ascii=True),
            ),
        )

    connection.commit()
    _MIGRATED_DATABASES.add(db_key)


def generate_report_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"report-{timestamp}-{secrets.token_hex(3)}"


def generate_share_token() -> str:
    return secrets.token_urlsafe(9)


def build_report_record(
    input_mode: str,
    input_value: str,
    report_id: Optional[str] = None,
    owner_session_id: Optional[str] = None,
    share_token: Optional[str] = None,
) -> dict:
    now = _utc_now()

    return {
        "id": report_id or generate_report_id(),
        "schema_version": 1,
        "status": "running",
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "input_mode": input_mode,
        "input_value": input_value,
        "owner_session_id": str(owner_session_id or ""),
        "share_token": str(share_token or generate_share_token()),
        "pipeline_stage": "scraping" if input_mode == "url" else "detecting",
        "progress": {"done": 0, "total": 0},
        "is_pinned": False,
        "is_archived": False,
        "claims": [],
        "results": [],
        "ai_detection": None,
        "media_detection": None,
        "error": None,
    }


def save_report(report: dict) -> dict:
    report = dict(report)
    report["updated_at"] = _utc_now()
    report["owner_session_id"] = str(report.get("owner_session_id", "") or "")
    report["share_token"] = str(report.get("share_token", "") or generate_share_token())

    with _WRITE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            _import_legacy_json_reports(connection)
            connection.execute(
                """
                INSERT INTO reports (
                    report_id,
                    status,
                    created_at,
                    updated_at,
                    completed_at,
                    input_mode,
                    input_value,
                    owner_session_id,
                    share_token,
                    is_pinned,
                    is_archived,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    status = excluded.status,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    completed_at = excluded.completed_at,
                    input_mode = excluded.input_mode,
                    input_value = excluded.input_value,
                    owner_session_id = excluded.owner_session_id,
                    share_token = excluded.share_token,
                    is_pinned = excluded.is_pinned,
                    is_archived = excluded.is_archived,
                    payload_json = excluded.payload_json
                """,
                (
                    report["id"],
                    report.get("status", "done"),
                    report.get("created_at") or report["updated_at"],
                    report["updated_at"],
                    report.get("completed_at"),
                    report.get("input_mode", "text"),
                    report.get("input_value", ""),
                    report.get("owner_session_id", ""),
                    report.get("share_token", ""),
                    1 if report.get("is_pinned") else 0,
                    1 if report.get("is_archived") else 0,
                    json.dumps(report, ensure_ascii=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    return report


def get_report(
    report_id: str,
    *,
    owner_session_id: Optional[str] = None,
    share_token: Optional[str] = None,
    allow_legacy_public_reports: bool = True,
) -> Optional[dict]:
    with _WRITE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            _import_legacy_json_reports(connection)
            row = connection.execute(
                """
                SELECT report_id, owner_session_id, share_token, is_pinned, is_archived, payload_json
                FROM reports
                WHERE report_id = ?
                """,
                (report_id,),
            ).fetchone()
        finally:
            connection.close()

    if not row:
        return None

    report = _payload_from_row(row)
    if not _report_is_accessible(
        report,
        owner_session_id=owner_session_id,
        share_token=share_token,
        allow_legacy_public_reports=allow_legacy_public_reports,
    ):
        return None
    return report


def list_reports(
    *,
    owner_session_id: str,
    limit: int = 20,
    offset: int = 0,
    include_archived: bool = False,
    allow_legacy_public_reports: bool = True,
) -> dict:
    filters = "WHERE owner_session_id = ?"
    parameters: list[object] = [owner_session_id]

    if allow_legacy_public_reports:
        filters = "WHERE (owner_session_id = ? OR owner_session_id = '')"
    if not include_archived:
        filters = f"{filters} AND is_archived = 0"

    with _WRITE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            _import_legacy_json_reports(connection)
            total = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM reports
                {filters}
                """,
                parameters,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT report_id, owner_session_id, share_token, is_pinned, is_archived, payload_json
                FROM reports
                {filters}
                ORDER BY is_pinned DESC, created_at DESC, updated_at DESC
                LIMIT ?
                OFFSET ?
                """,
                (*parameters, limit, offset),
            ).fetchall()
        finally:
            connection.close()

    reports = [_payload_from_row(row) for row in rows]
    return {
        "reports": reports,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(reports) < total,
    }


def update_report_metadata(
    report_id: str,
    *,
    owner_session_id: str,
    is_pinned: Optional[bool] = None,
    is_archived: Optional[bool] = None,
    allow_legacy_public_reports: bool = True,
) -> Optional[dict]:
    report = get_report(
        report_id,
        owner_session_id=owner_session_id,
        allow_legacy_public_reports=allow_legacy_public_reports,
    )
    if report is None:
        return None

    if is_pinned is not None:
        report["is_pinned"] = bool(is_pinned)
    if is_archived is not None:
        report["is_archived"] = bool(is_archived)

    return save_report(report)


def delete_report(
    report_id: str,
    *,
    owner_session_id: str,
    allow_legacy_public_reports: bool = True,
) -> bool:
    report = get_report(
        report_id,
        owner_session_id=owner_session_id,
        allow_legacy_public_reports=allow_legacy_public_reports,
    )
    if report is None:
        return False

    with _WRITE_LOCK:
        connection = _connect()
        try:
            _ensure_schema(connection)
            _import_legacy_json_reports(connection)
            cursor = connection.execute(
                """
                DELETE FROM reports
                WHERE report_id = ?
                """,
                (report_id,),
            )
            connection.commit()
            return cursor.rowcount > 0
        finally:
            connection.close()
