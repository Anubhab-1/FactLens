from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pipeline.retriever as retriever


class _FakeSearchTool:
    def __init__(self, responses: dict[str, list[dict]]) -> None:
        self.responses = responses

    async def ainvoke(self, payload: dict) -> list[dict]:
        return self.responses.get(payload["query"], [])


class _StringSearchTool:
    def __init__(self, message: str) -> None:
        self.message = message

    async def ainvoke(self, _payload: dict) -> str:
        return self.message


class _QueuedLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    async def ainvoke(self, _messages):
        if not self.responses:
            raise AssertionError("No queued planner responses remain.")
        return SimpleNamespace(content=self.responses.pop(0))


class _SerializedLLM:
    def __init__(self) -> None:
        self.inflight = 0
        self.max_inflight = 0

    async def ainvoke(self, messages):
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            if self.inflight > 1:
                raise AssertionError("LLM ainvoke was entered concurrently.")
            await asyncio.sleep(0.01)
            claim_line = str(messages[-1].content).splitlines()[0]
            claim_text = claim_line.split("Claim:", 1)[1].strip()
            return SimpleNamespace(
                content=json.dumps([{"query": claim_text, "objective": "direct"}])
            )
        finally:
            self.inflight -= 1


def _claim() -> dict:
    return {
        "id": "1",
        "claim": "The city approved an $18 million budget in 2026.",
        "claim_type": "numeric",
        "time_sensitive": True,
    }


def _poor_primary_result() -> list[dict]:
    return [
        {
            "url": "https://rumor.example/post",
            "title": "Forum recap",
            "raw_content": (
                "Unofficial forum recap of the 2026 city budget debate. "
                "Commenters mentioned an 18 million dollar proposal, but the post did not confirm whether it was approved."
            ),
            "published_date": "2026-03-01",
        }
    ]


def _strong_recovery_result() -> list[dict]:
    return [
        {
            "url": "https://records.example/budget-2026",
            "title": "2026 city budget approval",
            "raw_content": (
                "The city council approved the 2026 budget at 18 million dollars. "
                "The official vote record confirms the amount."
            ),
            "published_date": "2026-03-22",
        }
    ]


class RetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        retriever._search_provider_failures.clear()
        retriever._search_provider_last_failure.clear()
        retriever._search_provider_circuit_open.clear()

    def test_serper_search_sync_builds_grounded_results(self) -> None:
        response = {
            "organic": [
                {
                    "title": "Paris - Wikipedia",
                    "link": "https://en.wikipedia.org/wiki/Paris",
                    "snippet": (
                        "Paris is the capital and most populous city of France. "
                        "It is a major European city and a center of art, fashion, gastronomy, and culture."
                    ),
                    "date": "2026-03-20",
                }
            ]
        }

        with patch.object(retriever, "SERPER_API_KEY", new="test-key"):
            with patch.object(retriever, "_http_post_json", return_value=response):
                with patch.object(retriever, "_fetch_fallback_result", return_value=None):
                    results = retriever._serper_search_sync("Paris capital of France", max_results=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://en.wikipedia.org/wiki/Paris")
        self.assertIn("capital and most populous city of France", results[0]["raw_content"])
        self.assertEqual(results[0]["published_date"], "2026-03-20")

    def test_wikipedia_search_sync_builds_grounded_results(self) -> None:
        responses = [
            {
                "query": {
                    "search": [
                        {
                            "title": "Paris",
                            "timestamp": "2026-03-20T00:00:00Z",
                        }
                    ]
                }
            },
            {
                "query": {
                    "pages": [
                        {
                            "title": "Paris",
                            "fullurl": "https://en.wikipedia.org/wiki/Paris",
                            "extract": (
                                "Paris is the capital and largest city of France. "
                                "It is a major European city and a center of art, fashion, gastronomy, and culture."
                            ),
                            "revisions": [{"timestamp": "2026-03-20T00:00:00Z"}],
                        }
                    ]
                }
            },
        ]

        with patch.object(retriever, "_http_get_json", side_effect=responses):
            results = retriever._wikipedia_search_sync("Paris capital of France", max_results=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://en.wikipedia.org/wiki/Paris")
        self.assertIn("capital and largest city of France", results[0]["raw_content"])
        self.assertEqual(results[0]["published_date"], "2026-03-20")

    def test_build_search_api_result_passes_published_date_hint_to_fallback_fetch(self) -> None:
        with patch.object(
            retriever,
            "_fetch_fallback_result",
            return_value={
                "url": "https://example.org/page",
                "title": "Example page",
                "raw_content": "Fetched content",
                "published_date": "2026-03-20",
            },
        ) as fallback_fetch:
            result = retriever._build_search_api_result(
                "https://example.org/page",
                "Example page",
                "Snippet text",
                published_date="2026-03-20",
            )

        fallback_fetch.assert_called_once_with(
            "https://example.org/page",
            "Example page",
            "Snippet text",
            published_date_hint="2026-03-20",
        )
        self.assertEqual(result["published_date"], "2026-03-20")

    def test_search_query_provider_attempts_uses_wikipedia_when_other_search_is_unavailable(self) -> None:
        async def run_attempts():
            with patch.object(
                retriever,
                "search_tool",
                new=_StringSearchTool("plan limit reached"),
            ):
                with patch.object(retriever, "_search_with_wikipedia", return_value=_strong_recovery_result()):
                    with patch.object(retriever, "_search_with_duckduckgo", return_value=[]):
                        with patch.object(retriever, "_search_with_bing", return_value=[]):
                            return await retriever._search_query_provider_attempts("Paris capital of France")

        attempts = asyncio.run(run_attempts())

        self.assertTrue(any(attempt["provider"] == "wikipedia" for attempt in attempts))
        wikipedia_attempt = next(attempt for attempt in attempts if attempt["provider"] == "wikipedia")
        self.assertEqual(len(wikipedia_attempt["results"]), 1)
        self.assertTrue(wikipedia_attempt["fallback_used"])

    def test_search_query_provider_attempts_uses_serper_when_configured(self) -> None:
        async def run_attempts():
            with patch.object(retriever, "search_tool", new=None):
                with patch.object(retriever, "SERPER_API_KEY", new="test-key"):
                    with patch.object(retriever, "SERPAPI_API_KEY", new=""):
                        with patch.object(retriever, "_search_with_serper", return_value=_strong_recovery_result()):
                            with patch.object(retriever, "_search_with_wikipedia", return_value=[]):
                                with patch.object(retriever, "_search_with_duckduckgo", return_value=[]):
                                    with patch.object(retriever, "_search_with_bing", return_value=[]):
                                        return await retriever._search_query_provider_attempts("Paris capital of France")

        attempts = asyncio.run(run_attempts())

        self.assertTrue(any(attempt["provider"] == "serper" for attempt in attempts))
        serper_attempt = next(attempt for attempt in attempts if attempt["provider"] == "serper")
        self.assertEqual(len(serper_attempt["results"]), 1)
        self.assertTrue(serper_attempt["fallback_used"])

    def test_build_source_context_queries_uses_source_url_slug(self) -> None:
        claim = {
            "id": "1",
            "claim": "Iran has introduced a safe shipping corridor in the Strait of Hormuz.",
            "claim_type": "entity",
            "time_sensitive": True,
            "source_url": "https://timesofindia.indiatimes.com/business/international-business/an-alternative-route-to-strait-of-hormuz-iran-sets-up-corridor-offers-ships-safe-passage-for-a-price/articleshow/129696419.cms",
            "source_text": (
                "Iran has introduced a 'safe shipping corridor' in the Strait of Hormuz. "
                "According to maritime news agency Lloyd's List, operators are seeking safe passage."
            ),
        }

        queries = retriever._build_source_context_queries(claim, phase="primary")

        self.assertTrue(queries)
        self.assertTrue(any("an alternative route to strait of hormuz" in query["query"].lower() for query in queries))
        self.assertTrue(any("safe shipping corridor" in query["query"].lower() for query in queries))
        self.assertTrue(any("site:lloydslist.com" in query["query"].lower() for query in queries))
        self.assertTrue(any(query["objective"] == "authoritative" for query in queries))

    def test_build_source_context_queries_use_named_phrases_for_ship_claims(self) -> None:
        claim = {
            "id": "7",
            "claim": (
                "Three India-flagged gas tankers Shivalik, Nanda Devi and Jag Laadki "
                "have successfully transited the strait."
            ),
            "context": (
                "Among them, three India-flagged gas tankers Shivalik, Nanda Devi and Jag Laadki "
                "have successfully transited the strait and arrived in India after taking this route."
            ),
            "claim_type": "entity",
            "time_sensitive": True,
            "source_url": "https://timesofindia.indiatimes.com/business/international-business/an-alternative-route-to-strait-of-hormuz-iran-sets-up-corridor-offers-ships-safe-passage-for-a-price/articleshow/129696419.cms",
        }

        queries = retriever._build_source_context_queries(claim, phase="recovery")

        self.assertTrue(any("nanda devi" in query["query"].lower() for query in queries))
        self.assertTrue(any("jag laadki" in query["query"].lower() for query in queries))

    def test_extract_result_url_ignores_duckduckgo_tracker_links(self) -> None:
        url = retriever._extract_result_url(
            "/y.js?ad_domain=guestreservations.com&ad_provider=bingv7aa"
        )

        self.assertEqual(url, "")

    def test_build_search_api_result_uses_snippet_when_fetch_fails(self) -> None:
        snippet = (
            "The Strait of Hormuz is the world's most important oil transit chokepoint, "
            "according to the U.S. Energy Information Administration."
        )

        with patch.object(retriever, "_fetch_fallback_result", return_value=None):
            result = retriever._build_search_api_result(
                "https://www.eia.gov/todayinenergy/detail.php?id=61024",
                "World oil transit chokepoints",
                snippet,
                published_date="2024-06-25",
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["raw_content"], snippet)
        self.assertEqual(result["published_date"], "2024-06-25")

    def test_result_matches_query_constraints_requires_matching_domain(self) -> None:
        query = {
            "query": "site:eia.gov OR site:energy.gov Strait of Hormuz oil chokepoint",
            "objective": "authoritative",
            "phase": "primary",
            "planner": "heuristic",
        }

        self.assertTrue(
            retriever._result_matches_query_constraints(
                {"url": "https://www.eia.gov/todayinenergy/detail.php?id=61024"},
                query,
            )
        )
        self.assertFalse(
            retriever._result_matches_query_constraints(
                {"url": "https://www.zhihu.com/question/1908108790345241497"},
                query,
            )
        )

    def test_select_query_mix_preserves_claim_specific_authoritative_query(self) -> None:
        claim_specific = [
            {
                "query": 'site:nasa.gov Earth only natural satellite Moon',
                "objective": "authoritative",
                "phase": "primary",
                "planner": "heuristic",
            },
            {
                "query": '"Earth has one natural satellite" moon',
                "objective": "direct",
                "phase": "primary",
                "planner": "heuristic",
            },
            {
                "query": '"Earth one moon natural satellite"',
                "objective": "direct",
                "phase": "primary",
                "planner": "heuristic",
            },
        ]
        generated = [
            {
                "query": "Earth natural satellite",
                "objective": "direct",
                "phase": "primary",
                "planner": "llm",
            },
            {
                "query": "Earth natural satellite discovery recent findings",
                "objective": "recency",
                "phase": "primary",
                "planner": "llm",
            },
            {
                "query": "site:nasa.gov site:esa.int Earth natural satellite",
                "objective": "authoritative",
                "phase": "primary",
                "planner": "llm",
            },
        ]

        selected = retriever._select_query_mix(claim_specific, generated)

        self.assertEqual(len(selected), 4)
        self.assertTrue(
            any(query["query"] == 'site:nasa.gov Earth only natural satellite Moon' for query in selected)
        )
        self.assertTrue(any(query["objective"] == "recency" for query in selected))

    def test_fetch_fallback_result_discards_binary_pdf_content(self) -> None:
        with patch.object(
            retriever,
            "_http_get",
            return_value="%PDF-1.6\n1771 0 obj\nstream\nbinary payload\nendobj\n%%EOF",
        ):
            result = retriever._fetch_fallback_result(
                "https://example.edu/document.pdf",
                "PDF Presentation",
                "Periodic table PDF",
            )

        self.assertIsNone(result)

    def test_focus_content_for_claim_finds_relevant_window_late_in_long_page(self) -> None:
        claim = "Paris is the capital of France."
        long_content = (
            ("Navigation menu About Contact Subscribe " * 90)
            + "Paris is the capital city of France and serves as its political center. "
            + ("Related links and footer content " * 60)
        )

        focused = retriever._focus_content_for_claim(claim, long_content, title="Paris article")

        self.assertIn("capital city of France", focused)
        self.assertNotEqual(focused[:120], long_content[:120])

    def test_generate_queries_serializes_llm_calls_across_claims(self) -> None:
        llm = _SerializedLLM()
        claim_one = {
            "id": "1",
            "claim": "Paris is the capital of France.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        claim_two = {
            "id": "2",
            "claim": "The chemical symbol for gold is Au.",
            "claim_type": "entity",
            "time_sensitive": False,
        }

        async def run_both():
            return await asyncio.gather(
                retriever._generate_queries(claim_one),
                retriever._generate_queries(claim_two),
            )

        with patch.object(retriever, "llm", new=llm):
            query_sets = asyncio.run(run_both())

        self.assertEqual(llm.max_inflight, 1)
        self.assertTrue(
            any("capital of france" in query["query"].lower() for query in query_sets[0])
        )
        self.assertTrue(any("gold" in query["query"].lower() for query in query_sets[1]))

    def test_build_claim_specific_queries_targets_known_fact_patterns(self) -> None:
        gold_queries = retriever._build_claim_specific_queries(
            {
                "id": "1",
                "claim": "The chemical symbol for gold is Au.",
                "claim_type": "entity",
                "time_sensitive": False,
            }
        )
        earth_queries = retriever._build_claim_specific_queries(
            {
                "id": "2",
                "claim": "Earth has one natural satellite, the Moon.",
                "claim_type": "entity",
                "time_sensitive": False,
            }
        )
        pacific_queries = retriever._build_claim_specific_queries(
            {
                "id": "3",
                "claim": "The Pacific Ocean is the largest ocean on Earth.",
                "claim_type": "comparison",
                "time_sensitive": False,
            }
        )
        hormuz_queries = retriever._build_claim_specific_queries(
            {
                "id": "4",
                "claim": "The Strait of Hormuz is one of the world's busiest oil chokepoints.",
                "claim_type": "entity",
                "time_sensitive": False,
            }
        )
        leadership_queries = retriever._build_claim_specific_queries(
            {
                "id": "5",
                "claim": "The current CEO of ExampleCorp is Jane Doe.",
                "claim_type": "entity",
                "time_sensitive": True,
            }
        )
        location_queries = retriever._build_claim_specific_queries(
            {
                "id": "6",
                "claim": "Berlin is in Spain.",
                "claim_type": "entity",
                "time_sensitive": False,
            }
        )

        self.assertTrue(any("nist.gov" in query["query"] for query in gold_queries))
        self.assertTrue(any("site:nasa.gov" in query["query"] for query in earth_queries))
        self.assertTrue(any("site:noaa.gov" in query["query"] for query in pacific_queries))
        self.assertTrue(any("site:eia.gov" in query["query"] for query in hormuz_queries))
        self.assertTrue(any("official ceo leadership" in query["query"].lower() for query in leadership_queries))
        self.assertTrue(any('"Berlin" capital city country' in query["query"] for query in location_queries))
        self.assertTrue(
            any(
                query["objective"] == "authoritative"
                and "site:britannica.com OR site:wikipedia.org" in query["query"]
                for query in location_queries
            )
        )

    def test_build_source_record_drops_ambiguous_google_earth_result(self) -> None:
        claim = {
            "id": "1",
            "claim": "Earth has one natural satellite, the Moon.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        result = {
            "url": "https://support.google.com/earth/community-guide/256123000/versions-of-google-earth-desktop-web-mobile?hl=en",
            "title": "Versions of Google Earth (desktop, web, mobile)",
            "raw_content": (
                "Versions of Google Earth (desktop, web, mobile) - Google Earth Community. "
                "Google Earth Help Center. Learn how to use Google Earth on desktop and mobile."
            ),
            "published_date": "unknown",
        }
        query = {
            "query": "Earth natural satellite",
            "objective": "direct",
            "phase": "primary",
            "planner": "llm",
        }

        source = retriever._build_source_record(claim, result, query)

        self.assertIsNone(source)

    def test_build_source_record_drops_generic_ocean_page_without_claim_match(self) -> None:
        claim = {
            "id": "1",
            "claim": "The Pacific Ocean is the largest ocean on Earth.",
            "claim_type": "comparison",
            "time_sensitive": False,
        }
        result = {
            "url": "https://oceanexplorer.noaa.gov/ocean-fact/explored/",
            "title": "How much of the ocean has been explored?",
            "raw_content": (
                "The ocean covers approximately 70% of Earth's surface. "
                "It is the largest livable space on the planet, but this page only discusses the ocean in general."
            ),
            "published_date": "2026-01-27",
        }
        query = {
            "query": "largest ocean recent studies OR largest ocean updated facts",
            "objective": "recency",
            "phase": "primary",
            "planner": "llm",
        }

        source = retriever._build_source_record(claim, result, query)

        self.assertIsNone(source)

    def test_build_source_record_tags_first_party_company_pages(self) -> None:
        claim = {
            "id": "1",
            "claim": "The current CEO of ExampleCorp is Jane Doe.",
            "claim_type": "entity",
            "time_sensitive": True,
        }
        result = {
            "url": "https://example.com/leadership",
            "title": "Leadership team",
            "raw_content": "Jane Doe is the current CEO of ExampleCorp as of March 2026.",
            "published_date": "2026-03-15",
        }
        query = {
            "query": "\"ExampleCorp\" official CEO leadership",
            "objective": "authoritative",
            "phase": "primary",
            "planner": "heuristic",
        }

        source = retriever._build_source_record(claim, result, query)

        self.assertIsNotNone(source)
        self.assertEqual(source["source_origin"], "first_party")
        self.assertTrue(source["primary_preferred"])
        self.assertEqual(source["independence_key"], "example.com")

    def test_build_claim_specific_queries_adds_known_entity_alias_variants(self) -> None:
        queries = retriever._build_claim_specific_queries(
            {
                "id": "1",
                "claim": "WHO declared mpox a public health emergency of international concern.",
                "claim_type": "entity",
                "time_sensitive": True,
            }
        )

        self.assertTrue(
            any("World Health Organization" in query["query"] for query in queries)
        )
        self.assertTrue(any(query["objective"] == "recency" for query in queries))

    def test_select_diverse_sources_demotes_social_results_for_plain_fact_claims(self) -> None:
        claim = {
            "id": "1",
            "claim": "Berlin is in Spain.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        selected = retriever._select_diverse_sources(
            claim,
            [
                {
                    "id": "S1",
                    "url": "https://www.youtube.com/watch?v=demo",
                    "domain": "youtube.com",
                    "source_type": "social",
                    "source_origin": "social",
                    "source_origin_score": 0.3,
                    "primary_preferred": False,
                    "published_label": "unknown",
                    "overall_score": 0.94,
                    "authority_score": 0.22,
                    "relevance_score": 0.91,
                    "recency_score": 0.45,
                    "independence_key": "youtube.com",
                    "source_intelligence": {},
                },
                {
                    "id": "S2",
                    "url": "https://en.wikipedia.org/wiki/Berlin",
                    "domain": "en.wikipedia.org",
                    "source_type": "reference",
                    "source_origin": "reference",
                    "source_origin_score": 0.8,
                    "primary_preferred": True,
                    "published_label": "unknown",
                    "overall_score": 0.73,
                    "authority_score": 0.74,
                    "relevance_score": 0.76,
                    "recency_score": 0.45,
                    "independence_key": "wikipedia",
                    "source_intelligence": {},
                },
            ],
            max_sources=1,
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["id"], "S2")

    def test_retrieve_evidence_seeds_source_article_for_url_claim(self) -> None:
        claim = {
            "id": "1",
            "claim": "The corridor is being offered only to ships that receive prior approval from Iranian authorities.",
            "claim_type": "entity",
            "time_sensitive": True,
            "source_url": "https://example.com/news/iran-sets-up-corridor-offers-ships-safe-passage-for-a-price",
            "source_text": (
                "Iran has introduced a safe shipping corridor. "
                "The corridor is being offered only to ships that receive prior approval from Iranian authorities."
            ),
        }

        async def fake_generate_queries(_claim: dict) -> list[dict]:
            return []

        async def fake_plan_recovery_queries(*_args, **_kwargs):
            return [], {
                "mode": "not_needed",
                "reasoning": "",
                "fallback_used": False,
            }

        with patch.object(retriever, "_generate_queries", new=fake_generate_queries):
            with patch.object(retriever, "_plan_recovery_queries", new=fake_plan_recovery_queries):
                result = asyncio.run(retriever.retrieve_evidence(claim))

        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0]["url"], claim["source_url"])
        self.assertEqual(result["sources"][0]["query_phase"], "source")

    def test_execute_query_batch_tries_next_provider_when_first_provider_adds_no_sources(self) -> None:
        claim = {
            "id": "9",
            "claim": "The Strait of Hormuz is one of the world's busiest oil chokepoints.",
            "claim_type": "entity",
            "time_sensitive": False,
        }
        queries = [
            {
                "query": "site:eia.gov Strait of Hormuz oil chokepoint",
                "objective": "authoritative",
                "phase": "primary",
                "planner": "heuristic",
            }
        ]
        candidate_sources = {}

        async def fake_attempts(*_args, **_kwargs) -> list[dict]:
            return [
                {
                    "provider": "tavily",
                    "results": [
                        {
                            "url": "https://www.zhihu.com/question/1908108790345241497",
                            "title": "SAFE product question",
                            "raw_content": "SAFE agreements and product forums unrelated to shipping or oil chokepoints.",
                            "published_date": "unknown",
                        }
                    ],
                    "fallback_used": False,
                    "warning": None,
                    "error": None,
                },
                {
                    "provider": "google_cse",
                    "results": [
                        {
                            "url": "https://www.eia.gov/todayinenergy/detail.php?id=61024",
                            "title": "World oil transit chokepoints",
                            "raw_content": (
                                "The Strait of Hormuz is one of the world's busiest oil chokepoints, "
                                "with large volumes of petroleum liquids moving through it each day."
                            ),
                            "published_date": "2024-06-25",
                        }
                    ],
                    "fallback_used": True,
                    "warning": "tavily returned no usable sources.",
                    "error": None,
                },
            ]

        with patch.object(retriever, "_search_query_provider_attempts", new=fake_attempts):
            query_errors, empty_authoritative_queries = asyncio.run(
                retriever._execute_query_batch(claim, queries, candidate_sources)
            )

        self.assertFalse(query_errors)
        self.assertFalse(empty_authoritative_queries)
        self.assertEqual(queries[0]["provider"], "google_cse")
        self.assertEqual(queries[0]["added_source_count"], 1)
        self.assertEqual(len(queries[0]["provider_attempts"]), 2)
        self.assertEqual(len(candidate_sources), 1)

    def test_retrieve_evidence_uses_llm_planned_recovery_queries(self) -> None:
        claim = _claim()
        llm = _QueuedLLM(
            [
                json.dumps(
                    {
                        "decision": "search",
                        "reasoning": "The first pass lacks an authoritative dated source.",
                        "queries": [
                            {
                                "query": "city approved 18 million budget 2026 official record",
                                "objective": "authoritative",
                            }
                        ],
                    }
                )
            ]
        )
        search_tool = _FakeSearchTool(
            {
                claim["claim"]: _poor_primary_result(),
                "city approved 18 million budget 2026 official record": _strong_recovery_result(),
            }
        )

        async def fake_generate_queries(_claim: dict) -> list[dict]:
            return [
                {
                    "query": claim["claim"],
                    "objective": "direct",
                    "phase": "primary",
                    "planner": "llm",
                }
            ]

        with patch.object(retriever, "_generate_queries", new=fake_generate_queries):
            with patch.object(retriever, "search_tool", new=search_tool):
                with patch.object(retriever, "llm", new=llm):
                    with patch.object(
                        retriever,
                        "llm_descriptor",
                        new=SimpleNamespace(issue=None),
                    ):
                        with patch.object(retriever, "_search_with_duckduckgo", return_value=[]):
                            with patch.object(retriever, "_search_with_bing", return_value=[]):
                                result = asyncio.run(retriever.retrieve_evidence(claim))

        self.assertTrue(result["retrieval_summary"]["recovery_triggered"])
        self.assertIn(
            result["retrieval_summary"]["recovery_strategy"],
            {"llm_planner", "heuristic_after_llm"},
        )
        self.assertTrue(result["retrieval_summary"]["recovery_planner_notes"])
        self.assertTrue(
            any(
                query["phase"] == "recovery" and query["planner"] == "llm"
                for query in result["query_variants"]
            )
        )
        self.assertGreaterEqual(len(result["sources"]), 1)

    def test_retrieve_evidence_falls_back_to_heuristic_recovery_when_planner_fails(self) -> None:
        claim = _claim()
        llm = _QueuedLLM(["not valid json"])
        heuristic_query = f"{claim['claim']} official statistics report dataset"
        search_tool = _FakeSearchTool(
            {
                claim["claim"]: _poor_primary_result(),
                heuristic_query: _strong_recovery_result(),
            }
        )

        async def fake_generate_queries(_claim: dict) -> list[dict]:
            return [
                {
                    "query": claim["claim"],
                    "objective": "direct",
                    "phase": "primary",
                    "planner": "llm",
                }
            ]

        with patch.object(retriever, "_generate_queries", new=fake_generate_queries):
            with patch.object(retriever, "search_tool", new=search_tool):
                with patch.object(retriever, "llm", new=llm):
                    with patch.object(
                        retriever,
                        "llm_descriptor",
                        new=SimpleNamespace(issue=None),
                    ):
                        with patch.object(retriever, "_search_with_duckduckgo", return_value=[]):
                            with patch.object(retriever, "_search_with_bing", return_value=[]):
                                result = asyncio.run(retriever.retrieve_evidence(claim))

        self.assertTrue(result["retrieval_summary"]["recovery_triggered"])
        self.assertEqual(result["retrieval_summary"]["recovery_strategy"], "heuristic_fallback")
        self.assertTrue(result["retrieval_summary"]["recovery_fallback_used"])
        self.assertEqual(result["query_variants"][-1]["planner"], "heuristic")
        self.assertEqual(result["query_variants"][-1]["phase"], "recovery")
        self.assertGreaterEqual(len(result["sources"]), 1)

    def test_retrieve_evidence_surfaces_string_search_errors(self) -> None:
        claim = _claim()

        async def fake_generate_queries(_claim: dict) -> list[dict]:
            return [
                {
                    "query": claim["claim"],
                    "objective": "direct",
                    "phase": "primary",
                    "planner": "llm",
                }
            ]

        with patch.object(retriever, "_generate_queries", new=fake_generate_queries):
            with patch.object(
                retriever,
                "search_tool",
                new=_StringSearchTool("HTTPError('432 Client Error')"),
            ):
                with patch.object(
                    retriever,
                    "_search_with_duckduckgo",
                    side_effect=RuntimeError("DuckDuckGo unavailable"),
                ):
                    with patch.object(
                        retriever,
                        "_search_with_wikipedia",
                        side_effect=RuntimeError("Wikipedia unavailable"),
                    ):
                        with patch.object(
                            retriever,
                            "_search_with_bing",
                            side_effect=RuntimeError("Bing unavailable"),
                        ):
                            result = asyncio.run(retriever.retrieve_evidence(claim))

        self.assertEqual(result["sources"], [])
        self.assertIn("432 Client Error", result["error"])
        self.assertEqual(result["query_variants"][0]["status"], "error")

    def test_retrieve_evidence_falls_back_to_bing_when_other_providers_fail(self) -> None:
        claim = _claim()

        async def fake_generate_queries(_claim: dict) -> list[dict]:
            return [
                {
                    "query": claim["claim"],
                    "objective": "direct",
                    "phase": "primary",
                    "planner": "llm",
                }
            ]

        with patch.object(retriever, "_generate_queries", new=fake_generate_queries):
            with patch.object(
                retriever,
                "search_tool",
                new=_StringSearchTool("HTTPError('432 Client Error')"),
            ):
                with patch.object(
                    retriever,
                    "_search_with_duckduckgo",
                    side_effect=RuntimeError("DuckDuckGo unavailable"),
                ):
                    with patch.object(
                        retriever,
                        "_search_with_wikipedia",
                        return_value=[],
                    ):
                        with patch.object(
                            retriever,
                            "_search_with_bing",
                            return_value=_strong_recovery_result(),
                        ):
                            result = asyncio.run(retriever.retrieve_evidence(claim))

        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["query_variants"][0]["status"], "ok")
        self.assertEqual(result["query_variants"][0]["provider"], "bing_html")
        self.assertTrue(result["query_variants"][0]["fallback_used"])
        self.assertIn("432 Client Error", result["query_variants"][0]["warning"])


if __name__ == "__main__":
    unittest.main()
