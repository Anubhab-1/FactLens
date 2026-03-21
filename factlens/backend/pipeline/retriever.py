from __future__ import annotations

import ast
import json
import os
from datetime import datetime
from pathlib import Path
import re

from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from pipeline.scoring import (
    classify_source_type,
    compute_overall_source_score,
    compute_recency_score,
    compute_relevance_score,
    domain_authority_score,
    extract_best_snippet,
    extract_domain,
    format_date_label,
    normalize_url,
    summarize_retrieval,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


llm = (
    ChatNVIDIA(
        model="meta/llama-3.1-70b-instruct",
        api_key=os.getenv("NVIDIA_API_KEY"),
        temperature=0.1,
        max_tokens=2048,
    )
    if os.getenv("NVIDIA_API_KEY")
    else None
)

search_tool = (
    TavilySearchResults(
        max_results=4,
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
        include_raw_content=True,
        search_depth="advanced",
    )
    if os.getenv("TAVILY_API_KEY")
    else None
)

QUERY_SYSTEM_PROMPT = """You are a search strategist for a fact-checking engine.
Given a single claim, produce 3 complementary web search queries:
1. A direct query that restates the claim.
2. An authoritative-source query that prefers official or high-credibility sources.
3. A context or recency query that is good at surfacing contradictory or updated evidence.

Return ONLY a JSON array in this format:
[
  {"query": "search terms", "objective": "direct|authoritative|recency"}
]"""


def _parse_json_array(raw_text: str) -> list[dict]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    match = re.search(r"\[[\s\S]*\]", cleaned)
    if match:
        cleaned = match.group(0)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        normalized = re.sub(r"\btrue\b", "True", cleaned, flags=re.IGNORECASE)
        normalized = re.sub(r"\bfalse\b", "False", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bnull\b", "None", normalized, flags=re.IGNORECASE)
        try:
            parsed = ast.literal_eval(normalized)
        except (SyntaxError, ValueError) as exc:
            raise ValueError("Could not parse retriever response.") from exc

    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array.")
    return parsed


def _fallback_queries(claim: dict) -> list[dict]:
    claim_text = claim["claim"].strip()
    current_year = datetime.utcnow().year
    fallback_queries = [
        {"query": claim_text, "objective": "direct"},
        {"query": f'"{claim_text}" official source', "objective": "authoritative"},
    ]

    if claim.get("time_sensitive", False):
        fallback_queries.append(
            {
                "query": f'{claim_text} {current_year} latest update official source',
                "objective": "recency",
            }
        )
    else:
        fallback_queries.append(
            {
                "query": f'{claim_text} fact check evidence',
                "objective": "recency",
            }
        )

    deduped = []
    seen = set()
    for query in fallback_queries:
        key = query["query"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(query)
    return deduped


async def _generate_queries(claim: dict) -> list[dict]:
    if llm is None:
        return _fallback_queries(claim)

    user_message = (
        f"Claim: {claim['claim']}\n"
        f"Claim type: {claim.get('claim_type', 'entity')}\n"
        f"Time sensitive: {claim.get('time_sensitive', False)}"
    )

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=QUERY_SYSTEM_PROMPT),
                HumanMessage(content=user_message),
            ]
        )
        query_objects = _parse_json_array(
            response.content if isinstance(response.content, str) else str(response.content)
        )
    except Exception:
        return _fallback_queries(claim)

    normalized_queries = []
    seen = set()
    for query in query_objects:
        query_text = str(query.get("query", "")).strip()
        objective = str(query.get("objective", "direct")).strip().lower() or "direct"
        key = query_text.lower()
        if query_text and key not in seen:
            seen.add(key)
            normalized_queries.append({"query": query_text, "objective": objective})

    return normalized_queries[:3] if normalized_queries else _fallback_queries(claim)


def _normalize_search_results(results: object) -> list[dict]:
    if isinstance(results, tuple):
        content, _artifact = results
        if isinstance(content, str):
            raise ValueError(content)
        return content
    if isinstance(results, list):
        return results
    if isinstance(results, dict):
        return results.get("results", [])
    return []


def _trim_content(content: str, max_chars: int = 900) -> str:
    normalized = re.sub(r"\s+", " ", (content or "").strip())
    return normalized[:max_chars]


def _source_rank_tuple(source: dict, time_sensitive: bool = False) -> tuple:
    has_known_date = source.get("published_label") not in {None, "", "unknown"}
    return (
        1 if time_sensitive and has_known_date else 0,
        source.get("overall_score", 0.0),
        source.get("authority_score", 0.0),
        source.get("relevance_score", 0.0),
        source.get("recency_score", 0.0),
    )


def _select_diverse_sources(
    claim: dict,
    candidate_sources: list[dict],
    max_sources: int = 7,
    per_domain_limit: int = 2,
) -> list[dict]:
    ranked_sources = sorted(
        candidate_sources,
        key=lambda item: _source_rank_tuple(item, claim.get("time_sensitive", False)),
        reverse=True,
    )

    selected = []
    domain_counts: dict[str, int] = {}
    selected_urls = set()

    for source in ranked_sources:
        domain = source.get("domain", "")
        if domain and domain_counts.get(domain, 0) >= per_domain_limit:
            continue

        selected.append(source)
        selected_urls.add(source.get("url"))
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        if len(selected) >= max_sources:
            return selected

    for source in ranked_sources:
        if source.get("url") in selected_urls:
            continue
        selected.append(source)
        if len(selected) >= max_sources:
            break

    return selected


async def retrieve_evidence(claim: dict) -> dict:
    try:
        if search_tool is None:
            raise RuntimeError("TAVILY_API_KEY is not configured.")

        query_variants = await _generate_queries(claim)
        candidate_sources = {}
        query_errors = []

        for query in query_variants:
            try:
                results = await search_tool.ainvoke({"query": query["query"]})
                normalized_results = _normalize_search_results(results)
                query["status"] = "ok"
                query["result_count"] = len(normalized_results)
            except Exception as exc:
                query["status"] = "error"
                query["error"] = str(exc)
                query_errors.append(str(exc))
                continue

            for result in normalized_results:
                url = result.get("url", "")
                if not url:
                    continue

                title = str(result.get("title", "Untitled source")).strip()
                content = _trim_content(result.get("content") or result.get("raw_content") or "")
                snippet = extract_best_snippet(claim["claim"], content, title=title)
                domain = extract_domain(url)
                authority_score = domain_authority_score(domain)
                relevance_score = compute_relevance_score(claim["claim"], title, snippet, content)
                recency_score = compute_recency_score(result.get("published_date"))
                overall_score = compute_overall_source_score(
                    authority_score, relevance_score, recency_score
                )

                source = {
                    "title": title,
                    "url": url,
                    "content": content[:700],
                    "published_date": result.get("published_date", "unknown"),
                    "published_label": format_date_label(result.get("published_date")),
                    "domain": domain,
                    "source_type": classify_source_type(domain),
                    "snippet": snippet,
                    "authority_score": round(authority_score, 2),
                    "relevance_score": round(relevance_score, 2),
                    "recency_score": round(recency_score, 2),
                    "overall_score": round(overall_score, 2),
                    "query_objective": query["objective"],
                }

                normalized = normalize_url(url)
                existing = candidate_sources.get(normalized)
                if existing is None or source["overall_score"] > existing["overall_score"]:
                    candidate_sources[normalized] = source

        ranked_sources = _select_diverse_sources(claim, list(candidate_sources.values()))

        for index, source in enumerate(ranked_sources, start=1):
            source["id"] = f"S{index}"

        retrieval_summary = summarize_retrieval(ranked_sources)

        return {
            "claim_id": claim["id"],
            "query_used": query_variants[0]["query"] if query_variants else "",
            "query_variants": query_variants,
            "retrieval_summary": retrieval_summary,
            "sources": ranked_sources,
            "error": "; ".join(query_errors) if query_errors and not ranked_sources else None,
        }
    except Exception as exc:
        return {
            "claim_id": claim["id"],
            "query_used": "",
            "query_variants": [],
            "retrieval_summary": {
                "source_count": 0,
                "authoritative_count": 0,
                "recent_count": 0,
                "freshest_date": "unknown",
                "domains": [],
            },
            "sources": [],
            "error": str(exc),
        }
