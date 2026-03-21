from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from security import InMemoryRateLimiter
from settings import Settings
from storage.reports import build_report_record, save_report


def build_saved_report(report_id: str, owner_session_id: str) -> dict:
    report = build_report_record(
        "text",
        f"Saved report {report_id}",
        report_id=report_id,
        owner_session_id=owner_session_id,
    )
    report["status"] = "done"
    return save_report(report)


class ApiSecurityTests(unittest.TestCase):
    def test_reports_are_scoped_to_the_request_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        build_saved_report("report-owner-a", "owner-a")
                        build_saved_report("report-owner-b", "owner-b")

                        with TestClient(main.app) as client:
                            client.cookies.set(main.settings.session_cookie_name, "owner-a")
                            response = client.get("/reports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([report["id"] for report in response.json()["reports"]], ["report-owner-a"])

    def test_share_token_allows_read_without_manage_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        report = build_saved_report("report-shared", "owner-a")

                        with TestClient(main.app) as client:
                            client.cookies.set(main.settings.session_cookie_name, "owner-b")
                            detail_response = client.get(
                                f"/reports/report-shared?share={report['share_token']}"
                            )
                            update_response = client.patch(
                                "/reports/report-shared",
                                json={"is_pinned": True},
                            )

        self.assertEqual(detail_response.status_code, 200)
        self.assertFalse(detail_response.json()["viewer_can_manage"])
        self.assertEqual(update_response.status_code, 404)

    def test_rate_limiter_returns_429_after_limit_is_exceeded(self) -> None:
        throttled_settings = Settings(
            allowed_origins=main.settings.allowed_origins,
            session_cookie_name=main.settings.session_cookie_name,
            session_cookie_secure=main.settings.session_cookie_secure,
            session_cookie_max_age=main.settings.session_cookie_max_age,
            public_share_enabled=main.settings.public_share_enabled,
            allow_legacy_public_reports=main.settings.allow_legacy_public_reports,
            rate_limit_window_seconds=60,
            rate_limit_read_requests=1,
            rate_limit_write_requests=1,
            rate_limit_analyze_requests=1,
        )

        with patch.object(main, "settings", throttled_settings):
            with patch.object(main, "rate_limiter", InMemoryRateLimiter()):
                with TestClient(main.app) as client:
                    first = client.get("/reports")
                    second = client.get("/reports")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["detail"], "Rate limit exceeded. Try again later.")
        self.assertIn("Retry-After", second.headers)


if __name__ == "__main__":
    unittest.main()
