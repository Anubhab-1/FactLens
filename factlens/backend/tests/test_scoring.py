from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from pipeline.extractor import _looks_like_outline, _parse_json_array, extract_claims
from pipeline.scoring import (
    calibrate_verdict,
    classify_claim_type,
    extract_best_snippet,
    summarize_retrieval,
)


class ScoringTests(unittest.TestCase):
    def test_classify_claim_type_prefers_numeric(self) -> None:
        claim_type = classify_claim_type("India's GDP grew by 7.8% in 2024.")
        self.assertEqual(claim_type, "numeric")

    def test_extract_best_snippet_selects_most_relevant_sentence(self) -> None:
        claim = "Paris is the capital of France."
        content = (
            "France is a country in Europe. "
            "Paris is the capital of France and its largest city. "
            "It is known for art, fashion, and culture."
        )
        snippet = extract_best_snippet(claim, content)
        self.assertIn("Paris is the capital of France", snippet)

    def test_calibrate_verdict_true_with_strong_support(self) -> None:
        sources = [
            {
                "id": "S1",
                "url": "https://example.gov/fact",
                "overall_score": 0.92,
                "authority_score": 0.97,
                "recency_score": 0.9,
            },
            {
                "id": "S2",
                "url": "https://example.edu/report",
                "overall_score": 0.84,
                "authority_score": 0.9,
                "recency_score": 0.76,
            },
        ]
        assessments = [
            {"source_id": "S1", "stance": "SUPPORT", "strength": 0.95},
            {"source_id": "S2", "stance": "SUPPORT", "strength": 0.86},
        ]

        verdict = calibrate_verdict(assessments, sources)
        self.assertEqual(verdict["verdict"], "TRUE")
        self.assertGreaterEqual(verdict["confidence"], 0.68)

    def test_calibrate_verdict_partial_when_sources_conflict(self) -> None:
        sources = [
            {
                "id": "S1",
                "url": "https://example.gov/fact",
                "overall_score": 0.9,
                "authority_score": 0.95,
                "recency_score": 0.88,
            },
            {
                "id": "S2",
                "url": "https://example.com/article",
                "overall_score": 0.82,
                "authority_score": 0.7,
                "recency_score": 0.8,
            },
        ]
        assessments = [
            {"source_id": "S1", "stance": "SUPPORT", "strength": 0.9},
            {"source_id": "S2", "stance": "CONFLICT", "strength": 0.8},
        ]

        verdict = calibrate_verdict(assessments, sources)
        self.assertEqual(verdict["verdict"], "PARTIALLY_TRUE")
        self.assertTrue(verdict["conflict_detected"])

    def test_calibrate_verdict_time_sensitive_claim_needs_dated_evidence(self) -> None:
        sources = [
            {
                "id": "S1",
                "url": "https://example.com/current",
                "overall_score": 0.86,
                "authority_score": 0.85,
                "recency_score": 0.45,
                "published_date": "unknown",
            },
            {
                "id": "S2",
                "url": "https://example.com/archive",
                "overall_score": 0.8,
                "authority_score": 0.78,
                "recency_score": 0.45,
                "published_date": "unknown",
            },
        ]
        assessments = [
            {"source_id": "S1", "stance": "SUPPORT", "strength": 0.9},
            {"source_id": "S2", "stance": "CONFLICT", "strength": 0.8},
        ]

        verdict = calibrate_verdict(assessments, sources, claim_time_sensitive=True)
        self.assertEqual(verdict["verdict"], "UNVERIFIABLE")
        self.assertIn(
            "The claim appears time-sensitive but none of the relevant sources were date-stamped.",
            verdict["risk_flags"],
        )

    def test_calibrate_verdict_material_conflict_blocks_true(self) -> None:
        sources = [
            {
                "id": "S1",
                "url": "https://example.gov/fact",
                "overall_score": 0.91,
                "authority_score": 0.97,
                "recency_score": 0.92,
                "published_date": "2026-03-01",
            },
            {
                "id": "S2",
                "url": "https://example.org/report",
                "overall_score": 0.7,
                "authority_score": 0.76,
                "recency_score": 0.86,
                "published_date": "2026-02-25",
            },
        ]
        assessments = [
            {"source_id": "S1", "stance": "SUPPORT", "strength": 0.95},
            {"source_id": "S2", "stance": "CONFLICT", "strength": 0.8},
        ]

        verdict = calibrate_verdict(assessments, sources)
        self.assertEqual(verdict["verdict"], "PARTIALLY_TRUE")

    def test_summarize_retrieval_counts_dated_sources_and_domains(self) -> None:
        summary = summarize_retrieval(
            [
                {
                    "domain": "reuters.com",
                    "authority_score": 0.94,
                    "recency_score": 0.9,
                    "published_date": "2026-03-10",
                },
                {
                    "domain": "bbc.com",
                    "authority_score": 0.9,
                    "recency_score": 0.8,
                    "published_date": "2026-02-01",
                },
                {
                    "domain": "bbc.com",
                    "authority_score": 0.82,
                    "recency_score": 0.45,
                    "published_date": "unknown",
                },
            ]
        )

        self.assertEqual(summary["dated_count"], 2)
        self.assertEqual(summary["distinct_domain_count"], 2)

    def test_parse_json_array_raises_value_error_on_unterminated_string(self) -> None:
        malformed = '[{"id": "1", "claim": "Open quote\n}]'
        with self.assertRaises(ValueError):
            _parse_json_array(malformed)

    def test_extract_claims_falls_back_when_retry_parse_is_malformed(self) -> None:
        responses = iter(
            [
                "not json at all",
                '[{"id": "1", "claim": "unterminated\n}]',
            ]
        )

        async def fake_invoke(_message: str) -> str:
            return next(responses)

        with patch("pipeline.extractor.llm", object()):
            with patch("pipeline.extractor._invoke_extractor", side_effect=fake_invoke):
                claims = asyncio.run(
                    extract_claims("Paris is the capital of France. It is in Europe.")
                )

        self.assertGreaterEqual(len(claims), 1)
        self.assertEqual(claims[0]["claim"], "Paris is the capital of France.")

    def test_outline_detection_blocks_table_of_contents_input(self) -> None:
        outline = (
            "Climate change\n"
            "Causes\n"
            "Greenhouse gases\n"
            "Effects on weather\n"
            "Sea level rise\n"
            "Mitigation\n"
            "Adaptation\n"
            "Policy\n"
            "Public opinion\n"
            "History of climate science"
        )

        self.assertTrue(_looks_like_outline(outline))
        self.assertEqual(asyncio.run(extract_claims(outline)), [])


if __name__ == "__main__":
    unittest.main()
