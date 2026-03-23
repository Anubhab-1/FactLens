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
    def test_draft_claims_returns_editable_payload(self) -> None:
        async def fake_detect_ai(_text: str) -> dict:
            return {
                "label": "LIKELY_HUMAN",
                "ai_probability": 0.12,
                "signals_found": ["specific phrasing"],
                "explanation": "Looks concise.",
            }

        async def fake_extract_claims(_text: str) -> dict:
            return {
                "claims": [
                    {
                        "id": "1",
                        "claim": "Mars has two moons named Phobos and Deimos.",
                        "context": "Mars has two moons named Phobos and Deimos.",
                        "time_sensitive": False,
                        "claim_type": "entity",
                    }
                ],
                "meta": {
                    "mode": "llm",
                    "source_mode": None,
                    "provider": "nvidia",
                    "provider_label": "NVIDIA",
                    "model": "meta/llama-3.1-70b-instruct",
                    "warnings": [],
                    "error": None,
                    "claim_count": 1,
                },
            }

        with TestClient(main.app) as client:
            with patch("main.detect_ai", new=fake_detect_ai):
                with patch("main.extract_claims_with_metadata", new=fake_extract_claims):
                    response = client.post(
                        "/draft-claims",
                        json={"text": "Mars has two moons named Phobos and Deimos."},
                    )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["input_mode"], "text")
        self.assertEqual(payload["source_text"], "Mars has two moons named Phobos and Deimos.")
        self.assertEqual(len(payload["claims"]), 1)
        self.assertEqual(payload["claims"][0]["claim"], "Mars has two moons named Phobos and Deimos.")
        self.assertEqual(payload["ai_detection"]["label"], "LIKELY_HUMAN")
        self.assertEqual(payload["claim_extraction"]["mode"], "llm")

    def test_draft_claims_returns_422_when_url_scrape_fails(self) -> None:
        async def fake_scrape_url(_url: str) -> dict:
            raise ValueError("Could not extract text from URL.")

        with TestClient(main.app) as client:
            with patch("main.scrape_url", new=fake_scrape_url):
                response = client.post(
                    "/draft-claims",
                    json={"url": "https://example.com/article"},
                )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Could not extract text from URL.")

    def test_analyze_requires_review_when_extraction_is_heuristic(self) -> None:
        async def fake_detect_ai(_text: str) -> dict:
            return {
                "label": "LIKELY_HUMAN",
                "ai_probability": 0.11,
                "signals_found": [],
                "explanation": "Looks human.",
            }

        async def fake_extract_claims(_text: str) -> dict:
            return {
                "claims": [
                    {
                        "id": "1",
                        "claim": "Mars has two moons named Phobos and Deimos.",
                        "context": "Mars has two moons named Phobos and Deimos.",
                        "time_sensitive": False,
                        "claim_type": "entity",
                    }
                ],
                "meta": {
                    "mode": "heuristic",
                    "source_mode": None,
                    "provider": None,
                    "provider_label": None,
                    "model": None,
                    "warnings": [
                        "No LLM provider is configured, so FactLens used a heuristic claim draft. Review these claims carefully before verification."
                    ],
                    "error": None,
                    "claim_count": 1,
                },
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        with patch("main.detect_ai", new=fake_detect_ai):
                            with patch("main.extract_claims_with_metadata", new=fake_extract_claims):
                                with TestClient(main.app) as client:
                                    response = client.post(
                                        "/analyze",
                                        json={"text": "Mars has two moons named Phobos and Deimos."},
                                    )
                                    reports_response = client.get("/reports")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "review_required"', response.text)
        self.assertNotIn('"type": "done"', response.text)
        reports_payload = reports_response.json()
        self.assertEqual(reports_payload["reports"], [])

    def test_analyze_reviewed_stream_uses_reviewed_claims_and_saves_report(self) -> None:
        async def fake_retrieve_evidence(claim: dict) -> dict:
            return {
                "claim_id": claim["id"],
                "query_used": claim["claim"],
                "query_variants": [{"query": claim["claim"], "objective": "direct", "phase": "primary"}],
                "retrieval_summary": {
                    "source_count": 1,
                    "authoritative_count": 1,
                    "recent_count": 1,
                    "dated_count": 1,
                    "distinct_domain_count": 1,
                    "freshest_date": "2026-03-22",
                    "domains": ["science.example"],
                    "query_attempt_count": 1,
                    "failed_query_count": 0,
                    "recovery_triggered": False,
                    "recovery_query_count": 0,
                    "recovery_reason": [],
                },
                "sources": [
                    {
                        "id": "S1",
                        "title": "Mars Facts",
                        "url": "https://science.example/mars",
                        "domain": "science.example",
                        "source_type": "web",
                        "published_date": "2026-03-22",
                        "published_label": "2026-03-22",
                        "snippet": "Mars has two moons named Phobos and Deimos.",
                        "evidence_passages": [
                            {
                                "text": "Mars has two moons named Phobos and Deimos.",
                                "score": 0.91,
                                "kind": "sentence",
                            }
                        ],
                        "authority_score": 0.91,
                        "relevance_score": 0.92,
                        "recency_score": 0.98,
                        "overall_score": 0.93,
                        "query_objective": "direct",
                        "query_phase": "primary",
                    }
                ],
                "error": None,
            }

        async def fake_verify_claim(claim: dict, evidence: dict) -> dict:
            return {
                "claim_id": claim["id"],
                "claim": claim["claim"],
                "claim_type": claim["claim_type"],
                "time_sensitive": claim["time_sensitive"],
                "verdict": "TRUE",
                "confidence": 0.88,
                "reasoning": "The reviewed claim is supported by the saved source.",
                "supporting_sources": ["https://science.example/mars"],
                "conflicting_sources": [],
                "conflict_detected": False,
                "supporting_evidence": evidence["sources"],
                "conflicting_evidence": [],
                "mixed_evidence": [],
                "neutral_evidence": [],
                "conflict_summary": {
                    "summary": "",
                    "drivers": [],
                    "supporting_count": 1,
                    "conflicting_count": 0,
                    "mixed_count": 0,
                    "supporting_newest": "2026-03-22",
                    "conflicting_newest": "unknown",
                    "supporting_avg_authority": 0.91,
                    "conflicting_avg_authority": 0.0,
                },
                "confidence_breakdown": {
                    "support_score": 0.93,
                    "conflict_score": 0.0,
                    "source_quality": 0.91,
                    "freshness": 0.98,
                    "evidence_coverage": 0.5,
                    "clarity": 0.9,
                },
                "risk_flags": [],
                "query_variants": evidence["query_variants"],
                "retrieval_summary": evidence["retrieval_summary"],
                "evidence_used": evidence["sources"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        with patch("main.retrieve_evidence", new=fake_retrieve_evidence):
                            with patch("main.verify_claim", new=fake_verify_claim):
                                with TestClient(main.app) as client:
                                    client.cookies.set(main.settings.session_cookie_name, "owner-a")
                                    response = client.post(
                                        "/analyze-reviewed",
                                        json={
                                            "input_mode": "text",
                                            "input_value": "Original reviewed input",
                                            "source_text": "Mars has two moons named Phobos and Deimos.",
                                            "claims": [
                                                {
                                                    "id": "c1",
                                                    "claim": "Mars has two moons named Phobos and Deimos.",
                                                    "context": "Mars has two moons named Phobos and Deimos.",
                                                }
                                            ],
                                            "ai_detection": {
                                                "label": "LIKELY_HUMAN",
                                                "ai_probability": 0.11,
                                                "signals_found": [],
                                                "explanation": "Looks human.",
                                            },
                                        },
                                    )
                                    reports_response = client.get("/reports")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "extracting_done"', response.text)
        self.assertIn('"type": "done"', response.text)

        reports_payload = reports_response.json()
        self.assertEqual(len(reports_payload["reports"]), 1)
        report = reports_payload["reports"][0]
        self.assertEqual(report["input_value"], "Original reviewed input")
        self.assertEqual(report["claims"][0]["id"], "c1")
        self.assertEqual(report["results"][0]["verdict"], "TRUE")
        self.assertEqual(report["source_text"], "Mars has two moons named Phobos and Deimos.")

    def test_source_text_payload_updates_report_state(self) -> None:
        report = build_report_record("text", "Example input", report_id="report-source-text")

        updated = main._apply_payload_to_report(
            report,
            {
                "type": "source_text_ready",
                "data": {
                    "source_text": "First sentence. Second sentence.",
                    "source_text_truncated": True,
                },
            },
        )

        self.assertEqual(updated["source_text"], "First sentence. Second sentence.")
        self.assertTrue(updated["source_text_truncated"])

    def test_extracting_done_payload_updates_claim_extraction_state(self) -> None:
        report = build_report_record("text", "Example input", report_id="report-extract-state")

        updated = main._apply_payload_to_report(
            report,
            {
                "type": "extracting_done",
                "data": {
                    "claims": [{"id": "1", "claim": "Example claim"}],
                    "count": 1,
                    "claim_extraction": {
                        "mode": "heuristic",
                        "source_mode": None,
                        "provider": None,
                        "provider_label": None,
                        "model": None,
                        "warnings": ["Heuristic draft."],
                        "error": None,
                        "claim_count": 1,
                    },
                },
            },
        )

        self.assertEqual(updated["claim_extraction"]["mode"], "heuristic")
        self.assertEqual(updated["claim_extraction"]["warnings"], ["Heuristic draft."])

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

    def test_claim_recalculation_requires_owner_and_persists_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        report = build_report_record(
                            "text",
                            "Example input",
                            report_id="report-override",
                            owner_session_id="owner-a",
                        )
                        report["status"] = "done"
                        report["pipeline_stage"] = "done"
                        report["claims"] = [
                            {
                                "id": "1",
                                "claim": "Example claim",
                                "context": "Example claim",
                                "time_sensitive": False,
                                "claim_type": "entity",
                            }
                        ]
                        report["results"] = [
                            {
                                "claim_id": "1",
                                "claim": "Example claim",
                                "claim_type": "entity",
                                "time_sensitive": False,
                                "claim_requires_recency": False,
                                "verdict": "TRUE",
                                "confidence": 0.81,
                                "reasoning": "Original model verdict.",
                                "supporting_sources": ["https://example.gov/support"],
                                "conflicting_sources": ["https://example.org/conflict"],
                                "conflict_detected": True,
                                "supporting_evidence": [
                                    {
                                        "id": "S1",
                                        "url": "https://example.gov/support",
                                        "title": "Government statement",
                                        "domain": "example.gov",
                                        "published_date": "2026-03-20",
                                        "published_label": "2026-03-20",
                                        "snippet": "The claim is correct.",
                                        "snippet_used": "The claim is correct.",
                                        "assessment_summary": "Supports the claim.",
                                        "stance": "SUPPORT",
                                        "strength": 0.94,
                                        "overall_score": 0.92,
                                        "authority_score": 0.97,
                                        "recency_score": 0.9,
                                    }
                                ],
                                "conflicting_evidence": [
                                    {
                                        "id": "S2",
                                        "url": "https://example.org/conflict",
                                        "title": "Independent audit",
                                        "domain": "example.org",
                                        "published_date": "2026-03-18",
                                        "published_label": "2026-03-18",
                                        "snippet": "The claim is incorrect.",
                                        "snippet_used": "The claim is incorrect.",
                                        "assessment_summary": "Conflicts with the claim.",
                                        "stance": "CONFLICT",
                                        "strength": 0.9,
                                        "overall_score": 0.86,
                                        "authority_score": 0.88,
                                        "recency_score": 0.82,
                                    }
                                ],
                                "mixed_evidence": [],
                                "neutral_evidence": [],
                                "conflict_summary": {
                                    "summary": "",
                                    "drivers": [],
                                    "supporting_count": 1,
                                    "conflicting_count": 1,
                                    "mixed_count": 0,
                                    "supporting_newest": "2026-03-20",
                                    "conflicting_newest": "2026-03-18",
                                    "supporting_avg_authority": 0.97,
                                    "conflicting_avg_authority": 0.88,
                                },
                                "confidence_breakdown": {
                                    "support_score": 1.0,
                                    "conflict_score": 0.72,
                                    "source_quality": 0.89,
                                    "freshness": 0.9,
                                    "evidence_coverage": 0.5,
                                    "clarity": 0.28,
                                },
                                "risk_flags": [],
                                "query_variants": [],
                                "retrieval_summary": {
                                    "source_count": 2,
                                    "authoritative_count": 2,
                                    "recent_count": 2,
                                    "dated_count": 2,
                                    "distinct_domain_count": 2,
                                    "freshest_date": "2026-03-20",
                                    "domains": ["example.gov", "example.org"],
                                },
                                "evidence_used": [
                                    {
                                        "id": "S1",
                                        "url": "https://example.gov/support",
                                        "title": "Government statement",
                                        "domain": "example.gov",
                                        "published_date": "2026-03-20",
                                        "published_label": "2026-03-20",
                                        "snippet": "The claim is correct.",
                                        "snippet_used": "The claim is correct.",
                                        "assessment_summary": "Supports the claim.",
                                        "stance": "SUPPORT",
                                        "strength": 0.94,
                                        "overall_score": 0.92,
                                        "authority_score": 0.97,
                                        "recency_score": 0.9,
                                    },
                                    {
                                        "id": "S2",
                                        "url": "https://example.org/conflict",
                                        "title": "Independent audit",
                                        "domain": "example.org",
                                        "published_date": "2026-03-18",
                                        "published_label": "2026-03-18",
                                        "snippet": "The claim is incorrect.",
                                        "snippet_used": "The claim is incorrect.",
                                        "assessment_summary": "Conflicts with the claim.",
                                        "stance": "CONFLICT",
                                        "strength": 0.9,
                                        "overall_score": 0.86,
                                        "authority_score": 0.88,
                                        "recency_score": 0.82,
                                    },
                                ],
                                "base_source_assessments": [
                                    {
                                        "source_id": "S1",
                                        "url": "https://example.gov/support",
                                        "stance": "SUPPORT",
                                        "strength": 0.94,
                                        "summary": "Supports the claim.",
                                        "snippet_used": "The claim is correct.",
                                    },
                                    {
                                        "source_id": "S2",
                                        "url": "https://example.org/conflict",
                                        "stance": "CONFLICT",
                                        "strength": 0.9,
                                        "summary": "Conflicts with the claim.",
                                        "snippet_used": "The claim is incorrect.",
                                    },
                                ],
                                "manual_override": None,
                            }
                        ]
                        save_report(report)

                        with TestClient(main.app) as client:
                            client.cookies.set(main.settings.session_cookie_name, "owner-b")
                            denied = client.post(
                                "/reports/report-override/claims/1/recalculate",
                                json={
                                    "overrides": [
                                        {
                                            "source_id": "S1",
                                            "stance": "CONFLICT",
                                        }
                                    ]
                                },
                            )

                        with TestClient(main.app) as client:
                            client.cookies.set(main.settings.session_cookie_name, "owner-a")
                            allowed = client.post(
                                "/reports/report-override/claims/1/recalculate",
                                json={
                                    "overrides": [
                                        {
                                            "source_id": "S1",
                                            "stance": "CONFLICT",
                                        }
                                    ]
                                },
                            )

        self.assertEqual(denied.status_code, 404)
        self.assertEqual(allowed.status_code, 200)
        payload = allowed.json()
        self.assertEqual(payload["results"][0]["verdict"], "FALSE")
        self.assertTrue(payload["results"][0]["manual_override"]["active"])
        self.assertEqual(payload["results"][0]["manual_override"]["override_count"], 1)

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
