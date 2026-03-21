from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app, settings
from storage.report_exports import build_report_pdf
from storage.reports import build_report_record, save_report


def build_completed_report(report_id: str) -> dict:
    report = build_report_record(
        "text",
        "Mars has two moons named Phobos and Deimos. Delta: D",
        report_id=report_id,
        owner_session_id="owner-a",
    )
    report["status"] = "done"
    report["completed_at"] = "2026-03-21T15:00:00+00:00"
    report["claims"] = [
        {
            "id": "1",
            "claim": "Mars has two moons named Phobos and Deimos.",
            "context": "Mars has two moons named Phobos and Deimos.",
        }
    ]
    report["ai_detection"] = {
        "label": "LIKELY_HUMAN",
        "ai_probability": 0.18,
        "signals_found": ["specific scientific entities"],
        "explanation": "The wording looks concise and factual.",
    }
    report["media_detection"] = {
        "label": "UNKNOWN",
        "ai_probability": None,
        "signals_found": [],
        "explanation": "No media found to analyze.",
        "media_url": None,
    }
    report["results"] = [
        {
            "claim_id": "1",
            "claim": "Mars has two moons named Phobos and Deimos.",
            "claim_type": "entity",
            "time_sensitive": False,
            "verdict": "TRUE",
            "confidence": 0.91,
            "reasoning": "Multiple astronomy sources agree on the names of the two moons.",
            "supporting_evidence": [
                {
                    "title": "Mars Facts",
                    "url": "https://science.example/mars-facts",
                    "domain": "science.example",
                    "published_label": "Mar 20, 2026",
                    "authority_score": 0.98,
                    "relevance_score": 0.94,
                    "overall_score": 0.96,
                }
            ],
            "conflicting_evidence": [],
            "mixed_evidence": [],
            "neutral_evidence": [],
            "supporting_sources": ["https://science.example/mars-facts"],
            "conflicting_sources": [],
            "conflict_detected": False,
            "confidence_breakdown": {
                "support_score": 0.96,
                "conflict_score": 0.0,
                "source_quality": 0.98,
                "freshness": 0.9,
            },
            "risk_flags": ["Scientific naming should still be checked against primary sources."],
            "query_variants": [
                {
                    "objective": "direct",
                    "query": "Mars moons Phobos Deimos",
                }
            ],
            "retrieval_summary": {
                "distinct_domain_count": 1,
                "freshest_date": "2026-03-20",
            },
            "evidence_used": [
                {
                    "title": "Mars Facts",
                    "url": "https://science.example/mars-facts",
                    "domain": "science.example",
                    "published_label": "Mar 20, 2026",
                }
            ],
        }
    ]
    return report


class ReportExportTests(unittest.TestCase):
    def test_build_report_pdf_returns_pdf_bytes(self) -> None:
        pdf_bytes = build_report_pdf(build_completed_report("report-pdf-bytes"))

        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
        self.assertIn(b"FactLens Verification Report", pdf_bytes)
        self.assertIn(b"report-pdf-bytes", pdf_bytes)
        self.assertIn(b"Mars has two moons named Phobos and Deimos.", pdf_bytes)

    def test_export_report_pdf_response_has_pdf_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "reports.db"
            legacy_dir = temp_root / "legacy"

            with patch("storage.reports.REPORTS_DB_PATH", db_path):
                with patch("storage.reports.LEGACY_REPORTS_DIR", legacy_dir):
                    with patch("storage.reports._MIGRATED_DATABASES", set()):
                        save_report(build_completed_report("report-pdf-response"))
                        with TestClient(app) as client:
                            client.cookies.set(settings.session_cookie_name, "owner-a")
                            response = client.get("/reports/report-pdf-response/export/pdf")

        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(
            response.headers["Content-Disposition"],
            'attachment; filename="report-pdf-response.pdf"',
        )
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))


if __name__ == "__main__":
    unittest.main()
