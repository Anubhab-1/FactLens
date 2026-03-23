from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage.reports import (
    build_report_record,
    delete_report,
    get_report,
    list_reports,
    save_report,
    update_report_metadata,
)


class ReportStorageTests(unittest.TestCase):
    def test_database_url_override_uses_configured_sqlite_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "override.db"
            legacy_dir = temp_root / "legacy"
            database_url = f"sqlite:///{db_path.as_posix()}"

            with patch.dict(os.environ, {"FACTLENS_DATABASE_URL": database_url}, clear=False):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._ENGINE_CACHE", {}):
                        with patch("storage.reports._TABLE_CACHE", {}):
                            with patch("storage.reports._SCHEMA_READY_DATABASES", set()):
                                with patch("storage.reports._MIGRATED_DATABASES", set()):
                                    report = build_report_record(
                                        "text",
                                        "Configured database URL",
                                        report_id="report-db-url",
                                        owner_session_id="owner-a",
                                    )
                                    save_report(report)
                                    persisted = get_report("report-db-url", owner_session_id="owner-a")

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["id"], "report-db-url")

    def test_save_and_get_report_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        report = build_report_record(
                            "text",
                            "Paris is the capital of France.",
                            report_id="report-test",
                            owner_session_id="owner-a",
                        )
                        report["status"] = "done"
                        report["claims"] = [{"id": "1", "claim": "Paris is the capital of France."}]
                        save_report(report)

                        persisted = get_report("report-test", owner_session_id="owner-a")

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["id"], "report-test")
        self.assertEqual(persisted["status"], "done")
        self.assertEqual(len(persisted["claims"]), 1)

    def test_save_report_persists_evaluation_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        report = build_report_record(
                            "text",
                            "The current CEO of ExampleCorp is Jane Doe.",
                            report_id="report-eval",
                            owner_session_id="owner-a",
                        )
                        report["status"] = "done"
                        report["claim_extraction"] = {
                            "mode": "manual_review",
                            "source_mode": "heuristic",
                            "provider_label": "NVIDIA",
                            "warnings": ["Claims were manually reviewed before verification."],
                            "claim_count": 1,
                        }
                        report["claims"] = [
                            {
                                "id": "1",
                                "claim": "The current CEO of ExampleCorp is Jane Doe.",
                                "time_sensitive": True,
                            }
                        ]
                        report["results"] = [
                            {
                                "claim_id": "1",
                                "claim": "The current CEO of ExampleCorp is Jane Doe.",
                                "time_sensitive": True,
                                "verdict": "UNVERIFIABLE",
                                "confidence": 0.48,
                                "conflict_detected": True,
                                "risk_flags": ["Reflection Auditor corrected the initial verdict: current evidence is stale."],
                                "subclaim_results": [{"subclaim_id": "1-sub1", "claim": "CEO is Jane Doe."}],
                                "manual_override": {"active": True},
                                "retrieval_summary": {
                                    "source_count": 2,
                                    "independent_source_count": 2,
                                    "primary_source_count": 1,
                                    "query_attempt_count": 4,
                                    "failed_query_count": 1,
                                    "recovery_triggered": True,
                                    "recovery_strategy": "heuristic_after_llm",
                                },
                                "conflict_summary": {
                                    "contradiction_types": [
                                        {"id": "date_drift", "label": "Date drift"},
                                        {"id": "entity_mismatch", "label": "Entity mismatch"},
                                    ]
                                },
                            }
                        ]
                        save_report(report)
                        persisted = get_report("report-eval", owner_session_id="owner-a")

        self.assertIsNotNone(persisted["evaluation"])
        self.assertEqual(persisted["evaluation"]["summary"]["verified_claims"], 1)
        self.assertEqual(persisted["evaluation"]["extraction"]["mode"], "manual_review")
        self.assertEqual(persisted["evaluation"]["retrieval"]["recovery_triggered_claim_count"], 1)
        self.assertEqual(persisted["evaluation"]["verification"]["manual_override_claim_count"], 1)
        self.assertEqual(
            persisted["evaluation"]["verification"]["top_contradiction_type"]["id"],
            "date_drift",
        )

    def test_list_reports_returns_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        older = build_report_record("text", "Older input", report_id="report-older", owner_session_id="owner-a")
                        newer = build_report_record("url", "https://example.com", report_id="report-newer", owner_session_id="owner-a")
                        older["created_at"] = "2026-03-20T10:00:00+00:00"
                        newer["created_at"] = "2026-03-21T10:00:00+00:00"
                        save_report(older)
                        save_report(newer)

                        reports = list_reports(owner_session_id="owner-a", limit=10)["reports"]

        self.assertEqual([report["id"] for report in reports], ["report-newer", "report-older"])

    def test_legacy_json_reports_are_imported_into_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            legacy_payload = build_report_record("text", "Legacy report", report_id="report-legacy")
            legacy_payload["status"] = "done"

            with (legacy_dir / "report-legacy.json").open("w", encoding="utf-8") as handle:
                json.dump(legacy_payload, handle, ensure_ascii=True, indent=2)

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        imported = get_report("report-legacy", owner_session_id="owner-any")
                        reports = list_reports(owner_session_id="owner-any", limit=5)["reports"]

        self.assertIsNotNone(imported)
        self.assertEqual(imported["id"], "report-legacy")
        self.assertEqual([report["id"] for report in reports], ["report-legacy"])

    def test_update_report_metadata_pins_and_archives_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        report = build_report_record("text", "Lifecycle report", report_id="report-life", owner_session_id="owner-a")
                        save_report(report)

                        updated = update_report_metadata(
                            "report-life",
                            owner_session_id="owner-a",
                            is_pinned=True,
                            is_archived=True,
                        )
                        active_reports = list_reports(owner_session_id="owner-a", limit=10, include_archived=False)["reports"]
                        archived_reports = list_reports(owner_session_id="owner-a", limit=10, include_archived=True)["reports"]

        self.assertTrue(updated["is_pinned"])
        self.assertTrue(updated["is_archived"])
        self.assertEqual(active_reports, [])
        self.assertEqual([report["id"] for report in archived_reports], ["report-life"])

    def test_pinned_reports_sort_ahead_of_unpinned(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        first = build_report_record("text", "First", report_id="report-first", owner_session_id="owner-a")
                        second = build_report_record("text", "Second", report_id="report-second", owner_session_id="owner-a")
                        first["created_at"] = "2026-03-20T10:00:00+00:00"
                        second["created_at"] = "2026-03-21T10:00:00+00:00"
                        save_report(first)
                        save_report(second)
                        update_report_metadata("report-first", owner_session_id="owner-a", is_pinned=True)

                        reports = list_reports(owner_session_id="owner-a", limit=10)["reports"]

        self.assertEqual([report["id"] for report in reports], ["report-first", "report-second"])

    def test_delete_report_removes_it_from_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        report = build_report_record("text", "Delete me", report_id="report-delete", owner_session_id="owner-a")
                        save_report(report)

                        deleted = delete_report("report-delete", owner_session_id="owner-a")
                        persisted = get_report("report-delete", owner_session_id="owner-a")

        self.assertTrue(deleted)
        self.assertIsNone(persisted)

    def test_report_requires_owner_or_share_token_for_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        report = build_report_record(
                            "text",
                            "Restricted report",
                            report_id="report-private",
                            owner_session_id="owner-a",
                        )
                        save_report(report)

                        denied = get_report("report-private", owner_session_id="owner-b")
                        allowed_by_owner = get_report("report-private", owner_session_id="owner-a")
                        allowed_by_share = get_report(
                            "report-private",
                            owner_session_id="owner-b",
                            share_token=report["share_token"],
                        )

        self.assertIsNone(denied)
        self.assertEqual(allowed_by_owner["id"], "report-private")
        self.assertEqual(allowed_by_share["id"], "report-private")


if __name__ == "__main__":
    unittest.main()
