from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_origins() -> list[str]:
    raw_value = os.getenv("FACTLENS_ALLOWED_ORIGINS")
    if raw_value:
        origins = [item.strip() for item in raw_value.split(",") if item.strip()]
        if origins:
            return origins

    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]


@dataclass(frozen=True)
class Settings:
    allowed_origins: list[str]
    session_cookie_name: str
    session_cookie_secure: bool
    session_cookie_max_age: int
    public_share_enabled: bool
    allow_legacy_public_reports: bool
    rate_limit_window_seconds: int
    rate_limit_read_requests: int
    rate_limit_write_requests: int
    rate_limit_analyze_requests: int


def load_settings() -> Settings:
    return Settings(
        allowed_origins=_get_origins(),
        session_cookie_name=os.getenv("FACTLENS_SESSION_COOKIE_NAME", "factlens_session"),
        session_cookie_secure=_get_bool("FACTLENS_SESSION_COOKIE_SECURE", False),
        session_cookie_max_age=_get_int("FACTLENS_SESSION_COOKIE_MAX_AGE", 60 * 60 * 24 * 30),
        public_share_enabled=_get_bool("FACTLENS_PUBLIC_SHARE_ENABLED", True),
        allow_legacy_public_reports=_get_bool("FACTLENS_LEGACY_PUBLIC_REPORTS", True),
        rate_limit_window_seconds=_get_int("FACTLENS_RATE_LIMIT_WINDOW_SECONDS", 60),
        rate_limit_read_requests=_get_int("FACTLENS_RATE_LIMIT_READ_REQUESTS", 240),
        rate_limit_write_requests=_get_int("FACTLENS_RATE_LIMIT_WRITE_REQUESTS", 90),
        rate_limit_analyze_requests=_get_int("FACTLENS_RATE_LIMIT_ANALYZE_REQUESTS", 12),
    )
