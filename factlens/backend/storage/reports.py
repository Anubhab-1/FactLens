from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    delete,
    func,
    inspect,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import Select

from storage.report_diagnostics import build_report_diagnostics

REPORTS_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "reports.db"
LEGACY_REPORTS_DIR = Path(__file__).resolve().parents[1] / "data" / "reports"
_WRITE_LOCK = threading.Lock()
_MIGRATED_DATABASES: set[str] = set()
_SCHEMA_READY_DATABASES: set[str] = set()
_ENGINE_CACHE: dict[str, Engine] = {}
_TABLE_CACHE: dict[str, Table] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_database_url(database_url: str) -> str:
    normalized = str(database_url or "").strip()
    if normalized.startswith("postgres://"):
        return f"postgresql+psycopg2://{normalized[len('postgres://'):]}"
    if normalized.startswith("postgresql://"):
        return f"postgresql+psycopg2://{normalized[len('postgresql://'):]}"
    return normalized


def _default_sqlite_url() -> str:
    return f"sqlite:///{REPORTS_DB_PATH.resolve().as_posix()}"


def _database_url() -> str:
    configured = (
        os.getenv("FACTLENS_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    return _normalize_database_url(configured) or _default_sqlite_url()


def _current_database_key() -> str:
    return _database_url()


def _ensure_sqlite_db_dir(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    database_path = database_url[len("sqlite:///") :]
    if not database_path or database_path == ":memory:":
        return

    Path(database_path).parent.mkdir(parents=True, exist_ok=True)


def _engine() -> Engine:
    database_key = _current_database_key()
    engine = _ENGINE_CACHE.get(database_key)
    if engine is not None:
        return engine

    _ensure_sqlite_db_dir(database_key)
    connect_args = {"check_same_thread": False} if database_key.startswith("sqlite:///") else {}
    engine_kwargs = {
        "future": True,
        "connect_args": connect_args,
    }
    if database_key.startswith("sqlite:///"):
        engine_kwargs["poolclass"] = NullPool
    engine = create_engine(database_key, **engine_kwargs)
    _ENGINE_CACHE[database_key] = engine
    return engine


def _reports_table() -> Table:
    database_key = _current_database_key()
    table = _TABLE_CACHE.get(database_key)
    if table is not None:
        return table

    metadata = MetaData()
    table = Table(
        "reports",
        metadata,
        Column("report_id", String(128), primary_key=True),
        Column("status", String(32), nullable=False),
        Column("created_at", String(64), nullable=False),
        Column("updated_at", String(64), nullable=False),
        Column("completed_at", String(64), nullable=True),
        Column("input_mode", String(16), nullable=False),
        Column("input_value", Text, nullable=False),
        Column("owner_session_id", String(128), nullable=False, default=""),
        Column("share_token", String(128), nullable=False, default=""),
        Column("is_pinned", Boolean, nullable=False, default=False),
        Column("is_archived", Boolean, nullable=False, default=False),
        Column("payload_json", Text, nullable=False),
    )
    _TABLE_CACHE[database_key] = table
    return table


def _ensure_column(connection: Connection, column_name: str, column_sql: str) -> None:
    columns = {
        column["name"]
        for column in inspect(connection).get_columns("reports")
    }
    if column_name in columns:
        return
    connection.exec_driver_sql(f"ALTER TABLE reports ADD COLUMN {column_name} {column_sql}")


def _ensure_schema(connection: Connection, table: Table) -> None:
    database_key = _current_database_key()
    if database_key in _SCHEMA_READY_DATABASES:
        return

    table.metadata.create_all(connection)
    _ensure_column(connection, "owner_session_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "share_token", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "is_pinned", "BOOLEAN NOT NULL DEFAULT FALSE")
    _ensure_column(connection, "is_archived", "BOOLEAN NOT NULL DEFAULT FALSE")
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC)"
    )
    _SCHEMA_READY_DATABASES.add(database_key)


def _payload_from_row(row) -> dict:
    mapping = row._mapping
    payload = json.loads(mapping["payload_json"])
    payload["id"] = payload.get("id") or mapping["report_id"]
    payload["owner_session_id"] = payload.get("owner_session_id", mapping["owner_session_id"])
    payload["share_token"] = payload.get("share_token", mapping["share_token"])
    payload["is_pinned"] = bool(payload.get("is_pinned", mapping["is_pinned"]))
    payload["is_archived"] = bool(payload.get("is_archived", mapping["is_archived"]))
    payload["evaluation"] = build_report_diagnostics(
        payload,
        generated_at=str((payload.get("evaluation") or {}).get("generated_at") or payload.get("updated_at") or _utc_now()),
    )
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


def _build_row_values(report: dict) -> dict:
    return {
        "report_id": report["id"],
        "status": report.get("status", "done"),
        "created_at": report.get("created_at") or report["updated_at"],
        "updated_at": report["updated_at"],
        "completed_at": report.get("completed_at"),
        "input_mode": report.get("input_mode", "text"),
        "input_value": report.get("input_value", ""),
        "owner_session_id": report.get("owner_session_id", ""),
        "share_token": report.get("share_token", ""),
        "is_pinned": bool(report.get("is_pinned")),
        "is_archived": bool(report.get("is_archived")),
        "payload_json": json.dumps(report, ensure_ascii=True),
    }


def _upsert_row(connection: Connection, table: Table, values: dict) -> None:
    dialect_name = connection.engine.dialect.name
    if dialect_name == "sqlite":
        insert_stmt = sqlite_insert(table).values(**values)
        update_values = {key: values[key] for key in values if key != "report_id"}
        connection.execute(
            insert_stmt.on_conflict_do_update(
                index_elements=[table.c.report_id],
                set_=update_values,
            )
        )
        return

    if dialect_name == "postgresql":
        insert_stmt = postgresql_insert(table).values(**values)
        update_values = {key: values[key] for key in values if key != "report_id"}
        connection.execute(
            insert_stmt.on_conflict_do_update(
                index_elements=[table.c.report_id],
                set_=update_values,
            )
        )
        return

    updated = connection.execute(
        table.update()
        .where(table.c.report_id == values["report_id"])
        .values(**{key: values[key] for key in values if key != "report_id"})
    )
    if updated.rowcount:
        return
    try:
        connection.execute(table.insert().values(**values))
    except IntegrityError:
        connection.execute(
            table.update()
            .where(table.c.report_id == values["report_id"])
            .values(**{key: values[key] for key in values if key != "report_id"})
        )


def _import_legacy_json_reports(connection: Connection, table: Table) -> None:
    database_key = _current_database_key()
    if database_key in _MIGRATED_DATABASES:
        return

    legacy_paths = _legacy_report_paths()
    if not legacy_paths:
        _MIGRATED_DATABASES.add(database_key)
        return

    for path in legacy_paths:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        report_id = payload.get("id") or path.stem
        existing = connection.execute(
            select(table.c.report_id).where(table.c.report_id == report_id)
        ).first()
        if existing is not None:
            continue

        payload["id"] = report_id
        payload["owner_session_id"] = str(payload.get("owner_session_id", "") or "")
        payload["share_token"] = str(payload.get("share_token", "") or secrets.token_urlsafe(8))
        payload["is_pinned"] = bool(payload.get("is_pinned", False))
        payload["is_archived"] = bool(payload.get("is_archived", False))

        values = {
            "report_id": report_id,
            "status": payload.get("status", "done"),
            "created_at": payload.get("created_at") or _utc_now(),
            "updated_at": payload.get("updated_at") or payload.get("created_at") or _utc_now(),
            "completed_at": payload.get("completed_at"),
            "input_mode": payload.get("input_mode", "text"),
            "input_value": payload.get("input_value", ""),
            "owner_session_id": payload.get("owner_session_id", ""),
            "share_token": payload.get("share_token", ""),
            "is_pinned": bool(payload.get("is_pinned")),
            "is_archived": bool(payload.get("is_archived")),
            "payload_json": json.dumps(payload, ensure_ascii=True),
        }
        connection.execute(table.insert().values(**values))

    _MIGRATED_DATABASES.add(database_key)


def _prepare_storage(connection: Connection, table: Table) -> None:
    _ensure_schema(connection, table)
    _import_legacy_json_reports(connection, table)


def _report_select(table: Table) -> Select:
    return select(
        table.c.report_id,
        table.c.owner_session_id,
        table.c.share_token,
        table.c.is_pinned,
        table.c.is_archived,
        table.c.payload_json,
    )


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
        "source_text": "",
        "source_text_truncated": False,
        "source_capture": None,
        "claim_extraction": {
            "mode": "pending",
            "source_mode": None,
            "provider": None,
            "provider_label": None,
            "model": None,
            "warnings": [],
            "error": None,
            "claim_count": 0,
        },
        "ai_detection": None,
        "media_detection": None,
        "evaluation": None,
        "error": None,
    }


def save_report(report: dict) -> dict:
    report = dict(report)
    report["updated_at"] = _utc_now()
    report["owner_session_id"] = str(report.get("owner_session_id", "") or "")
    report["share_token"] = str(report.get("share_token", "") or generate_share_token())
    report["evaluation"] = build_report_diagnostics(report, generated_at=report["updated_at"])

    with _WRITE_LOCK:
        engine = _engine()
        table = _reports_table()
        with engine.begin() as connection:
            _prepare_storage(connection, table)
            _upsert_row(connection, table, _build_row_values(report))

    return report


def get_report(
    report_id: str,
    *,
    owner_session_id: Optional[str] = None,
    share_token: Optional[str] = None,
    allow_legacy_public_reports: bool = True,
) -> Optional[dict]:
    with _WRITE_LOCK:
        engine = _engine()
        table = _reports_table()
        with engine.begin() as connection:
            _prepare_storage(connection, table)
            row = connection.execute(
                _report_select(table).where(table.c.report_id == report_id)
            ).first()

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
    table = _reports_table()
    conditions = [
        or_(table.c.owner_session_id == owner_session_id, table.c.owner_session_id == "")
        if allow_legacy_public_reports
        else table.c.owner_session_id == owner_session_id
    ]
    if not include_archived:
        conditions.append(table.c.is_archived.is_(False))

    filters = and_(*conditions)

    with _WRITE_LOCK:
        engine = _engine()
        with engine.begin() as connection:
            _prepare_storage(connection, table)
            total = connection.execute(
                select(func.count()).select_from(table).where(filters)
            ).scalar_one()
            rows = connection.execute(
                _report_select(table)
                .where(filters)
                .order_by(
                    table.c.is_pinned.desc(),
                    table.c.created_at.desc(),
                    table.c.updated_at.desc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()

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
        engine = _engine()
        table = _reports_table()
        with engine.begin() as connection:
            _prepare_storage(connection, table)
            result = connection.execute(
                delete(table).where(table.c.report_id == report_id)
            )
            return result.rowcount > 0
