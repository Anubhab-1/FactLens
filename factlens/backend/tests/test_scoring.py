from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pipeline.extractor import (
    _looks_like_outline,
    _parse_json_array,
    extract_claims,
    extract_claims_with_metadata,
)
from pipeline.retriever import retrieve_evidence
from pipeline.scoring import (
    calibrate_verdict,
    claim_alias_phrases,
    classify_claim_type,
    extract_evidence_passages,
    extract_best_snippet,
    compute_relevance_score,
    infer_source_origin,
    summarize_conflict_profile,
    summarize_retrieval,
)
from pipeline.verifier import recalculate_claim_result, verify_claim


class _QueuedVerifierLLM:
    def __init__(self, responses: list[str]) -> None:
        self._primary = [r for r in responses if '"correction_needed"' not in r and "'correction_needed'" not in r]
        self._reflection = [r for r in responses if '"correction_needed"' in r or "'correction_needed'" in r]
        if not self._primary and responses:
            self._primary = list(responses)

    async def ainvoke(self, messages):
        sys_msg = str(messages[0].content) if messages else ""
        if "skeptical fact-check auditor" in sys_msg:
            if not self._reflection:
                return SimpleNamespace(content='{"correction_needed": false, "suggested_verdict": "UNVERIFIABLE", "reasoning": ""}')
            return SimpleNamespace(content=self._reflection.pop(0) if len(self._reflection) > 1 else self._reflection[0])
        else:
            if not self._primary:
                raise AssertionError("No queued primary responses remain.")
            return SimpleNamespace(content=self._primary.pop(0) if len(self._primary) > 1 else self._primary[0])


class _FailingVerifierLLM:
    async def ainvoke(self, _messages):
        raise RuntimeError("model failure")


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        from pipeline import retriever
        retriever._search_provider_failures.clear()
        retriever._search_provider_last_failure.clear()
        retriever._search_provider_circuit_open.clear()

    def test_recalculate_claim_result_support_override_flips_verdict(self) -> None:
        claim = {
            "id": "1",
            "claim": "Example claim",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        result = {
            "claim_id": "1",
            "claim": "Example claim",
            "claim_type": "entity",
            "time_sensitive": False,
            "claim_requires_recency": False,
            "verdict": "TRUE",
            "confidence": 0.81,
            "reasoning": "Original model verdict.",
            "risk_flags": [],
            "query_variants": [],
            "retrieval_summary": {"source_count": 2},
            "evidence_used": [
                {
                    "id": "S1",
                    "url": "https://example.gov/support",
                    "title": "Government statement",
                    "overall_score": 0.92,
                    "authority_score": 0.97,
                    "recency_score": 0.9,
                    "published_date": "2026-03-20",
                    "published_label": "2026-03-20",
                    "snippet": "The claim is correct.",
                    "stance": "SUPPORT",
                    "strength": 0.94,
                    "assessment_summary": "Supports the claim.",
                    "snippet_used": "The claim is correct.",
                },
                {
                    "id": "S2",
                    "url": "https://example.org/conflict",
                    "title": "Independent audit",
                    "overall_score": 0.86,
                    "authority_score": 0.88,
                    "recency_score": 0.82,
                    "published_date": "2026-03-18",
                    "published_label": "2026-03-18",
                    "snippet": "The claim is incorrect.",
                    "stance": "CONFLICT",
                    "strength": 0.9,
                    "assessment_summary": "Conflicts with the claim.",
                    "snippet_used": "The claim is incorrect.",
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

        recalculated = recalculate_claim_result(
            claim,
            result,
            overrides={"S1": "CONFLICT"},
        )

        self.assertEqual(recalculated["verdict"], "FALSE")
        self.assertIsNotNone(recalculated["manual_override"])
        self.assertEqual(recalculated["manual_override"]["override_count"], 1)
        self.assertIn("manually reclassifying 1 source", recalculated["reasoning"].lower())
        self.assertEqual(recalculated["supporting_evidence"], [])
        self.assertEqual(len(recalculated["conflicting_evidence"]), 2)

    def test_recalculate_claim_result_with_empty_overrides_resets_to_base_verdict(self) -> None:
        claim = {
            "id": "1",
            "claim": "Example claim",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        result = {
            "claim_id": "1",
            "claim": "Example claim",
            "claim_type": "entity",
            "time_sensitive": False,
            "claim_requires_recency": False,
            "verdict": "FALSE",
            "confidence": 0.73,
            "reasoning": "Overridden verdict.",
            "risk_flags": ["Manual review changed 1 source stance."],
            "query_variants": [],
            "retrieval_summary": {"source_count": 2},
            "evidence_used": [
                {
                    "id": "S1",
                    "url": "https://example.gov/support",
                    "title": "Government statement",
                    "overall_score": 0.92,
                    "authority_score": 0.97,
                    "recency_score": 0.9,
                    "published_date": "2026-03-20",
                    "published_label": "2026-03-20",
                    "snippet": "The claim is correct.",
                    "stance": "CONFLICT",
                    "strength": 0.94,
                    "assessment_summary": "Supports the claim.",
                    "snippet_used": "The claim is correct.",
                },
                {
                    "id": "S2",
                    "url": "https://example.org/conflict",
                    "title": "Independent audit",
                    "overall_score": 0.86,
                    "authority_score": 0.88,
                    "recency_score": 0.82,
                    "published_date": "2026-03-18",
                    "published_label": "2026-03-18",
                    "snippet": "The claim is incorrect.",
                    "stance": "CONFLICT",
                    "strength": 0.9,
                    "assessment_summary": "Conflicts with the claim.",
                    "snippet_used": "The claim is incorrect.",
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
            "manual_override": {
                "active": True,
                "updated_at": "2026-03-22T10:00:00+00:00",
                "override_count": 1,
                "overrides": [
                    {
                        "source_id": "S1",
                        "url": "https://example.gov/support",
                        "from_stance": "SUPPORT",
                        "to_stance": "CONFLICT",
                    }
                ],
                "base_verdict": "TRUE",
                "base_confidence": 0.81,
            },
        }

        recalculated = recalculate_claim_result(claim, result, overrides={})

        self.assertEqual(recalculated["verdict"], "PARTIALLY_TRUE")
        self.assertIsNone(recalculated["manual_override"])
        self.assertEqual(len(recalculated["supporting_evidence"]), 1)
        self.assertEqual(len(recalculated["conflicting_evidence"]), 1)

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

    def test_extract_evidence_passages_prefers_direct_grounding_sentence(self) -> None:
        claim = "Mars has two moons named Phobos and Deimos."
        content = (
            "Mars is the fourth planet from the Sun. "
            "Mars has two moons named Phobos and Deimos. "
            "Scientists continue to study both moons."
        )

        passages = extract_evidence_passages(claim, content, title="Mars Facts")

        self.assertGreaterEqual(len(passages), 1)
        self.assertIn("Phobos and Deimos", passages[0]["text"])
        self.assertGreaterEqual(passages[0]["score"], 0.5)
        self.assertTrue(str(passages[0]["id"]).startswith("passage-"))
        self.assertEqual(passages[0]["char_count"], len(passages[0]["text"]))

    def test_extract_evidence_passages_uses_numeric_alignment(self) -> None:
        claim = "India's GDP grew by 7.8% in 2024."
        content = (
            "India posted strong economic growth in 2024. "
            "Official estimates said GDP grew by 7.8% in 2024, exceeding expectations. "
            "Analysts debated how long that pace would continue."
        )

        passages = extract_evidence_passages(claim, content, title="Economic update")

        self.assertGreaterEqual(len(passages), 1)
        self.assertIn("7.8%", passages[0]["text"])
        self.assertIn("2024", passages[0]["text"])

    def test_exact_value_claims_preserve_short_symbol_tokens(self) -> None:
        claim = "The chemical symbol for gold is Au."
        content = (
            "Gold appears in the periodic table as Au. "
            "It has atomic number 79 and is widely used in electronics and jewelry."
        )

        snippet = extract_best_snippet(claim, content, title="Gold facts")
        passages = extract_evidence_passages(claim, content, title="Gold facts")
        relevance = compute_relevance_score(claim, "Gold facts", snippet, content)

        self.assertIn("Au", snippet)
        self.assertGreaterEqual(len(passages), 1)
        self.assertIn("Au", passages[0]["text"])
        self.assertGreaterEqual(relevance, 0.45)

    def test_claim_alias_phrases_expand_known_entities_and_titles(self) -> None:
        who_aliases = claim_alias_phrases("WHO issued updated guidance.")
        org_aliases = claim_alias_phrases("The World Health Organization issued updated guidance.")
        pm_aliases = claim_alias_phrases("The PM of India is Narendra Modi.")

        self.assertIn("World Health Organization", who_aliases)
        self.assertIn("WHO", org_aliases)
        self.assertIn("prime minister", [alias.lower() for alias in pm_aliases])

    def test_compute_relevance_score_uses_alias_expansion_for_known_entities(self) -> None:
        claim = "WHO declared mpox a public health emergency of international concern."
        title = "World Health Organization statement"
        snippet = "The World Health Organization declared mpox a public health emergency of international concern."
        content = (
            "The World Health Organization declared mpox a public health emergency of international concern. "
            "The decision was announced after an emergency committee meeting."
        )

        relevance = compute_relevance_score(claim, title, snippet, content)

        self.assertGreaterEqual(relevance, 0.65)

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

    def test_calibrate_verdict_true_with_clean_timeless_consensus(self) -> None:
        sources = [
            {
                "id": "S1",
                "url": "https://physics.nist.gov/cgi-bin/Star/compos.pl?ap079",
                "overall_score": 0.62,
                "authority_score": 0.97,
                "relevance_score": 0.33,
                "recency_score": 0.45,
                "evidence_passages": [{"text": "Composition of GOLD: Atomic number 79", "score": 0.33}],
                "published_date": "unknown",
            },
            {
                "id": "S2",
                "url": "https://www.periodictable.one/element/79",
                "overall_score": 0.53,
                "authority_score": 0.48,
                "relevance_score": 0.62,
                "recency_score": 0.45,
                "evidence_passages": [{"text": "Gold in the periodic table. Symbol Au. Atomic number 79.", "score": 0.72}],
                "published_date": "unknown",
            },
        ]
        assessments = [
            {
                "source_id": "S1",
                "stance": "SUPPORT",
                "strength": 0.9,
                "summary": "NIST material on gold.",
                "snippet_used": "Composition of GOLD: Atomic number 79",
            },
            {
                "source_id": "S2",
                "stance": "SUPPORT",
                "strength": 0.9,
                "summary": "Periodic table listing for gold.",
                "snippet_used": "Symbol Au. Atomic number 79.",
            },
        ]

        verdict = calibrate_verdict(assessments, sources)

        self.assertEqual(verdict["verdict"], "TRUE")
        self.assertGreaterEqual(verdict["confidence"], 0.68)
        self.assertNotIn("Most relevant sources were medium or low authority.", verdict["risk_flags"])

    def test_calibrate_verdict_true_with_grounded_consensus_without_authoritative_support(self) -> None:
        sources = [
            {
                "id": "S1",
                "url": "https://www.newworldencyclopedia.org/entry/Paris,_France",
                "overall_score": 0.71,
                "authority_score": 0.72,
                "relevance_score": 0.75,
                "recency_score": 0.45,
                "evidence_passages": [{"text": "Paris is the capital city of France.", "score": 0.74}],
                "published_date": "unknown",
            },
            {
                "id": "S2",
                "url": "https://www.mapsofworld.com/where-is/paris.html",
                "overall_score": 0.64,
                "authority_score": 0.55,
                "relevance_score": 0.75,
                "recency_score": 0.5,
                "evidence_passages": [
                    {
                        "text": "Paris is the capital and largest city of France, situated on the River Seine.",
                        "score": 0.74,
                    }
                ],
                "published_date": "2024-05-16",
            },
        ]
        assessments = [
            {
                "source_id": "S1",
                "stance": "SUPPORT",
                "strength": 0.72,
                "summary": "New World Encyclopedia article about Paris, France.",
                "snippet_used": "Paris is the capital city of France.",
            },
            {
                "source_id": "S2",
                "stance": "SUPPORT",
                "strength": 0.55,
                "summary": "Map article about Paris in France.",
                "snippet_used": "Paris is the capital and largest city of France.",
            },
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

    def test_calibrate_verdict_keeps_single_medium_quality_source_unverifiable(self) -> None:
        sources = [
            {
                "id": "S1",
                "url": "https://example.com/blog-post",
                "overall_score": 0.61,
                "authority_score": 0.58,
                "relevance_score": 0.79,
                "recency_score": 0.82,
                "published_date": "2026-03-20",
                "evidence_passages": [
                    {
                        "text": "Mars has exactly two moons named Phobos and Deimos.",
                        "score": 0.84,
                    }
                ],
            }
        ]
        assessments = [
            {
                "source_id": "S1",
                "stance": "SUPPORT",
                "strength": 0.84,
                "summary": "A single blog post supports the claim.",
                "snippet_used": "Mars has exactly two moons named Phobos and Deimos.",
            }
        ]

        verdict = calibrate_verdict(assessments, sources)

        self.assertEqual(verdict["verdict"], "UNVERIFIABLE")
        self.assertIn("The verdict relies on sparse evidence coverage.", verdict["risk_flags"])

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

    def test_summarize_conflict_profile_identifies_temporal_and_numeric_drift(self) -> None:
        claim = {
            "claim": "India's GDP grew by 7.8% in 2024.",
            "claim_type": "numeric",
            "time_sensitive": True,
        }
        supporting = [
            {
                "published_date": "2026-03-10",
                "authority_score": 0.94,
                "snippet": "Official estimates said GDP grew by 7.8% in 2024.",
                "title": "Government estimate",
            }
        ]
        conflicting = [
            {
                "published_date": "2025-01-05",
                "authority_score": 0.61,
                "snippet": "Earlier reporting claimed GDP growth was 6.9% in 2024.",
                "title": "Old market analysis",
            }
        ]

        summary = summarize_conflict_profile(claim, supporting, conflicting, [])

        self.assertIn("temporal drift", summary["drivers"])
        self.assertIn("authority imbalance", summary["drivers"])
        self.assertIn("numeric disagreement", summary["drivers"])
        self.assertEqual(
            [item["id"] for item in summary["contradiction_types"]],
            ["date_drift", "metric_mismatch"],
        )
        self.assertEqual(summary["supporting_newest"], "2026-03-10")
        self.assertEqual(summary["conflicting_newest"], "2025-01-05")

    def test_summarize_conflict_profile_marks_scope_mismatch_when_mixed_evidence_exists(self) -> None:
        claim = {
            "claim": "The company announced layoffs because revenue fell 20%.",
            "claim_type": "causal",
            "time_sensitive": False,
        }
        supporting = [
            {
                "published_date": "2026-03-01",
                "authority_score": 0.82,
                "snippet": "The company announced layoffs after reporting lower revenue.",
            }
        ]
        conflicting = [
            {
                "published_date": "2026-03-02",
                "authority_score": 0.8,
                "snippet": "Executives denied that the layoffs were tied directly to revenue.",
            }
        ]
        mixed = [
            {
                "published_date": "2026-03-03",
                "authority_score": 0.78,
                "snippet": "Coverage agreed layoffs happened but disputed the cause.",
            }
        ]

        summary = summarize_conflict_profile(claim, supporting, conflicting, mixed)

        self.assertIn("scope mismatch", summary["drivers"])
        self.assertGreater(summary["mixed_count"], 0)
        self.assertIn("scope_mismatch", {item["id"] for item in summary["contradiction_types"]})

    def test_summarize_conflict_profile_uses_mixed_evidence_when_support_bucket_is_empty(self) -> None:
        claim = {
            "claim": "Tomatoes are vegetables.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        conflicting = [
            {
                "published_date": "2026-03-02",
                "authority_score": 0.58,
                "snippet": "Tomatoes are botanically fruits.",
            }
        ]
        mixed = [
            {
                "published_date": "2026-03-01",
                "authority_score": 0.79,
                "snippet": "Tomatoes are fruits that are considered vegetables in culinary contexts.",
            }
        ]

        summary = summarize_conflict_profile(claim, [], conflicting, mixed)

        self.assertNotEqual(summary["summary"], "")
        self.assertIn("scope mismatch", summary["drivers"])
        self.assertEqual(summary["supporting_count"], 0)
        self.assertEqual(summary["mixed_count"], 1)
        self.assertEqual(summary["supporting_newest"], "2026-03-01")

    def test_summarize_conflict_profile_classifies_debunking_and_entity_mismatch(self) -> None:
        claim = {
            "claim": "The current CEO of ExampleCorp is Jane Doe.",
            "claim_type": "entity",
            "time_sensitive": True,
        }
        supporting = [
            {
                "published_date": "2026-03-10",
                "authority_score": 0.91,
                "snippet": "Jane Doe is the current CEO of ExampleCorp.",
            }
        ]
        conflicting = [
            {
                "published_date": "2026-03-12",
                "authority_score": 0.88,
                "snippet": "This claim is false. John Smith is the CEO of ExampleCorp.",
            }
        ]

        summary = summarize_conflict_profile(claim, supporting, conflicting, [])

        self.assertIn("direct debunking", summary["drivers"])
        self.assertIn("entity mismatch", summary["drivers"])
        self.assertEqual(
            [item["id"] for item in summary["contradiction_types"]],
            ["direct_debunking", "entity_mismatch"],
        )
        self.assertEqual(summary["primary_contradiction_type"], "direct_debunking")

    def test_summarize_retrieval_counts_dated_sources_and_domains(self) -> None:
        summary = summarize_retrieval(
            [
                {
                    "domain": "reuters.com",
                    "authority_score": 0.94,
                    "recency_score": 0.9,
                    "published_date": "2026-03-10",
                    "source_origin": "secondary",
                    "independence_key": "reuters",
                },
                {
                    "domain": "news.example.com",
                    "authority_score": 0.9,
                    "recency_score": 0.8,
                    "published_date": "2026-02-01",
                    "source_origin": "first_party",
                    "independence_key": "example.com",
                },
                {
                    "domain": "research.example.com",
                    "authority_score": 0.82,
                    "recency_score": 0.45,
                    "published_date": "unknown",
                    "source_origin": "official",
                    "independence_key": "example.com",
                },
            ]
        )

        self.assertEqual(summary["dated_count"], 2)
        self.assertEqual(summary["distinct_domain_count"], 3)
        self.assertEqual(summary["independent_source_count"], 2)
        self.assertEqual(summary["official_source_count"], 1)
        self.assertEqual(summary["first_party_count"], 1)
        self.assertEqual(summary["primary_source_count"], 2)

    def test_infer_source_origin_detects_first_party_company_page(self) -> None:
        profile = infer_source_origin(
            "The current CEO of ExampleCorp is Jane Doe.",
            "example.com",
            url="https://example.com/leadership",
            source_type="commercial",
        )

        self.assertEqual(profile["source_origin"], "first_party")
        self.assertTrue(profile["primary_preferred"])
        self.assertEqual(profile["independence_key"], "example.com")

    def test_parse_json_array_raises_value_error_on_unterminated_string(self) -> None:
        malformed = '[{"id": "1", "claim": "Open quote\n}]'
        with self.assertRaises(ValueError):
            _parse_json_array(malformed)

    def test_parse_published_date_ignores_invalid_month_matches(self) -> None:
        from pipeline.scoring import parse_published_date

        parsed = parse_published_date("This page references 2026-30-12 in malformed metadata.")

        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 1)
        self.assertEqual(parsed.day, 1)

    def test_extract_claims_falls_back_to_heuristics_when_retry_parse_is_malformed(self) -> None:
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
                extraction = asyncio.run(
                    extract_claims_with_metadata("Paris is the capital of France. It is in Europe.")
                )

        self.assertEqual(extraction["meta"]["mode"], "heuristic")
        self.assertGreaterEqual(len(extraction["claims"]), 1)
        self.assertEqual(extraction["claims"][0]["claim"], "Paris is the capital of France.")
        self.assertIn("heuristic claim draft", extraction["meta"]["warnings"][0])

    def test_extract_claims_uses_chunked_llm_extraction_for_long_input(self) -> None:
        long_text = ("Background filler about Paris and France. " * 220).strip()

        async def fake_chunked(_text: str):
            return (
                [
                    {
                        "id": "1",
                        "claim": "Paris is the capital of France.",
                        "context": "Paris is the capital of France.",
                        "time_sensitive": False,
                        "claim_type": "entity",
                    },
                    {
                        "id": "2",
                        "claim": "The Eiffel Tower is in Paris.",
                        "context": "The Eiffel Tower is in Paris.",
                        "time_sensitive": False,
                        "claim_type": "entity",
                    },
                ],
                ["Long input was extracted in 3 chunks for better claim coverage."],
            )

        with patch("pipeline.extractor._extract_chunked_claims", side_effect=fake_chunked):
            extraction = asyncio.run(extract_claims_with_metadata(long_text))

        self.assertEqual(extraction["meta"]["mode"], "llm")
        self.assertEqual(len(extraction["claims"]), 2)
        self.assertTrue(
            any("Long input was extracted in" in warning for warning in extraction["meta"]["warnings"])
        )

    def test_extract_claims_drops_refined_claims_that_rewrite_the_source(self) -> None:
        original_claims = [
            {
                "id": "1",
                "claim": "Berlin is in Spain.",
                "context": "Berlin is in Spain.",
                "time_sensitive": False,
                "claim_type": "entity",
            }
        ]
        rewritten_claims = [
            {
                "id": "1",
                "claim": "Berlin is the capital of Germany.",
                "context": "Berlin is in Spain.",
                "time_sensitive": False,
                "claim_type": "entity",
            }
        ]

        with patch("pipeline.extractor.llm", object()):
            with patch("pipeline.extractor._extract_llm_claims", return_value=original_claims):
                with patch("pipeline.extractor._refine_extracted_claims", return_value=rewritten_claims):
                    extraction = asyncio.run(extract_claims_with_metadata("Berlin is in Spain."))

        self.assertEqual(extraction["meta"]["mode"], "heuristic")
        self.assertEqual(len(extraction["claims"]), 1)
        self.assertEqual(extraction["claims"][0]["claim"], "Berlin is in Spain.")
        self.assertTrue(
            any("not grounded in the source text" in warning for warning in extraction["meta"]["warnings"])
        )

    def test_extract_claims_uses_heuristics_only_when_no_provider_is_configured(self) -> None:
        with patch("pipeline.extractor.llm", None):
            with patch(
                "pipeline.extractor.llm_descriptor",
                new=SimpleNamespace(
                    status="unconfigured",
                    provider=None,
                    provider_label=None,
                    model=None,
                    issue="No provider configured.",
                ),
            ):
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

    def test_retrieve_evidence_surfaces_grounded_passages(self) -> None:
        claim = {
            "id": "1",
            "claim": "Mars has two moons named Phobos and Deimos.",
            "claim_type": "entity",
            "time_sensitive": False,
        }

        class FakeSearchTool:
            async def ainvoke(self, _payload: dict) -> list[dict]:
                return [
                    {
                        "url": "https://science.example/mars-facts",
                        "title": "Mars Facts",
                        "content": (
                            "Mars has two moons named Phobos and Deimos. "
                            "The moons are thought to be captured asteroids."
                        ),
                        "published_date": "2026-03-20",
                    }
                ]

        async def fake_generate_queries(_claim: dict) -> list[dict]:
            return [{"query": "Mars moons Phobos Deimos", "objective": "direct"}]

        async def fake_plan_recovery_queries(*_args, **_kwargs):
            return [], {
                "mode": "not_needed",
                "reasoning": "",
                "fallback_used": False,
            }

        with patch("pipeline.retriever.search_tool", FakeSearchTool()):
            with patch("pipeline.retriever._generate_queries", new=fake_generate_queries):
                with patch("pipeline.retriever._plan_recovery_queries", new=fake_plan_recovery_queries):
                    evidence = asyncio.run(retrieve_evidence(claim))

        self.assertEqual(evidence["claim_id"], "1")
        self.assertEqual(len(evidence["sources"]), 1)
        source = evidence["sources"][0]
        self.assertTrue(source["evidence_passages"])
        self.assertEqual(source["snippet"], source["evidence_passages"][0]["text"])
        self.assertIn("Phobos and Deimos", source["evidence_passages"][0]["text"])
        self.assertTrue(source["source_snapshot"]["snapshot_id"].startswith("snapshot-"))
        self.assertEqual(
            source["source_snapshot"]["passage_ids"][0],
            source["evidence_passages"][0]["id"],
        )

    def test_retrieve_evidence_runs_recovery_when_primary_pass_is_sparse(self) -> None:
        claim = {
            "id": "1",
            "claim": "The current CEO of ExampleCorp is Jane Doe.",
            "claim_type": "entity",
            "time_sensitive": True,
        }

        class FakeSearchTool:
            async def ainvoke(self, payload: dict) -> list[dict]:
                if payload["query"] == "primary query":
                    return []
                if payload["query"] == "recovery query":
                    return [
                        {
                            "url": "https://reuters.com/leadership",
                            "title": "Leadership team",
                            "content": "Jane Doe is the current CEO of ExampleCorp as of March 2026.",
                            "published_date": "2026-03-15",
                        }
                    ]
                return []

        async def fake_generate_queries(_claim: dict) -> list[dict]:
            return [{"query": "primary query", "objective": "direct", "phase": "primary"}]

        recovery_queries = [
            {"query": "recovery query", "objective": "recency", "phase": "recovery"}
        ]

        async def fake_plan_recovery_queries(*_args, **_kwargs):
            return recovery_queries, {
                "mode": "llm_planner",
                "reasoning": "",
                "fallback_used": False,
            }

        with patch("pipeline.retriever.search_tool", FakeSearchTool()):
            with patch("pipeline.retriever._generate_queries", new=fake_generate_queries):
                with patch("pipeline.retriever._plan_recovery_queries", new=fake_plan_recovery_queries):
                    with patch("pipeline.retriever._search_with_duckduckgo", return_value=[]):
                        with patch("pipeline.retriever._search_with_bing", return_value=[]):
                            evidence = asyncio.run(retrieve_evidence(claim))

        self.assertEqual(len(evidence["sources"]), 1)
        self.assertTrue(evidence["retrieval_summary"]["recovery_triggered"])
        self.assertEqual(evidence["retrieval_summary"]["recovery_query_count"], 5)
        self.assertIn("Sparse evidence coverage.", evidence["retrieval_summary"]["recovery_reason"])
        self.assertEqual(len(evidence["query_variants"]), 6)
        self.assertEqual(evidence["query_variants"][1]["phase"], "recovery")
        self.assertEqual(evidence["query_variants"][1]["status"], "ok")

    def test_retrieve_evidence_skips_recovery_when_primary_pass_is_strong(self) -> None:
        claim = {
            "id": "1",
            "claim": "Mars has two moons named Phobos and Deimos.",
            "claim_type": "entity",
            "time_sensitive": False,
        }

        class FakeSearchTool:
            async def ainvoke(self, _payload: dict) -> list[dict]:
                return [
                    {
                        "url": "https://science.example/mars-facts",
                        "title": "Mars Facts",
                        "content": "Mars has two moons named Phobos and Deimos.",
                        "published_date": "2026-03-20",
                    },
                    {
                        "url": "https://space.example/mars-overview",
                        "title": "Mars overview",
                        "content": "The two moons of Mars are Phobos and Deimos.",
                        "published_date": "2026-03-19",
                    },
                ]

        async def fake_generate_queries(_claim: dict) -> list[dict]:
            return [{"query": "primary query", "objective": "direct", "phase": "primary"}]

        with patch("pipeline.retriever.search_tool", FakeSearchTool()):
            with patch("pipeline.retriever._generate_queries", new=fake_generate_queries):
                with patch("pipeline.retriever._plan_recovery_queries") as recovery_planner:
                    evidence = asyncio.run(retrieve_evidence(claim))

        recovery_planner.assert_not_called()
        self.assertEqual(len(evidence["sources"]), 2)
        self.assertFalse(evidence["retrieval_summary"]["recovery_triggered"])
        self.assertEqual(evidence["retrieval_summary"]["query_attempt_count"], 1)

    def test_verify_claim_surfaces_retrieval_warning_when_no_sources_exist(self) -> None:
        claim = {
            "id": "1",
            "claim": "The Pacific Ocean is the largest ocean on Earth.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [],
            "query_variants": [],
            "retrieval_summary": {"source_count": 0},
            "error": "HTTPError('432 Client Error')",
        }

        result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(result["verdict"], "UNVERIFIABLE")
        self.assertIn("No evidence could be retrieved for this claim.", result["risk_flags"])
        self.assertIn("Retrieval warning: HTTPError('432 Client Error')", result["risk_flags"])

    def test_verify_claim_marks_missing_dated_evidence_for_time_sensitive_claims(self) -> None:
        claim = {
            "id": "1",
            "claim": "The current CEO of ExampleCorp is Jane Doe.",
            "claim_type": "entity",
            "time_sensitive": True,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "Company bio",
                    "url": "https://example.com/leadership",
                    "domain": "example.com",
                    "published_label": "unknown",
                    "authority_score": 0.72,
                    "relevance_score": 0.83,
                    "overall_score": 0.74,
                    "published_date": "unknown",
                    "snippet": "Jane Doe is the CEO of ExampleCorp.",
                    "evidence_passages": [
                        {"text": "Jane Doe is the CEO of ExampleCorp.", "score": 0.82}
                    ],
                }
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 1},
            "error": None,
        }

        with patch("pipeline.verifier.llm", new=_FailingVerifierLLM()):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertTrue(result["temporal_context"]["requires_recency"])
        self.assertEqual(result["temporal_context"]["status"], "dated_evidence_missing")
        self.assertIn(
            "does not include any reliable publication dates",
            result["temporal_context"]["summary"],
        )

    def test_verify_claim_builds_subclaim_map_for_compound_claims(self) -> None:
        claim = {
            "id": "1",
            "claim": "Paris is the capital of France and Berlin is in Spain.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "France overview",
                    "url": "https://example.com/france",
                    "domain": "example.com",
                    "published_label": "2026-03-20",
                    "authority_score": 0.82,
                    "relevance_score": 0.86,
                    "overall_score": 0.82,
                    "published_date": "2026-03-20",
                    "snippet": "Paris is the capital of France.",
                    "evidence_passages": [
                        {"text": "Paris is the capital of France.", "score": 0.9}
                    ],
                },
                {
                    "id": "S2",
                    "title": "Berlin fact check",
                    "url": "https://example.org/berlin",
                    "domain": "example.org",
                    "published_label": "2026-03-19",
                    "authority_score": 0.8,
                    "relevance_score": 0.84,
                    "overall_score": 0.79,
                    "published_date": "2026-03-19",
                    "snippet": "The statement that Berlin is in Spain is false. Berlin is in Germany.",
                    "evidence_passages": [
                        {"text": "The statement that Berlin is in Spain is false. Berlin is in Germany.", "score": 0.88}
                    ],
                },
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 2},
            "error": None,
        }

        with patch("pipeline.verifier.llm", new=_FailingVerifierLLM()):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(result["verdict"], "PARTIALLY_TRUE")
        self.assertEqual(len(result["subclaim_results"]), 2)
        self.assertTrue(result["subclaim_summary"]["mixed_support"])
        self.assertEqual(
            {item["verdict"] for item in result["subclaim_results"]},
            {"TRUE", "FALSE"},
        )
        self.assertTrue(
            any("Subclaim review found" in flag for flag in result["risk_flags"])
        )

    def test_verify_claim_uses_default_reasoning_when_model_overstates_support(self) -> None:
        claim = {
            "id": "1",
            "claim": "Gold is the best metal.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "Opinionated reference",
                    "url": "https://example.com/gold",
                    "domain": "example.com",
                    "published_label": "2026-03-20",
                    "authority_score": 0.55,
                    "relevance_score": 0.7,
                    "overall_score": 0.7,
                    "published_date": "2026-03-20",
                    "snippet": "Some people argue gold is the best metal.",
                    "evidence_passages": [
                        {"text": "Some people argue gold is the best metal.", "score": 0.61}
                    ],
                }
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 1},
            "error": None,
        }
        llm = _QueuedVerifierLLM(
            [
                '{"reasoning":"The claim is supported by multiple sources.","claim_requires_recency":false,"risk_flags":[],"source_assessments":[{"source_id":"S1","stance":"SUPPORT","strength":0.9,"summary":"Supports the claim.","snippet_used":"Some people argue gold is the best metal."}]}'
            ]
        )

        with patch("pipeline.verifier.llm", new=llm):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(result["verdict"], "UNVERIFIABLE")
        self.assertEqual(
            result["reasoning"],
            "The retrieved sources were too weak, too sparse, or too conflicting to justify a firmer verdict.",
        )

    def test_verify_claim_downgrades_quasi_moon_conflict_for_earth_satellite_claim(self) -> None:
        claim = {
            "id": "1",
            "claim": "Earth has one natural satellite, the Moon.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "NASA Moon facts",
                    "url": "https://science.nasa.gov/moon/",
                    "domain": "science.nasa.gov",
                    "published_label": "2026-03-18",
                    "authority_score": 0.99,
                    "relevance_score": 0.88,
                    "overall_score": 0.87,
                    "published_date": "2026-03-18",
                    "snippet": "The Moon is Earth's only permanent natural satellite.",
                    "evidence_passages": [
                        {
                            "text": "The Moon is Earth's only permanent natural satellite.",
                            "score": 0.89,
                        }
                    ],
                },
                {
                    "id": "S2",
                    "title": "Encyclopedia Moon overview",
                    "url": "https://example.org/moon-overview",
                    "domain": "example.org",
                    "published_label": "2026-03-19",
                    "authority_score": 0.82,
                    "relevance_score": 0.84,
                    "overall_score": 0.78,
                    "published_date": "2026-03-19",
                    "snippet": "Earth's only natural satellite is the Moon.",
                    "evidence_passages": [
                        {
                            "text": "Earth's only natural satellite is the Moon.",
                            "score": 0.84,
                        }
                    ],
                },
                {
                    "id": "S3",
                    "title": "Quasi-moon explainer",
                    "url": "https://abcnews.com/example-quasi-moon",
                    "domain": "abcnews.com",
                    "published_label": "2025-10-23",
                    "authority_score": 0.55,
                    "relevance_score": 0.42,
                    "overall_score": 0.5,
                    "published_date": "2025-10-23",
                    "snippet": "An asteroid named 2025 PN7 has become a quasi-moon to Earth.",
                    "evidence_passages": [
                        {
                            "text": "An asteroid named 2025 PN7 has become a quasi-moon to Earth, sharing the Earth's orbit until 2083.",
                            "score": 0.43,
                        }
                    ],
                },
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 3},
            "error": None,
        }
        llm = _QueuedVerifierLLM(
            [
                '{"reasoning":"The evidence supports the claim.","claim_requires_recency":false,"risk_flags":[],"source_assessments":[{"source_id":"S1","stance":"SUPPORT","strength":0.95,"summary":"NASA states the Moon is Earth\\u2019s only permanent natural satellite.","snippet_used":"The Moon is Earth\\u2019s only permanent natural satellite."},{"source_id":"S2","stance":"SUPPORT","strength":0.86,"summary":"Reference source says Earth\\u2019s only natural satellite is the Moon.","snippet_used":"Earth\\u2019s only natural satellite is the Moon."},{"source_id":"S3","stance":"CONFLICT","strength":0.8,"summary":"Suggests Earth has another moon.","snippet_used":"An asteroid named 2025 PN7 has become a quasi-moon to Earth."}]}'
            ]
        )

        with patch("pipeline.verifier.llm", new=llm):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(result["verdict"], "TRUE")
        self.assertEqual(result["conflicting_evidence"], [])
        self.assertEqual(
            next(
                item["stance"]
                for item in result["base_source_assessments"]
                if item["source_id"] == "S3"
            ),
            "IRRELEVANT",
        )

    def test_verify_claim_requires_direct_location_grounding_for_geography_claims(self) -> None:
        claim = {
            "id": "1",
            "claim": "Berlin is in Spain.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "Berlin overview",
                    "url": "https://example.org/berlin-overview",
                    "domain": "example.org",
                    "published_label": "2026-03-20",
                    "authority_score": 0.86,
                    "relevance_score": 0.84,
                    "overall_score": 0.82,
                    "published_date": "2026-03-20",
                    "snippet": "Berlin is the capital and largest city of Germany.",
                    "evidence_passages": [
                        {
                            "text": "Berlin is the capital and largest city of Germany.",
                            "score": 0.88,
                        }
                    ],
                },
                {
                    "id": "S2",
                    "title": "Money Heist spinoff",
                    "url": "https://example.com/berlin-series",
                    "domain": "example.com",
                    "published_label": "2026-03-19",
                    "authority_score": 0.55,
                    "relevance_score": 0.58,
                    "overall_score": 0.56,
                    "published_date": "2026-03-19",
                    "snippet": "The series Berlin will be set in Paris and Spain.",
                    "evidence_passages": [
                        {
                            "text": "The series Berlin will be set in Paris and Spain.",
                            "score": 0.61,
                        }
                    ],
                },
                {
                    "id": "S3",
                    "title": "Germany profile",
                    "url": "https://example.net/germany-profile",
                    "domain": "example.net",
                    "published_label": "2026-03-18",
                    "authority_score": 0.84,
                    "relevance_score": 0.82,
                    "overall_score": 0.8,
                    "published_date": "2026-03-18",
                    "snippet": "Berlin is Germany's capital city.",
                    "evidence_passages": [
                        {
                            "text": "Berlin is Germany's capital city.",
                            "score": 0.86,
                        }
                    ],
                },
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 3},
            "error": None,
        }
        llm = _QueuedVerifierLLM(
            [
                '{"reasoning":"The sources mention Berlin and Spain in multiple contexts.","claim_requires_recency":false,"risk_flags":[],"source_assessments":[{"source_id":"S1","stance":"MIXED","strength":0.6,"summary":"Mentions Berlin.","snippet_used":"Berlin is the capital and largest city of Germany."},{"source_id":"S2","stance":"MIXED","strength":0.58,"summary":"Mentions Berlin and Spain.","snippet_used":"The series Berlin will be set in Paris and Spain."},{"source_id":"S3","stance":"MIXED","strength":0.59,"summary":"Mentions Berlin.","snippet_used":"Berlin is Germany\\u0027s capital city."}]}'
            ]
        )

        with patch("pipeline.verifier.llm", new=llm):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(result["verdict"], "FALSE")
        stances = {
            item["source_id"]: item["stance"]
            for item in result["base_source_assessments"]
        }
        self.assertEqual(stances["S1"], "CONFLICT")
        self.assertEqual(stances["S2"], "IRRELEVANT")
        self.assertEqual(stances["S3"], "CONFLICT")

    def test_verify_claim_normalizes_role_assignment_claims_with_wrong_subject(self) -> None:
        claim = {
            "id": "1",
            "claim": "The capital of Australia is Sydney.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "Sydney overview",
                    "url": "https://example.org/sydney-overview",
                    "domain": "example.org",
                    "published_label": "2026-03-20",
                    "authority_score": 0.74,
                    "relevance_score": 0.64,
                    "overall_score": 0.71,
                    "published_date": "2026-03-20",
                    "snippet": "Sydney is the capital city of the state of New South Wales.",
                    "evidence_passages": [
                        {
                            "text": "Sydney is the capital city of the state of New South Wales.",
                            "score": 0.78,
                        }
                    ],
                },
                {
                    "id": "S2",
                    "title": "Australia profile",
                    "url": "https://example.net/australia-profile",
                    "domain": "example.net",
                    "published_label": "2026-03-19",
                    "authority_score": 0.86,
                    "relevance_score": 0.82,
                    "overall_score": 0.8,
                    "published_date": "2026-03-19",
                    "snippet": "Australia's capital is Canberra.",
                    "evidence_passages": [
                        {
                            "text": "Australia's capital is Canberra.",
                            "score": 0.84,
                        }
                    ],
                },
                {
                    "id": "S3",
                    "title": "ACT overview",
                    "url": "https://example.edu/act-overview",
                    "domain": "example.edu",
                    "published_label": "2026-03-18",
                    "authority_score": 0.83,
                    "relevance_score": 0.79,
                    "overall_score": 0.78,
                    "published_date": "2026-03-18",
                    "snippet": "Canberra, the capital city of Australia, is situated within the territory.",
                    "evidence_passages": [
                        {
                            "text": "Canberra, the capital city of Australia, is situated within the territory.",
                            "score": 0.85,
                        }
                    ],
                },
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 3},
            "error": None,
        }
        llm = _QueuedVerifierLLM(
            [
                '{"reasoning":"The sources are mixed.","claim_requires_recency":false,"risk_flags":[],"source_assessments":[{"source_id":"S1","stance":"SUPPORT","strength":0.8,"summary":"Mentions Sydney as a capital city.","snippet_used":"Sydney is the capital city of the state of New South Wales."},{"source_id":"S2","stance":"MIXED","strength":0.6,"summary":"Mentions Australia\'s capital.","snippet_used":"Australia\'s capital is Canberra."},{"source_id":"S3","stance":"MIXED","strength":0.6,"summary":"Mentions Canberra and Australia.","snippet_used":"Canberra, the capital city of Australia, is situated within the territory."}]}',
                '{"correction_needed": false, "suggested_verdict": "UNVERIFIABLE", "reasoning": ""}',
            ]
        )

        with patch("pipeline.verifier.llm", new=llm):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(result["verdict"], "FALSE")
        stances = {
            item["source_id"]: item["stance"]
            for item in result["base_source_assessments"]
        }
        self.assertEqual(stances["S1"], "CONFLICT")
        self.assertEqual(stances["S2"], "CONFLICT")
        self.assertEqual(stances["S3"], "CONFLICT")

    def test_verify_claim_normalizes_superlative_role_claims(self) -> None:
        claim = {
            "id": "1",
            "claim": "Sydney is the largest city in Australia.",
            "claim_type": "comparison",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "Sydney profile",
                    "url": "https://example.org/sydney-profile",
                    "domain": "example.org",
                    "published_label": "2026-03-20",
                    "authority_score": 0.74,
                    "relevance_score": 0.7,
                    "overall_score": 0.72,
                    "published_date": "2026-03-20",
                    "snippet": "Sydney today is Australia's largest city and a major international centre of culture and finance.",
                    "evidence_passages": [
                        {
                            "text": "Sydney today is Australia's largest city and a major international centre of culture and finance.",
                            "score": 0.86,
                        }
                    ],
                },
                {
                    "id": "S2",
                    "title": "Melbourne population report",
                    "url": "https://example.net/melbourne-report",
                    "domain": "example.net",
                    "published_label": "2026-03-19",
                    "authority_score": 0.78,
                    "relevance_score": 0.73,
                    "overall_score": 0.77,
                    "published_date": "2026-03-19",
                    "snippet": "Melbourne has overtaken Sydney to become Australia's largest city by population.",
                    "evidence_passages": [
                        {
                            "text": "Melbourne has overtaken Sydney to become Australia's largest city by population.",
                            "score": 0.85,
                        }
                    ],
                },
                {
                    "id": "S3",
                    "title": "Population ranking",
                    "url": "https://example.edu/population-ranking",
                    "domain": "example.edu",
                    "published_label": "2026-03-18",
                    "authority_score": 0.82,
                    "relevance_score": 0.76,
                    "overall_score": 0.8,
                    "published_date": "2026-03-18",
                    "snippet": "The largest city in Australia is Melbourne.",
                    "evidence_passages": [
                        {
                            "text": "The largest city in Australia is Melbourne.",
                            "score": 0.84,
                        }
                    ],
                },
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 3},
            "error": None,
        }
        llm = _QueuedVerifierLLM(
            [
                '{"reasoning":"The sources mention Sydney and Melbourne.","claim_requires_recency":false,"risk_flags":[],"source_assessments":[{"source_id":"S1","stance":"MIXED","strength":0.6,"summary":"Mentions Sydney.","snippet_used":"Sydney today is Australia\'s largest city and a major international centre of culture and finance."},{"source_id":"S2","stance":"MIXED","strength":0.6,"summary":"Mentions Melbourne and Sydney.","snippet_used":"Melbourne has overtaken Sydney to become Australia\'s largest city by population."},{"source_id":"S3","stance":"MIXED","strength":0.6,"summary":"Mentions the largest city in Australia.","snippet_used":"The largest city in Australia is Melbourne."}]}',
                '{"correction_needed": false, "suggested_verdict": "UNVERIFIABLE", "reasoning": ""}',
            ]
        )

        with patch("pipeline.verifier.llm", new=llm):
            result = asyncio.run(verify_claim(claim, evidence))

        stances = {
            item["source_id"]: item["stance"]
            for item in result["base_source_assessments"]
        }
        self.assertEqual(stances["S1"], "SUPPORT")
        self.assertEqual(stances["S2"], "CONFLICT")
        self.assertEqual(stances["S3"], "CONFLICT")
        self.assertEqual(result["verdict"], "FALSE")

    def test_verify_claim_uses_heuristics_to_rescue_direct_contextual_evidence(self) -> None:
        claim = {
            "id": "1",
            "claim": "Tomatoes are vegetables.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "Tomato plant profile",
                    "url": "https://example.edu/tomato-profile",
                    "domain": "example.edu",
                    "published_label": "2026-03-20",
                    "authority_score": 0.91,
                    "relevance_score": 0.7,
                    "overall_score": 0.78,
                    "published_date": "2026-03-20",
                    "snippet": "While the portion eaten is botanically a fruit, tomatoes are considered a vegetable due to their savory flavor.",
                    "evidence_passages": [
                        {
                            "text": "While the portion eaten is botanically a fruit, tomatoes are considered a vegetable due to their savory flavor.",
                            "score": 0.81,
                        }
                    ],
                },
                {
                    "id": "S2",
                    "title": "Reference explainer",
                    "url": "https://example.org/tomato-explainer",
                    "domain": "example.org",
                    "published_label": "2026-03-19",
                    "authority_score": 0.86,
                    "relevance_score": 0.76,
                    "overall_score": 0.8,
                    "published_date": "2026-03-19",
                    "snippet": "Tomatoes are fruits that are considered vegetables by nutritionists.",
                    "evidence_passages": [
                        {
                            "text": "Tomatoes are fruits that are considered vegetables by nutritionists.",
                            "score": 0.82,
                        }
                    ],
                },
                {
                    "id": "S3",
                    "title": "Botany explainer",
                    "url": "https://example.com/tomato-botany",
                    "domain": "example.com",
                    "published_label": "2026-03-18",
                    "authority_score": 0.58,
                    "relevance_score": 0.73,
                    "overall_score": 0.76,
                    "published_date": "2026-03-18",
                    "snippet": "Tomatoes are botanically fruits because they form from a flower and contain seeds.",
                    "evidence_passages": [
                        {
                            "text": "Tomatoes are botanically fruits because they form from a flower and contain seeds.",
                            "score": 0.8,
                        }
                    ],
                },
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 3},
            "error": None,
        }
        llm = _QueuedVerifierLLM(
            [
                '{"reasoning":"The evidence is nuanced.","claim_requires_recency":false,"risk_flags":[],"source_assessments":[{"source_id":"S1","stance":"IRRELEVANT","strength":0.4,"summary":"Does not directly address the claim.","snippet_used":"While the portion eaten is botanically a fruit, tomatoes are considered a vegetable due to their savory flavor."},{"source_id":"S2","stance":"MIXED","strength":0.8,"summary":"States tomatoes can be treated as vegetables in nutrition contexts.","snippet_used":"Tomatoes are fruits that are considered vegetables by nutritionists."},{"source_id":"S3","stance":"CONFLICT","strength":0.78,"summary":"States tomatoes are botanically fruits.","snippet_used":"Tomatoes are botanically fruits because they form from a flower and contain seeds."}]}',
                '{"correction_needed": false, "suggested_verdict": "PARTIALLY_TRUE", "reasoning": ""}',
            ]
        )

        with patch("pipeline.verifier.llm", new=llm):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(result["verdict"], "PARTIALLY_TRUE")
        stances = {
            item["source_id"]: item["stance"]
            for item in result["base_source_assessments"]
        }
        self.assertEqual(stances["S1"], "MIXED")
        self.assertIn("scope mismatch", result["conflict_summary"]["drivers"])
        self.assertNotEqual(result["conflict_summary"]["summary"], "")

    def test_verify_claim_cross_checks_llm_against_heuristics_per_source(self) -> None:
        claim = {
            "id": "1",
            "claim": "Mars has 2 moons.",
            "claim_type": "numeric",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "Astronomy note",
                    "url": "https://example.org/mars-note",
                    "domain": "example.org",
                    "published_label": "2026-03-19",
                    "authority_score": 0.82,
                    "relevance_score": 0.78,
                    "overall_score": 0.8,
                    "published_date": "2026-03-19",
                    "snippet": "Mars has 1 moon.",
                    "evidence_passages": [
                        {
                            "text": "Mars has 1 moon.",
                            "score": 0.84,
                        }
                    ],
                }
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 1},
            "error": None,
        }
        llm = _QueuedVerifierLLM(
            [
                '{"reasoning":"The source supports the claim.","claim_requires_recency":false,"risk_flags":[],"source_assessments":[{"source_id":"S1","stance":"SUPPORT","strength":0.9,"summary":"Supports the claim.","snippet_used":"Mars has 1 moon."}]}',
                '{"correction_needed": false, "suggested_verdict": "UNVERIFIABLE", "reasoning": ""}',
            ]
        )

        with patch("pipeline.verifier.llm", new=llm):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(
            next(
                item["stance"]
                for item in result["base_source_assessments"]
                if item["source_id"] == "S1"
            ),
            "MIXED",
        )
        self.assertLess(result["confidence_breakdown"]["cross_check_agreement"], 1.0)
        self.assertTrue(
            any(
                "LLM and heuristic source assessment disagreed" in flag
                for flag in result["risk_flags"]
            )
        )

    def test_verify_claim_blocks_reflection_from_forcing_false_without_direct_evidence(self) -> None:
        claim = {
            "id": "1",
            "claim": "Berlin is in Spain.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "Berlin - Wikipedia",
                    "url": "https://en.wikipedia.org/wiki/Berlin",
                    "domain": "en.wikipedia.org",
                    "published_label": "unknown",
                    "authority_score": 0.74,
                    "relevance_score": 0.76,
                    "overall_score": 0.73,
                    "published_date": "unknown",
                    "snippet": "Friedrichstrasse was Berlin's legendary street during the Golden Twenties.",
                    "evidence_passages": [
                        {
                            "text": "Friedrichstrasse was Berlin's legendary street during the Golden Twenties.",
                            "score": 0.54,
                        }
                    ],
                },
                {
                    "id": "S2",
                    "title": "Money Heist spinoff",
                    "url": "https://example.com/berlin-series",
                    "domain": "example.com",
                    "published_label": "unknown",
                    "authority_score": 0.55,
                    "relevance_score": 0.58,
                    "overall_score": 0.56,
                    "published_date": "unknown",
                    "snippet": "The series Berlin will be set in Paris and Spain.",
                    "evidence_passages": [
                        {
                            "text": "The series Berlin will be set in Paris and Spain.",
                            "score": 0.57,
                        }
                    ],
                },
                {
                    "id": "S3",
                    "title": "Travel demand report",
                    "url": "https://example.net/travel-demand",
                    "domain": "example.net",
                    "published_label": "unknown",
                    "authority_score": 0.55,
                    "relevance_score": 0.58,
                    "overall_score": 0.56,
                    "published_date": "unknown",
                    "snippet": "Spain is one of the countries with the highest demand for flights to Berlin.",
                    "evidence_passages": [
                        {
                            "text": "Spain is one of the countries with the highest demand for flights to Berlin.",
                            "score": 0.55,
                        }
                    ],
                },
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 3},
            "error": None,
        }
        llm = _QueuedVerifierLLM(
            [
                '{"reasoning":"The evidence is mixed.","claim_requires_recency":false,"risk_flags":[],"source_assessments":[{"source_id":"S1","stance":"CONFLICT","strength":0.74,"summary":"Provides information about Berlin.","snippet_used":"Friedrichstrasse was Berlin\\u0027s legendary street during the Golden Twenties."},{"source_id":"S2","stance":"MIXED","strength":0.55,"summary":"Mentions Berlin and Spain.","snippet_used":"The series Berlin will be set in Paris and Spain."},{"source_id":"S3","stance":"MIXED","strength":0.55,"summary":"Mentions Berlin in relation to Spain.","snippet_used":"Spain is one of the countries with the highest demand for flights to Berlin."}]}',
                '{"correction_needed": true, "suggested_verdict": "FALSE", "reasoning": "Berlin is not in Spain."}',
            ]
        )

        with patch("pipeline.verifier.llm", new=llm):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(result["verdict"], "UNVERIFIABLE")
        self.assertTrue(
            any(
                "suggested FALSE" in flag
                for flag in result["risk_flags"]
            )
        )

    def test_verify_claim_falls_back_to_heuristics_when_model_fails(self) -> None:
        claim = {
            "id": "1",
            "claim": "Mars has two moons named Phobos and Deimos.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        evidence = {
            "claim_id": "1",
            "sources": [
                {
                    "id": "S1",
                    "title": "Mars facts",
                    "url": "https://science.example/mars-facts",
                    "domain": "science.example",
                    "published_label": "2026-03-20",
                    "authority_score": 0.82,
                    "relevance_score": 0.86,
                    "overall_score": 0.82,
                    "published_date": "2026-03-20",
                    "snippet": "Mars has two moons named Phobos and Deimos.",
                    "evidence_passages": [
                        {"text": "Mars has two moons named Phobos and Deimos.", "score": 0.9}
                    ],
                },
                {
                    "id": "S2",
                    "title": "Planetary overview",
                    "url": "https://space.example/mars-overview",
                    "domain": "space.example",
                    "published_label": "2026-03-19",
                    "authority_score": 0.78,
                    "relevance_score": 0.84,
                    "overall_score": 0.8,
                    "published_date": "2026-03-19",
                    "snippet": "The two moons of Mars are Phobos and Deimos.",
                    "evidence_passages": [
                        {"text": "The two moons of Mars are Phobos and Deimos.", "score": 0.82}
                    ],
                },
            ],
            "query_variants": [],
            "retrieval_summary": {"source_count": 2},
            "error": None,
        }

        with patch("pipeline.verifier.llm", new=_FailingVerifierLLM()):
            result = asyncio.run(verify_claim(claim, evidence))

        self.assertEqual(result["verdict"], "TRUE")
        self.assertTrue(
            any("heuristic source assessment" in flag for flag in result["risk_flags"])
        )
        self.assertEqual(len(result["base_source_assessments"]), 2)


if __name__ == "__main__":
    unittest.main()
