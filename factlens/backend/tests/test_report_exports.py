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
        "label": "NO_STRONG_SIGNAL",
        "ai_probability": 0.18,
        "signals_found": ["no obvious artifact clusters"],
        "explanation": "No strong synthetic-media cues were returned.",
        "media_url": "https://images.example/photo.png",
        "analysis_mode": "vision_llm_heuristic",
        "warnings": ["This is a heuristic synthetic-media review, not a forensic deepfake determination."],
        "limitations": ["This result comes from a general vision LLM, not a forensic deepfake classifier."],
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
                    "id": "S1",
                    "title": "Mars Facts",
                    "url": "https://science.example/mars-facts",
                    "domain": "science.example",
                    "published_label": "Mar 20, 2026",
                    "authority_score": 0.98,
                    "relevance_score": 0.94,
                    "overall_score": 0.96,
                    "evidence_passages": [
                        {
                            "id": "passage-1",
                            "text": "Mars has two moons named Phobos and Deimos.",
                            "score": 0.88,
                            "kind": "sentence",
                        }
                    ],
                    "source_snapshot": {
                        "snapshot_id": "snapshot-marsproof",
                        "captured_at": "2026-03-21T15:00:00+00:00",
                        "content_hash": "abc123def4567890",
                    },
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
            "temporal_context": {
                "status": "dated_but_not_required",
                "requires_recency": False,
                "dated_source_count": 1,
                "freshest_date": "2026-03-20",
                "oldest_date": "2026-03-20",
                "summary": "Dated evidence was available through 2026-03-20, although this claim is not strongly time-sensitive.",
            },
            "subclaim_summary": {
                "count": 2,
                "mixed_support": True,
                "verdict_breakdown": {"TRUE": 1, "FALSE": 1},
                "synthesis_note": "Subclaim review found that different parts of this claim resolve differently.",
            },
            "subclaim_results": [
                {
                    "subclaim_id": "1-sub1",
                    "claim": "Mars has two moons.",
                    "verdict": "TRUE",
                    "confidence": 0.92,
                },
                {
                    "subclaim_id": "1-sub2",
                    "claim": "Mars has a moon named Europa.",
                    "verdict": "FALSE",
                    "confidence": 0.88,
                },
            ],
            "evidence_used": [
                {
                    "id": "S1",
                    "title": "Mars Facts",
                    "url": "https://science.example/mars-facts",
                    "domain": "science.example",
                    "published_label": "Mar 20, 2026",
                    "overall_score": 0.96,
                    "evidence_passages": [
                        {
                            "id": "passage-1",
                            "text": "Mars has two moons named Phobos and Deimos.",
                            "score": 0.88,
                            "kind": "sentence",
                        }
                    ],
                    "source_snapshot": {
                        "snapshot_id": "snapshot-marsproof",
                        "captured_at": "2026-03-21T15:00:00+00:00",
                        "content_hash": "abc123def4567890",
                    },
                }
            ],
            "evidence_provenance": [
                {
                    "source_id": "S1",
                    "source_title": "Mars Facts",
                    "url": "https://science.example/mars-facts",
                    "domain": "science.example",
                    "stance": "SUPPORT",
                    "published_label": "Mar 20, 2026",
                    "overall_score": 0.96,
                    "primary_quote": "Mars has two moons named Phobos and Deimos.",
                    "top_passages": [
                        {
                            "id": "passage-1",
                            "text": "Mars has two moons named Phobos and Deimos.",
                            "score": 0.88,
                            "kind": "sentence",
                        }
                    ],
                    "snapshot_id": "snapshot-marsproof",
                    "captured_at": "2026-03-21T15:00:00+00:00",
                    "content_hash": "abc123def4567890",
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
        self.assertIn(b"No strong synthetic-media signal", pdf_bytes)
        self.assertIn(b"Snapshot proof 1", pdf_bytes)
        self.assertIn(b"snapshot-marsproof", pdf_bytes)
        self.assertIn(b"RUN DIAGNOSTICS", pdf_bytes)
        self.assertIn(b"Extraction:", pdf_bytes)
        self.assertIn(b"Verification:", pdf_bytes)
        self.assertIn(b"Temporal context:", pdf_bytes)
        self.assertIn(b"Subclaim synthesis:", pdf_bytes)
        self.assertIn(b"Mars has two moons.", pdf_bytes)

    def test_build_report_pdf_includes_contradiction_type_labels(self) -> None:
        report = build_completed_report("report-pdf-conflict")
        report["results"][0]["verdict"] = "PARTIALLY_TRUE"
        report["results"][0]["conflict_detected"] = True
        report["results"][0]["conflict_summary"] = {
            "summary": "Supporting and conflicting sources disagree mainly because of direct debunking and entity mismatch.",
            "drivers": ["direct debunking", "entity mismatch"],
            "contradiction_types": [
                {"id": "direct_debunking", "label": "Direct debunking"},
                {"id": "entity_mismatch", "label": "Entity mismatch"},
            ],
            "primary_contradiction_type": "direct_debunking",
            "supporting_count": 1,
            "conflicting_count": 1,
            "mixed_count": 0,
            "supporting_newest": "2026-03-20",
            "conflicting_newest": "2026-03-19",
            "supporting_avg_authority": 0.98,
            "conflicting_avg_authority": 0.82,
        }
        pdf_bytes = build_report_pdf(report)

        self.assertIn(b"Contradiction types:", pdf_bytes)
        self.assertIn(b"Direct debunking", pdf_bytes)
        self.assertIn(b"Entity mismatch", pdf_bytes)

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
