from __future__ import annotations

import asyncio
import ast
import base64
from collections import Counter
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from functools import partial
import re
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from typing import Any, Callable, Optional

from bs4 import BeautifulSoup
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, SystemMessage
import trafilatura

# Circuit breaker state for search providers
_search_provider_failures = {}
_search_provider_last_failure = {}
_search_provider_circuit_open = {}

def _is_circuit_open(provider: str, failure_threshold: int = 3, timeout_seconds: int = 60) -> bool:
    """Check if circuit breaker is open for a provider."""
    if provider not in _search_provider_circuit_open:
        return False
    
    if not _search_provider_circuit_open[provider]:
        return False
    
    # Check if timeout has passed
    last_failure = _search_provider_last_failure.get(provider, 0)
    if time.time() - last_failure > timeout_seconds:
        # Half-open state: allow one request to test
        _search_provider_circuit_open[provider] = False
        return False
    
    return True

def _record_failure(provider: str):
    """Record a failure for circuit breaker."""
    _search_provider_failures[provider] = _search_provider_failures.get(provider, 0) + 1
    _search_provider_last_failure[provider] = time.time()
    
    # Open circuit if threshold reached
    if _search_provider_failures[provider] >= 3:
        _search_provider_circuit_open[provider] = True

def _record_success(provider: str):
    """Record a success and reset failure count."""
    if provider in _search_provider_failures:
        _search_provider_failures[provider] = 0

from llm_provider import create_chat_model
from pipeline.scoring import (
    claim_alias_variants,
    classify_source_type,
    compute_overall_source_score,
    compute_recency_score,
    compute_relevance_score,
    domain_authority_score,
    extract_evidence_passages,
    extract_best_snippet,
    extract_domain,
    format_date_label,
    infer_source_origin,
    normalize_url,
    source_origin_label,
    summarize_retrieval,
    tokenize,
)

llm, llm_descriptor = create_chat_model("retriever", temperature=0.1, max_tokens=2048)
_retriever_llm_lock: asyncio.Lock | None = None


def _get_retriever_llm_lock() -> asyncio.Lock:
    global _retriever_llm_lock
    if _retriever_llm_lock is None:
        _retriever_llm_lock = asyncio.Lock()
    return _retriever_llm_lock


def _initialize_search_tool():
    """Initialize search tool with fallback options."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            return TavilySearchResults(
                max_results=6,
                tavily_api_key=tavily_key,
                include_raw_content=True,
                search_depth="advanced",
            )
        except Exception as e:
            # Log the error but continue - we'll fall back to other methods
            print(f"Warning: Failed to initialize Tavily search: {e}")
            return None
    return None

search_tool = _initialize_search_tool()

QUERY_SYSTEM_PROMPT = """You are a search strategist for a fact-checking engine.
Given a single claim, produce 4 complementary web search queries:
1. A direct query that restates the claim.
2. An authoritative-source query that prefers official or high-credibility sources.
3. A context or recency query that surfaces the latest updates.
4. A contradiction-seeking query (Devil's Advocate) that specifically tries to find evidence that DISPROVES the claim or offers a counter-narrative.

Return ONLY a JSON array in this format:
[
  {"query": "search terms", "objective": "direct|authoritative|recency|contradiction"}
]"""

RECOVERY_SYSTEM_PROMPT = """You are a retrieval planner for a fact-checking engine.
You are given:
- a claim
- the first-pass search queries
- a summary of the retrieved evidence quality
- a small evidence snapshot

Your goal is to decide if the current evidence is SUFFICIENT to prove or disprove the claim with 100% confidence.
If not, identify the missing "missing links" or specific details that need further search.

Return ONLY valid JSON:
{
  "decision": "search" | "stop",
  "reasoning": "Explain what is missing or why the current evidence is sufficient.",
  "queries": [
    {"query": "search terms", "objective": "direct|authoritative|recency|contradiction"}
  ]
}

Rules:
- Use "stop" only if you have found direct, authoritative support OR a clear, documented contradiction.
- If the sources are "mixed" or "low relevance", use "search" to find better grounding.
- Return at most 3 new queries.
- Do not repeat queries that were already tried.
"""

MIN_RECOVERY_SOURCE_COUNT = 2
MIN_RECOVERY_TOP_SCORE = 0.52
MIN_RECOVERY_TOP_RELEVANCE = 0.45
DUCKDUCKGO_SEARCH_URL = "https://duckduckgo.com/html/"
MICROSOFT_BING_SEARCH_URL = "https://www.bing.com/search"
GOOGLE_CSE_SEARCH_URL = "https://customsearch.googleapis.com/customsearch/v1"
SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_NEWS_SEARCH_URL = "https://google.serper.dev/news"
SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
FALLBACK_SEARCH_MAX_RESULTS = 3
FALLBACK_FETCH_TIMEOUT_SECONDS = int(os.getenv("FACTLENS_RETRIEVER_HTTP_TIMEOUT_SECONDS", "20"))
RETRIEVER_USER_AGENT = os.getenv("USER_AGENT", "FactLens/1.0")
MIN_FALLBACK_TEXT_CHARS = 120
MIN_SEARCH_SNIPPET_CHARS = 80
SEARCH_RESULT_HOSTS = {
    "bing.com",
    "duckduckgo.com",
    "google.com",
}
KNOWN_SOURCE_CONTEXT_DOMAINS = {
    "associated press": "apnews.com",
    "ap news": "apnews.com",
    "bbc": "bbc.com",
    "lloyd's list": "lloydslist.com",
    "lloyds list": "lloydslist.com",
    "reuters": "reuters.com",
}
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()

LOCATION_CONTAINMENT_PATTERN = re.compile(
    r"^\s*(.+?)\s+(?:is|are|was|were|lies|lie)\s+(?:located\s+|situated\s+)?in\s+(.+?)[.?!]?\s*$",
    re.IGNORECASE,
)


def _location_containment_claim(claim_text: str) -> tuple[str, str] | None:
    match = LOCATION_CONTAINMENT_PATTERN.search(str(claim_text or "").strip())
    if not match:
        return None

    subject = match.group(1).strip(" ,.")
    location = match.group(2).strip(" ,.")
    if len(tokenize(subject)) < 1 or len(tokenize(location)) < 1:
        return None
    return subject, location


def _claim_focus_text(claim_text: str) -> str:
    location_claim = _location_containment_claim(claim_text)
    if not location_claim:
        return str(claim_text or "").strip()

    subject, location = location_claim
    return (
        f"{subject} location geography country city capital region state province nation "
        f"{location}"
    ).strip()
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "").strip()
GOOGLE_CSE_ID = (
    os.getenv("GOOGLE_CSE_ID", "").strip()
    or os.getenv("GOOGLE_CUSTOM_SEARCH_ENGINE_ID", "").strip()
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", (text or "").strip()))


def _query_overlap_score(query_text: str, claim_text: str) -> float:
    claim_tokens = set(tokenize(claim_text))
    if not claim_tokens:
        return 0.0
    query_tokens = set(tokenize(query_text))
    if not query_tokens:
        return 0.0
    return len(claim_tokens & query_tokens) / len(claim_tokens)


def _build_claim_specific_queries(claim: dict, *, phase: str = "recovery") -> list[dict]:
    claim_text = claim["claim"].strip()
    lowered = claim_text.lower()
    claim_type = str(claim.get("claim_type", "entity") or "entity")
    alias_variants = claim_alias_variants(claim_text, max_variants=2)
    queries: list[dict] = []

    def add_query(query_text: str, objective: str) -> None:
        if not query_text.strip():
            return
        queries.append(
            {
                "query": query_text.strip(),
                "objective": objective,
                "phase": phase,
                "planner": "heuristic",
            }
        )

    def add_alias_queries() -> None:
        for variant in alias_variants:
            add_query(variant, "direct")
            if claim.get("time_sensitive", False):
                add_query(f"{variant} latest official update", "recency")

    capital_match = re.search(r"^\s*(.+?)\s+is the capital of\s+(.+?)[.?!]?\s*$", claim_text, re.IGNORECASE)
    location_match = _location_containment_claim(claim_text)
    symbol_match = re.search(
        r"^\s*the chemical symbol for\s+(.+?)\s+is\s+([A-Za-z0-9]+)[.?!]?\s*$",
        claim_text,
        re.IGNORECASE,
    )
    leadership_match = re.search(
        r"^\s*(?:the\s+)?(?:current|currently|latest)?\s*"
        r"(ceo|chief executive officer|president|prime minister|chair(?:man|person)?|mayor|governor)"
        r"\s+of\s+(.+?)\s+is\s+.+$",
        claim_text,
        re.IGNORECASE,
    )

    if symbol_match:
        element = symbol_match.group(1).strip()
        symbol = symbol_match.group(2).strip()
        add_query(f"{element} symbol {symbol} periodic table", "direct")
        add_query(f"site:nist.gov OR site:rsc.org OR site:ciaaw.org {element} chemical symbol", "authoritative")
        add_query(f'"{element} ({symbol})" element', "direct")
    elif capital_match:
        city = capital_match.group(1).strip()
        country = capital_match.group(2).strip()
        add_query(f'"{city}" "capital of {country}"', "direct")
        add_query(f"site:britannica.com OR site:wikipedia.org {country} capital {city}", "authoritative")
        add_query(f'"capital city of {country}" {city}', "direct")
    elif location_match:
        subject, location = location_match
        add_query(f'"{subject}" capital city country', "direct")
        add_query(f'where is "{subject}" city country', "direct")
        add_query(f'site:britannica.com OR site:wikipedia.org "{subject}" capital city', "authoritative")
        add_query(f'"{subject}" "{location}" city country', "contradiction")
    elif "natural satellite" in lowered and "earth" in lowered:
        add_query('"Earth has one natural satellite" moon', "direct")
        add_query("site:nasa.gov Earth only natural satellite Moon", "authoritative")
        add_query('"Earth one moon natural satellite"', "direct")
    # NEW: Celestial Bodies (Planets, Moons, Stars)
    elif any(word in lowered for word in ["planet", "moon", "star", "galaxy", "orbit", "celestial", "asteroid", "comet"]):
        add_query(f'"{claim_text}" official NASA space facts', "authoritative")
        add_query(f'site:nasa.gov OR site:esa.int OR site:jpl.nasa.gov "{claim_text}"', "authoritative")
    # NEW: Historical Figures & Events
    elif any(word in lowered for word in ["born", "died", "century", "dynasty", "empire", "war", "discovery", "discovered", "ancient", "medieval", "bc", "ad"]):
        add_query(f'"{claim_text}" historical record verification', "direct")
        add_query(f'site:britannica.com OR site:history.com OR site:archives.gov "{claim_text}"', "authoritative")
    # NEW: Science & Technology
    elif any(word in lowered for word in ["theory", "law of", "molecule", "atom", "gene", "dna", "particle", "physics", "chemistry", "biology", "invention", "invented"]):
        add_query(f'"{claim_text}" scientific consensus peer-reviewed', "authoritative")
        add_query(f'site:nature.com OR site:sciencemag.org OR site:nobelprize.org "{claim_text}"', "authoritative")
    elif "largest ocean" in lowered and "pacific" in lowered:
        add_query('"Pacific Ocean is the largest ocean"', "direct")
        add_query("site:noaa.gov Pacific Ocean largest ocean", "authoritative")
        add_query('"Pacific Ocean" "largest ocean on Earth"', "direct")
    elif "strait of hormuz" in lowered and "chokepoint" in lowered:
        add_query('"Strait of Hormuz" oil chokepoint', "direct")
        add_query("site:eia.gov OR site:energy.gov Strait of Hormuz oil chokepoint", "authoritative")
        add_query('"Strait of Hormuz" oil transit chokepoint', "direct")
    # NEW: Confirmation & Pseudoscience Heuristics
    elif any(word in lowered for word in ["nasa", "nih", "who", "unicef", "harvard", "stanford", "mit"]) and any(word in lowered for word in ["confirm", "proven", "study", "trial", "secret", "hidden"]):
        confirmer = next((w for w in ["nasa", "nih", "who", "unicef", "harvard", "stanford", "mit"] if w in lowered), "official")
        add_query(f'site:{confirmer}.gov OR site:{confirmer}.edu "{claim_text}"', "authoritative")
        add_query(f'"{claim_text}" debunked OR pseudoscience OR myth', "contradiction")
        if "quantum" in lowered:
            add_query(f'site:phys.org OR site:scientificamerican.com "{claim_text}" debunked', "authoritative")
    elif any(word in lowered for word in ["clinically proven", "scientifically proven", "quantum healing", "energy fields", "cure chronic"]):
        add_query(f'"{claim_text}" pseudoscience debunked', "contradiction")
        add_query(f'site:quackwatch.org OR site:rationalwiki.org "{claim_text}"', "authoritative")
        add_query(f'site:nih.gov OR site:pubmed.gov "{claim_text}"', "authoritative")
    elif leadership_match:
        role = leadership_match.group(1).strip()
        entity = leadership_match.group(2).strip()
        add_query(f'"{entity}" official {role} leadership', "authoritative")
        add_query(f'"{entity}" {role} official biography', "authoritative")
        add_query(f'"{entity}" {role} latest update', "recency")
    elif claim_type == "numeric":
        add_query(f"{claim_text} official statistics report dataset", "authoritative")
        add_query(f'"{claim_text}" official record', "direct")
    elif claim_type == "quote":
        add_query(f'{claim_text} official statement transcript', "authoritative")
        add_query(f'{claim_text} press release official', "direct")
    add_alias_queries()

    return queries


def _source_url_slug(claim: dict) -> str:
    source_url = str(claim.get("source_url", "") or "").strip()
    if not source_url:
        return ""

    parsed = urlparse(source_url)
    candidates = []
    for part in parsed.path.split("/"):
        cleaned = re.sub(r"\.\w+$", "", str(part or "").strip())
        if not cleaned:
            continue
        if cleaned.isdigit():
            continue
        if cleaned.lower() in {"article", "articles", "articleshow", "business", "international-business"}:
            continue

        normalized = _normalize_text(re.sub(r"[-_]+", " ", cleaned))
        if len(tokenize(normalized)) < 4:
            continue
        candidates.append(normalized)

    if not candidates:
        return ""
    return max(candidates, key=lambda value: (len(tokenize(value)), len(value)))


def _source_article_title(claim: dict) -> str:
    explicit_title = str(claim.get("source_title", "") or "").strip()
    return explicit_title or _source_url_slug(claim) or str(claim.get("source_url", "") or "").strip()


def _extract_quoted_phrases(*texts: str) -> list[str]:
    seen: set[str] = set()
    phrases: list[str] = []
    patterns = (
        r'"([^"\n]+)"',
        r"“([^”\n]+)”",
        r"'([^'\n]+)'",
        r"‘([^’\n]+)’",
    )

    for text in texts:
        for pattern in patterns:
            for match in re.findall(pattern, text or ""):
                phrase = _normalize_text(match)
                token_count = len(tokenize(phrase))
                key = phrase.lower()
                if token_count < 2 or token_count > 8 or key in seen:
                    continue
                seen.add(key)
                phrases.append(phrase)

    return phrases


def _extract_named_context_phrases(*texts: str) -> list[str]:
    pattern = re.compile(
        r"\b(?:[A-Z][A-Za-z]+(?:[-'][A-Za-z]+)?)(?:\s+(?:of|the|and)\s+[A-Z][A-Za-z]+(?:[-'][A-Za-z]+)?|\s+[A-Z][A-Za-z]+(?:[-'][A-Za-z]+)?){0,4}\b"
    )
    banned = {
        "According",
        "Among",
        "Any",
        "Costs",
        "For",
        "Meanwhile",
        "Other",
        "Several",
        "The",
        "Under",
        "What",
        "While",
    }
    seen: set[str] = set()
    phrases: list[str] = []

    for text in texts:
        for match in pattern.findall(text or ""):
            phrase = _normalize_text(match)
            token_count = len(tokenize(phrase))
            key = phrase.lower()
            if not phrase or token_count < 1 or token_count > 6 or key in seen:
                continue
            if phrase in banned:
                continue
            if token_count == 1 and not phrase.isupper():
                continue
            seen.add(key)
            phrases.append(phrase)

    return phrases


def _extract_cited_source_domains(*texts: str) -> list[str]:
    combined = " ".join(str(text or "") for text in texts).lower()
    domains: list[str] = []
    seen: set[str] = set()

    for marker, domain in KNOWN_SOURCE_CONTEXT_DOMAINS.items():
        if marker not in combined or domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)

    return domains


def _build_source_context_queries(claim: dict, *, phase: str = "recovery") -> list[dict]:
    slug = _source_url_slug(claim)
    if not slug:
        return []

    slug_terms = tokenize(slug)
    compact_slug = " ".join(slug_terms[:10]).strip()
    claim_text = str(claim.get("claim", "") or "").strip()
    context_text = str(claim.get("context", "") or "").strip()
    source_text = str(claim.get("source_text", "") or "").strip()
    quoted_phrases = _extract_quoted_phrases(claim_text, context_text, source_text)
    named_phrases = _extract_named_context_phrases(claim_text, context_text)
    cited_domains = _extract_cited_source_domains(claim_text, context_text, source_text)
    combined_text = " ".join(part for part in [claim_text, context_text, source_text, slug] if part).lower()
    location_anchor = '"Strait of Hormuz"' if "strait of hormuz" in combined_text else ""
    queries: list[dict] = []
    seen_queries: set[str] = set()

    def add_query(query_text: str, objective: str) -> None:
        normalized_query = query_text.strip()
        key = normalized_query.lower()
        if not normalized_query or key in seen_queries:
            return
        seen_queries.add(key)
        queries.append(
            {
                "query": normalized_query,
                "objective": objective,
                "phase": phase,
                "planner": "heuristic",
            }
        )

    add_query(f'"{slug}"', "direct")

    if quoted_phrases:
        phrase_query = [f'"{quoted_phrases[0]}"']
        if location_anchor and location_anchor.lower() not in quoted_phrases[0].lower():
            phrase_query.append(location_anchor)
        if "iran" in combined_text and "iran" not in quoted_phrases[0].lower():
            phrase_query.append("Iran")
        add_query(" ".join(phrase_query), "direct")

    if named_phrases:
        add_query(
            " ".join(
                f'"{phrase}"' if " " in phrase else phrase
                for phrase in named_phrases[:3]
            ),
            "direct",
        )
    elif compact_slug and compact_slug.lower() != slug.lower():
        add_query(compact_slug, "direct")

    if cited_domains:
        citation_terms = quoted_phrases[:1] or named_phrases[:2] or [compact_slug or slug]
        citation_query_terms = " ".join(
            f'"{term}"' if " " in term else term
            for term in citation_terms
        )
        add_query(
            f"site:{cited_domains[0]} {citation_query_terms}",
            "authoritative",
        )

    add_query(
        f"site:reuters.com OR site:apnews.com OR site:bbc.com OR site:lloydslist.com {compact_slug or slug}",
        "authoritative",
    )
    return queries


def _looks_like_binary_blob(text: str) -> bool:
    sample = (text or "")[:1200]
    if not sample:
        return False

    if sample.lstrip().startswith("%PDF-"):
        return True

    lowered = sample.lower()
    if "%pdf" in lowered and "endobj" in lowered and "stream" in lowered:
        return True

    control_chars = sum(1 for char in sample if ord(char) < 32 and char not in "\n\r\t")
    return (control_chars / max(len(sample), 1)) > 0.02


def _visible_text(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _normalize_text(soup.get_text("\n"))


def _extract_text_from_html(html: str, *, url: str) -> str:
    extracted = trafilatura.extract(
        html,
        url=url,
        output_format="txt",
        favor_precision=True,
        include_comments=False,
        include_tables=False,
    )
    return _normalize_text(extracted or "")


async def _run_blocking(func, *args, **kwargs):
    to_thread = getattr(asyncio, "to_thread", None)
    if to_thread is not None:
        return await to_thread(func, *args, **kwargs)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


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


def _parse_json_object(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    match = re.search(r"\{[\s\S]*\}", cleaned)
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
            raise ValueError("Could not parse retriever planner response.") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed


def _normalize_objective(value: object) -> str:
    objective = str(value or "direct").strip().lower()
    return objective if objective in {"direct", "authoritative", "recency", "contradiction"} else "direct"


def _fallback_queries(claim: dict) -> list[dict]:
    claim_text = claim["claim"].strip()
    current_year = datetime.utcnow().year
    alias_variants = claim_alias_variants(claim_text, max_variants=2)
    fallback_queries = [
        {"query": claim_text, "objective": "direct", "phase": "primary", "planner": "heuristic"},
        {
            "query": f'"{claim_text}" official source',
            "objective": "authoritative",
            "phase": "primary",
            "planner": "heuristic",
        },
    ]

    if claim.get("time_sensitive", False):
        fallback_queries.append(
            {
                "query": f'{claim_text} {current_year} latest update official source',
                "objective": "recency",
                "phase": "primary",
                "planner": "heuristic",
            }
        )
    else:
        fallback_queries.append(
            {
                "query": f'{claim_text} fact check evidence',
                "objective": "recency",
                "phase": "primary",
                "planner": "heuristic",
            }
        )

    for variant in alias_variants:
        fallback_queries.append(
            {
                "query": variant,
                "objective": "direct",
                "phase": "primary",
                "planner": "heuristic",
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
    claim_specific_queries = _build_claim_specific_queries(
        claim,
        phase="primary",
    ) + _build_source_context_queries(claim, phase="primary")
    fallback_queries = _fallback_queries(claim)

    if llm is None:
        return _select_query_mix(claim_specific_queries, fallback_queries)

    user_message = (
        f"Claim: {claim['claim']}\n"
        f"Claim type: {claim.get('claim_type', 'entity')}\n"
        f"Time sensitive: {claim.get('time_sensitive', False)}"
    )

    try:
        async with _get_retriever_llm_lock():
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
        return _select_query_mix(claim_specific_queries, fallback_queries)

    normalized_queries = []
    seen = set()
    for query in query_objects:
        query_text = str(query.get("query", "")).strip()
        objective = str(query.get("objective", "direct")).strip().lower() or "direct"
        key = query_text.lower()
        if query_text and key not in seen:
            if _query_overlap_score(query_text, claim["claim"]) < 0.2:
                continue
            seen.add(key)
            normalized_queries.append(
                {
                    "query": query_text,
                    "objective": _normalize_objective(objective),
                    "phase": "primary",
                    "planner": "llm",
                }
            )

    if normalized_queries:
        return _select_query_mix(claim_specific_queries, normalized_queries)

    return _select_query_mix(claim_specific_queries, fallback_queries)


def _normalize_search_results(results: object) -> list[dict]:
    if isinstance(results, str):
        raise ValueError(results)
    if isinstance(results, tuple):
        content, _artifact = results
        if isinstance(content, str):
            raise ValueError(content)
        return content
    if isinstance(results, list):
        return results
    if isinstance(results, dict):
        if isinstance(results.get("error"), str) and results.get("error").strip():
            raise ValueError(results["error"])
        if isinstance(results.get("results"), str):
            raise ValueError(results["results"])
        return results.get("results", [])
    return []


def _extract_result_url(href: str) -> str:
    resolved = urljoin(DUCKDUCKGO_SEARCH_URL, href or "")
    parsed = urlparse(resolved)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        redirected = parse_qs(parsed.query).get("uddg", [""])[0]
        if redirected:
            return unquote(redirected)
    if any(parsed.netloc == host or parsed.netloc.endswith(f".{host}") for host in SEARCH_RESULT_HOSTS):
        return ""
    return resolved if resolved.startswith("http") else ""


def _extract_bing_result_url(href: str) -> str:
    resolved = urljoin(MICROSOFT_BING_SEARCH_URL, href or "")
    parsed = urlparse(resolved)
    if "bing.com" in parsed.netloc:
        encoded_target = parse_qs(parsed.query).get("u", [""])[0]
        if encoded_target.startswith("a1"):
            encoded_target = encoded_target[2:]
            padding = "=" * (-len(encoded_target) % 4)
            try:
                return base64.b64decode(encoded_target + padding).decode("utf-8")
            except Exception:
                pass
        return ""
    if any(parsed.netloc == host or parsed.netloc.endswith(f".{host}") for host in SEARCH_RESULT_HOSTS):
        return ""
    return resolved if resolved.startswith("http") else ""


def _extract_published_date(html: str) -> str:
    if not html:
        return "unknown"

    soup = BeautifulSoup(html, "html.parser")
    candidate_values = []

    for tag in soup.find_all(["meta", "time"]):
        for key in ("content", "datetime"):
            value = str(tag.get(key, "")).strip()
            if value:
                candidate_values.append(value)

    for value in candidate_values:
        match = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", value)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    return "unknown"


def _normalize_search_published_date(*values: object) -> str:
    for value in values:
        if value in {None, "", "unknown"}:
            continue

        if isinstance(value, (int, float)) and value > 0:
            try:
                return datetime.utcfromtimestamp(float(value)).strftime("%Y-%m-%d")
            except Exception:
                continue

        text = str(value).strip()
        if not text:
            continue

        normalized_text = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized_text)
            return parsed.date().isoformat()
        except ValueError:
            pass

        match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        for fmt in (
            "%b %d, %Y",
            "%B %d, %Y",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d %Y",
            "%B %d %Y",
        ):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue

        relative_match = re.search(
            r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago",
            text.lower(),
        )
        if relative_match:
            amount = int(relative_match.group(1))
            unit = relative_match.group(2)
            if unit == "minute":
                delta = timedelta(minutes=amount)
            elif unit == "hour":
                delta = timedelta(hours=amount)
            elif unit == "day":
                delta = timedelta(days=amount)
            elif unit == "week":
                delta = timedelta(weeks=amount)
            elif unit == "month":
                delta = timedelta(days=30 * amount)
            else:
                delta = timedelta(days=365 * amount)
            return (datetime.utcnow() - delta).date().isoformat()

    return "unknown"


def _build_wikipedia_result(title: str, page: dict, fallback_timestamp: object) -> dict | None:
    extract = _normalize_text(str(page.get("extract", "") or ""))
    if not extract or len(extract) < MIN_FALLBACK_TEXT_CHARS:
        return None
    if "may refer to" in extract.lower():
        return None

    page_url = str(page.get("fullurl", "") or "").strip()
    if not page_url:
        page_url = f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"

    revision_candidates = page.get("revisions", []) if isinstance(page.get("revisions"), list) else []
    revision_timestamp = ""
    if revision_candidates and isinstance(revision_candidates[0], dict):
        revision_timestamp = str(revision_candidates[0].get("timestamp", "") or "").strip()

    return {
        "url": page_url,
        "title": title,
        "raw_content": extract,
        "published_date": _normalize_search_published_date(revision_timestamp, fallback_timestamp),
    }


def _wikipedia_search_sync(query: str, max_results: int = FALLBACK_SEARCH_MAX_RESULTS) -> list[dict]:
    search_data = _http_get_json(
        WIKIPEDIA_API_URL,
        params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": str(max_results * 2),
            "format": "json",
            "utf8": "1",
        },
    )
    search_items = search_data.get("query", {}).get("search", [])
    if not isinstance(search_items, list):
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()

    for item in search_items:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", "") or "").strip()
        if not title or title.lower().endswith("(disambiguation)"):
            continue

        page_data = _http_get_json(
            WIKIPEDIA_API_URL,
            params={
                "action": "query",
                "prop": "extracts|info|revisions",
                "titles": title,
                "format": "json",
                "formatversion": "2",
                "explaintext": "1",
                "exintro": "1",
                "inprop": "url",
                "rvprop": "timestamp",
                "rvlimit": "1",
            },
        )
        pages = page_data.get("query", {}).get("pages", [])
        if not isinstance(pages, list) or not pages:
            continue

        built = _build_wikipedia_result(
            title,
            pages[0] if isinstance(pages[0], dict) else {},
            item.get("timestamp"),
        )
        if built is None or built["url"] in seen_urls:
            continue

        seen_urls.add(built["url"])
        results.append(built)
        if len(results) >= max_results:
            break

    return results


def _extract_google_cse_published_date(item: dict) -> str:
    pagemap = item.get("pagemap", {}) if isinstance(item.get("pagemap"), dict) else {}
    metatags = pagemap.get("metatags", []) if isinstance(pagemap.get("metatags"), list) else []
    candidates: list[object] = [item.get("snippet"), item.get("htmlSnippet")]

    for tag in metatags:
        if not isinstance(tag, dict):
            continue
        candidates.extend(
            [
                tag.get("article:published_time"),
                tag.get("article:modified_time"),
                tag.get("date"),
                tag.get("pubdate"),
                tag.get("og:pubdate"),
                tag.get("og:updated_time"),
                tag.get("dc.date"),
            ]
        )

    return _normalize_search_published_date(*candidates)


def _extract_serpapi_published_date(item: dict) -> str:
    return _normalize_search_published_date(
        item.get("date"),
        item.get("date_utc"),
        item.get("snippet"),
    )


def _extract_serper_published_date(item: dict) -> str:
    return _normalize_search_published_date(
        item.get("date"),
        item.get("snippet"),
    )


def _http_get(url: str, *, params: dict[str, str] | None = None) -> str:
    target_url = url
    if params:
        target_url = f"{url}?{urlencode(params)}"
    request = Request(target_url, headers={"User-Agent": RETRIEVER_USER_AGENT})
    with urlopen(request, timeout=FALLBACK_FETCH_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


def _http_get_json(url: str, *, params: dict[str, str] | None = None) -> dict:
    payload = _http_get(url, params=params)
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object from the search provider.")
    return parsed


def _http_post_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    target_url = url
    if params:
        target_url = f"{url}?{urlencode(params)}"
    request_headers = {"User-Agent": RETRIEVER_USER_AGENT, **(headers or {})}
    request = Request(target_url, data=b"", headers=request_headers, method="POST")
    with urlopen(request, timeout=FALLBACK_FETCH_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        payload = response.read().decode(charset, errors="ignore")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object from the search provider.")
    return parsed


async def _fetch_fallback_result_async(
    url: str,
    title: str,
    snippet: str,
    *,
    published_date_hint: str = "unknown",
) -> dict | None:
    """Async wrapper for fetching and cleaning fallback search result content."""
    return await asyncio.to_thread(
        _fetch_fallback_result,
        url,
        title,
        snippet,
        published_date_hint=published_date_hint,
    )


def _fetch_fallback_result(
    url: str,
    title: str,
    snippet: str,
    *,
    published_date_hint: str = "unknown",
) -> dict | None:
    """Synchronous fetching and cleaning of fallback search result content."""
    try:
        html = _http_get(url)
        content = trafilatura.extract(html, include_links=False, include_images=False)
        content = content or snippet
        if _looks_like_binary_blob(content):
            return None
        if len(content) < MIN_FALLBACK_TEXT_CHARS:
            return None

        # Basic cleanup
        content = re.sub(r"\s+", " ", content).strip()
        normalized_content = _normalize_text(content)
        if len(normalized_content) < MIN_SEARCH_SNIPPET_CHARS:
            return None
        return {
            "url": url,
            "title": title or url,
            "raw_content": normalized_content,
            "published_date": _normalize_search_published_date(published_date_hint),
        }
    except Exception:
        return None


async def _search_with_duckduckgo(query_text: str) -> list[dict]:
    """Asynchronous DuckDuckGo search using parallel fetching."""
    try:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query_text)}"
        html = await asyncio.to_thread(_http_get, url)
        soup = BeautifulSoup(html, "html.parser")
        
        candidates = []
        for res in soup.select("a.result__a")[:5]: 
            link = _extract_result_url(res.get("href"))
            if not link: continue
            res_title = res.get_text()
            container = res.find_parent("div", class_="result")
            snippet_node = container.select_one(".result__snippet") if container else None
            snippet = snippet_node.get_text() if snippet_node else ""
            candidates.append((link, res_title, snippet))
        
        if not candidates:
            return []
            
        fetch_tasks = [
            _fetch_fallback_result_async(link, title, snip) 
            for link, title, snip in candidates[:3]
        ]
        results = await asyncio.gather(*fetch_tasks)
        return [r for r in results if r]
    except Exception:
        return []


async def _search_with_bing(query_text: str) -> list[dict]:
    """Asynchronous Bing search using parallel fetching."""
    try:
        url = f"https://www.bing.com/search?q={quote_plus(query_text)}"
        html = await asyncio.to_thread(_http_get, url)
        soup = BeautifulSoup(html, "html.parser")
        
        candidates = []
        for res in soup.select("li.b_algo h2 a")[:4]:
            link = _extract_bing_result_url(res.get("href"))
            if not link: continue
            res_title = res.get_text()
            candidates.append((link, res_title, ""))
        
        if not candidates:
            return []
            
        fetch_tasks = [
            _fetch_fallback_result_async(link, title, "") 
            for link, title, _ in candidates[:3]
        ]
        results = await asyncio.gather(*fetch_tasks)
        return [r for r in results if r]
    except Exception:
        return []





def _build_search_api_result(
    url: str,
    title: str,
    snippet: str,
    *,
    published_date: str = "unknown",
) -> dict | None:
    fetched = _fetch_fallback_result(
        url,
        title,
        snippet,
        published_date_hint=published_date,
    )
    if fetched is not None:
        return fetched

    normalized_snippet = _normalize_text(snippet)
    if len(normalized_snippet) < MIN_SEARCH_SNIPPET_CHARS:
        return None

    return {
        "url": url,
        "title": title or url,
        "raw_content": normalized_snippet,
        "published_date": _normalize_search_published_date(published_date),
    }



def _google_cse_search_sync(query: str, max_results: int = FALLBACK_SEARCH_MAX_RESULTS) -> list[dict]:
    if not (os.getenv("GOOGLE_API_KEY", "").strip() and GOOGLE_CSE_ID):
        return []

    data = _http_get_json(
        GOOGLE_CSE_SEARCH_URL,
        params={
            "key": os.getenv("GOOGLE_API_KEY", "").strip(),
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "num": str(max_results),
        },
    )
    items = data.get("items", [])
    if not isinstance(items, list):
        return []

    results = []
    seen_urls = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("link", "") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        built = _build_search_api_result(
            url,
            str(item.get("title", "") or "").strip(),
            str(item.get("snippet", "") or "").strip(),
            published_date=_extract_google_cse_published_date(item),
        )
        if built is None:
            continue
        results.append(built)
        if len(results) >= max_results:
            break

    return results


async def _search_with_google_cse(query: str) -> list[dict]:
    return await _run_blocking(_google_cse_search_sync, query)


async def _search_with_wikipedia(query: str) -> list[dict]:
    return await _run_blocking(_wikipedia_search_sync, query)


def _serper_search_sync(
    query: str,
    max_results: int = FALLBACK_SEARCH_MAX_RESULTS,
    *,
    news: bool = False,
) -> list[dict]:
    if not SERPER_API_KEY:
        return []

    data = _http_post_json(
        SERPER_NEWS_SEARCH_URL if news else SERPER_SEARCH_URL,
        params={
            "q": query,
            "num": str(max_results),
            "gl": "us",
            "hl": "en",
        },
        headers={
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
        },
    )
    candidate_key = "news" if news else "organic"
    items = data.get(candidate_key, [])
    if not isinstance(items, list) or not items:
        items = data.get("organic", []) if isinstance(data.get("organic"), list) else []

    results = []
    seen_urls = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("link", "") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        built = _build_search_api_result(
            url,
            str(item.get("title", "") or "").strip(),
            str(item.get("snippet", "") or "").strip(),
            published_date=_extract_serper_published_date(item),
        )
        if built is None:
            continue
        results.append(built)
        if len(results) >= max_results:
            break

    return results


async def _search_with_serper(
    query: str,
    *,
    news: bool = False,
) -> list[dict]:
    return await _run_blocking(_serper_search_sync, query, news=news)


def _serpapi_search_sync(
    query: str,
    max_results: int = FALLBACK_SEARCH_MAX_RESULTS,
    *,
    news: bool = False,
) -> list[dict]:
    if not SERPAPI_API_KEY:
        return []

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": str(max_results),
    }
    if news:
        params["tbm"] = "nws"

    data = _http_get_json(SERPAPI_SEARCH_URL, params=params)
    candidate_key = "news_results" if news else "organic_results"
    items = data.get(candidate_key, [])
    if not isinstance(items, list) or not items:
        items = data.get("organic_results", []) if isinstance(data.get("organic_results"), list) else []

    results = []
    seen_urls = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("link", "") or item.get("url", "") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        built = _build_search_api_result(
            url,
            str(item.get("title", "") or "").strip(),
            str(item.get("snippet", "") or "").strip(),
            published_date=_extract_serpapi_published_date(item),
        )
        if built is None:
            continue
        results.append(built)
        if len(results) >= max_results:
            break

    return results


async def _search_with_serpapi(
    query: str,
    *,
    news: bool = False,
) -> list[dict]:
    return await _run_blocking(_serpapi_search_sync, query, news=news)


def _prefer_news_search(objective: str, claim_time_sensitive: bool) -> bool:
    return objective == "recency" or (claim_time_sensitive and objective == "direct")


def _search_provider_specs(
    query_text: str,
    *,
    objective: str = "direct",
    claim_time_sensitive: bool = False,
) -> list[tuple[str, object, bool]]:
    specs: list[tuple[str, object, bool]] = []
    prefer_reference_first = not claim_time_sensitive and objective in {"direct", "authoritative"}
    use_secondary_search_apis = True

    if search_tool is not None:
        specs.append(
            (
                "tavily",
                lambda: search_tool.ainvoke({"query": query_text}),
                False,
            )
        )

    def append_wikipedia() -> None:
        specs.append(
            (
                "wikipedia",
                lambda: _search_with_wikipedia(query_text),
                True,
            )
        )

    def append_serper() -> None:
        specs.append(
            (
                "serper",
                lambda: _search_with_serper(
                    query_text,
                    news=_prefer_news_search(objective, claim_time_sensitive),
                ),
                True,
            )
        )

    if prefer_reference_first:
        append_wikipedia()

    if use_secondary_search_apis and SERPER_API_KEY:
        append_serper()

    if not prefer_reference_first:
        append_wikipedia()

    if use_secondary_search_apis and os.getenv("GOOGLE_API_KEY", "").strip() and GOOGLE_CSE_ID:
        specs.append(
            (
                "google_cse",
                lambda: _search_with_google_cse(query_text),
                True,
            )
        )
    specs.append(
        (
            "duckduckgo_html",
            lambda: _search_with_duckduckgo(query_text),
            True,
        )
    )
    specs.append(
        (
            "bing_html",
            lambda: _search_with_bing(query_text),
            True,
        )
    )

    return specs


async def _attempt_search_provider(
    provider: str,
    search_coro_factory,
    *,
    fallback_used: bool,
) -> dict:
    # Check circuit breaker
    if _is_circuit_open(provider):
        return {
            "provider": provider,
            "results": [],
            "fallback_used": fallback_used,
            "warning": f"{provider} circuit breaker is open due to repeated failures",
            "error": "Circuit breaker open",
        }
    
    try:
        # Reduced timeout for primary APIs to trigger fallbacks faster
        provider_timeout = 7.0 if provider == "tavily" else 15.0
        result = await asyncio.wait_for(search_coro_factory(), timeout=provider_timeout)
        normalized_results = _normalize_search_results(result)
        
        # Record success
        _record_success(provider)
        
        return {
            "provider": provider,
            "results": normalized_results,
            "fallback_used": fallback_used,
            "warning": None if normalized_results else f"{provider} returned no results.",
            "error": None,
        }
    except asyncio.TimeoutError:
        _record_failure(provider)
        return {
            "provider": provider,
            "results": [],
            "fallback_used": fallback_used,
            "warning": f"{provider} request timed out",
            "error": "Timeout",
        }
    except Exception as exc:
        exc_str = str(exc)
        # If rate limited (Error 432), open circuit for longer (1 hour)
        if "432" in exc_str:
            _record_failure(provider) # Sets initial failure
            _search_provider_failures[provider] = 10 # Force well past threshold
            _search_provider_circuit_open[provider] = True
            _search_provider_last_failure[provider] = time.time() + 3600 # Artificially shift last failure
        else:
            _record_failure(provider)
            
        return {
            "provider": provider,
            "results": [],
            "fallback_used": fallback_used,
            "warning": None,
            "error": exc_str,
        }


async def _search_query_provider_attempts(
    query_text: str,
    *,
    objective: str = "direct",
    claim_time_sensitive: bool = False,
) -> list[dict]:
    attempts: list[dict] = []

    for provider, search_coro_factory, fallback_used in _search_provider_specs(
        query_text,
        objective=objective,
        claim_time_sensitive=claim_time_sensitive,
    ):
        attempt = await _attempt_search_provider(
            provider,
            search_coro_factory,
            fallback_used=fallback_used,
        )
        attempts.append(attempt)

    return attempts


async def _search_query(query_text: str) -> tuple[list[dict], dict]:
    attempts = await _search_query_provider_attempts(query_text)
    for attempt in attempts:
        if attempt["results"]:
            return attempt["results"], {
                "provider": attempt["provider"],
                "fallback_used": bool(attempt["fallback_used"]),
                "warning": attempt.get("warning"),
            }

    errors = [attempt["error"] for attempt in attempts if attempt.get("error")]
    if errors:
        raise RuntimeError("; ".join(errors))

    if not attempts:
        return [], {
            "provider": "none",
            "fallback_used": False,
            "warning": "No search providers are configured.",
        }

    last_attempt = attempts[-1]
    return [], {
        "provider": last_attempt["provider"],
        "fallback_used": bool(last_attempt["fallback_used"]),
        "warning": last_attempt.get("warning"),
    }


def _trim_content(content: str, max_chars: int = 900) -> str:
    normalized = re.sub(r"\s+", " ", (content or "").strip())
    return normalized[:max_chars]


def _focus_content_for_claim(
    claim_text: str,
    raw_content: str,
    *,
    title: str = "",
    max_chars: int = 2200,
    window_chars: int = 900,
    step_chars: int = 350,
) -> str:
    normalized = _normalize_text(raw_content)
    if not normalized:
        return ""
    focus_claim_text = _claim_focus_text(claim_text)
    if len(normalized) <= max_chars:
        return normalized

    window_size = max(window_chars, 300)
    step_size = max(step_chars, 150)
    windows: list[tuple[float, int, str]] = []
    start = 0

    while start < len(normalized):
        raw_window = normalized[start : start + window_size]
        if not raw_window.strip():
            start += step_size
            continue

        window = raw_window
        if start > 0 and " " in window:
            window = window[window.find(" ") + 1 :]
        if start + window_size < len(normalized) and " " in window:
            window = window.rsplit(" ", 1)[0]
        window = window.strip()
        if len(window) < 80:
            start += step_size
            continue

        snippet = extract_best_snippet(focus_claim_text, window, title=title, max_chars=240)
        passages = extract_evidence_passages(
            focus_claim_text,
            window,
            title=title,
            max_passages=1,
            min_score=0.0,
            max_chars=260,
        )
        passage_score = max((float(passage.get("score", 0.0) or 0.0) for passage in passages), default=0.0)
        score = max(
            compute_relevance_score(focus_claim_text, title, snippet, window),
            passage_score,
        )
        windows.append((score, start, window))
        start += step_size

    if not windows:
        return _trim_content(normalized, max_chars=max_chars)

    windows.sort(key=lambda item: (item[0], -len(item[2])), reverse=True)
    if windows[0][0] < 0.2:
        return _trim_content(normalized, max_chars=max_chars)

    selected: list[tuple[int, str]] = []
    min_distance = max(step_size, window_size // 2)
    selection_floor = max(0.24, windows[0][0] * 0.5)
    for score, start, window in windows:
        if score < selection_floor:
            continue
        if any(abs(start - existing_start) < min_distance for existing_start, _ in selected):
            continue
        selected.append((start, window))
        combined_length = sum(len(text) for _, text in selected) + max(len(selected) - 1, 0)
        if combined_length >= max_chars:
            break

    if not selected:
        return _trim_content(normalized, max_chars=max_chars)

    focused = " ".join(text for _, text in sorted(selected, key=lambda item: item[0]))
    return _trim_content(focused, max_chars=max_chars)


def _dedupe_queries(queries: list[dict], seen_queries: set[str] | None = None) -> list[dict]:
    seen = set(seen_queries or set())
    deduped = []

    for query in queries:
        query_text = str(query.get("query", "")).strip()
        key = query_text.lower()
        if not query_text or key in seen:
            continue
        seen.add(key)
        deduped.append(query)

    return deduped


def _select_query_mix(
    claim_specific_queries: list[dict],
    generated_queries: list[dict],
    *,
    max_queries: int = 4,
) -> list[dict]:
    merged = _dedupe_queries(claim_specific_queries + generated_queries)
    if len(merged) <= max_queries:
        return merged

    selected: list[dict] = []
    seen: set[str] = set()

    def take_from(pools: list[list[dict]], objective: str | None = None) -> bool:
        for pool in pools:
            for query in pool:
                query_text = str(query.get("query", "")).strip()
                key = query_text.lower()
                if not query_text or key in seen:
                    continue
                if objective is not None and query.get("objective") != objective:
                    continue
                seen.add(key)
                selected.append(query)
                return True
        return False

    take_from([claim_specific_queries, generated_queries], "authoritative")
    take_from([claim_specific_queries, generated_queries], "direct")
    take_from([generated_queries, claim_specific_queries], "contradiction")
    take_from([generated_queries, claim_specific_queries], "recency")

    for query in merged:
        query_text = str(query.get("query", "")).strip()
        key = query_text.lower()
        if not query_text or key in seen:
            continue
        seen.add(key)
        selected.append(query)
        if len(selected) >= max_queries:
            break

    return selected[:max_queries]


def _source_rank_tuple(source: dict, claim: dict) -> tuple:
    has_known_date = source.get("published_label") not in {None, "", "unknown"}
    claim_type = str(claim.get("claim_type", "entity") or "entity")
    source_origin = str(source.get("source_origin", "") or "").strip().lower()
    source_type = str(source.get("source_type", "") or "").strip().lower()
    non_social_preference = 1
    non_web_preference = 1
    if claim_type != "quote":
        if source_origin == "social" or source_type == "social":
            non_social_preference = 0
        if source_origin in {"social", "web"} or source_type in {"social", "web"}:
            non_web_preference = 0
    return (
        1 if source.get("primary_preferred") else 0,
        non_social_preference,
        non_web_preference,
        source.get("source_origin_score", 0.0),
        1 if claim.get("time_sensitive", False) and has_known_date else 0,
        source.get("overall_score", 0.0),
        source.get("authority_score", 0.0),
        source.get("relevance_score", 0.0),
        source.get("recency_score", 0.0),
    )


def _annotate_source_independence(sources: list[dict]) -> list[dict]:
    group_sizes = Counter(
        str(
            source.get("independence_key")
            or source.get("domain", "")
            or source.get("url", "")
        ).strip()
        for source in sources
        if str(
            source.get("independence_key")
            or source.get("domain", "")
            or source.get("url", "")
        ).strip()
    )
    group_positions: dict[str, int] = {}
    annotated: list[dict] = []

    for source in sources:
        clone = dict(source)
        group_key = str(
            clone.get("independence_key")
            or clone.get("domain", "")
            or clone.get("url", "")
        ).strip()
        if group_key:
            rank = group_positions.get(group_key, 0) + 1
            group_positions[group_key] = rank
            group_size = group_sizes.get(group_key, 1)
        else:
            rank = 1
            group_size = 1

        independence_weight = 1.0 if group_size <= 1 else max(0.58, 1.0 - ((rank - 1) * 0.18))
        clone["independence_rank"] = rank
        clone["independence_group_size"] = group_size
        clone["independence_weight"] = round(independence_weight, 2)
        intelligence = dict(clone.get("source_intelligence") or {})
        intelligence["independence_rank"] = rank
        intelligence["independence_group_size"] = group_size
        intelligence["independence_weight"] = round(independence_weight, 2)
        clone["source_intelligence"] = intelligence
        annotated.append(clone)

    return annotated


def _select_diverse_sources(
    claim: dict,
    candidate_sources: list[dict],
    max_sources: int = 7,
    per_domain_limit: int = 2,
    per_network_limit: int = 2,
) -> list[dict]:
    ranked_sources = sorted(
        candidate_sources,
        key=lambda item: _source_rank_tuple(item, claim),
        reverse=True,
    )

    selected = []
    domain_counts: dict[str, int] = {}
    network_counts: dict[str, int] = {}
    selected_urls = set()

    for source in ranked_sources:
        domain = source.get("domain", "")
        network_key = str(source.get("independence_key", "") or domain).strip()
        if domain and domain_counts.get(domain, 0) >= per_domain_limit:
            continue
        if network_key and network_counts.get(network_key, 0) >= per_network_limit:
            continue

        selected.append(source)
        selected_urls.add(source.get("url"))
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        if network_key:
            network_counts[network_key] = network_counts.get(network_key, 0) + 1

        if len(selected) >= max_sources:
            return _annotate_source_independence(selected)

    for source in ranked_sources:
        if source.get("url") in selected_urls:
            continue
        selected.append(source)
        if len(selected) >= max_sources:
            break

    return _annotate_source_independence(selected)


def _query_site_constraints(query_text: str) -> list[str]:
    constraints = []
    seen = set()
    for match in re.findall(
        r"site:([A-Za-z0-9.-]+\.[A-Za-z]{2,})",
        query_text or "",
        flags=re.IGNORECASE,
    ):
        cleaned = match.strip().lower().lstrip(".")
        domain = cleaned[4:] if cleaned.startswith("www.") else cleaned
        if not domain or domain in seen:
            continue
        seen.add(domain)
        constraints.append(domain)
    return constraints


def _result_matches_query_constraints(result: dict, query: dict) -> bool:
    constraints = _query_site_constraints(str(query.get("query", "") or ""))
    if not constraints:
        return True

    domain = extract_domain(str(result.get("url", "") or ""))
    if not domain:
        return False

    return any(domain == constraint or domain.endswith(f".{constraint}") for constraint in constraints)


def _source_snapshot(url: str, title: str, content: str, passages: list[dict]) -> dict:
    focused_excerpt = str(content or "").strip()[:420]
    normalized_url = normalize_url(url)
    content_hash = hashlib.sha1(str(content or "").encode("utf-8")).hexdigest()
    snapshot_id = hashlib.sha1(f"{normalized_url}|{title}|{content_hash}".encode("utf-8")).hexdigest()[:12]
    return {
        "snapshot_id": f"snapshot-{snapshot_id}",
        "captured_at": f"{datetime.utcnow().replace(microsecond=0).isoformat()}Z",
        "content_hash": content_hash[:16],
        "excerpt": focused_excerpt,
        "excerpt_char_count": len(focused_excerpt),
        "passage_ids": [str(passage.get("id", "")).strip() for passage in passages if passage.get("id")],
    }


def _build_source_record(claim: dict, result: dict, query: dict, provider: str = "unknown") -> dict | None:
    url = result.get("url", "")
    if not url:
        return None

    title = str(result.get("title", "Untitled source")).strip()
    raw_content = result.get("raw_content") or result.get("content") or ""
    content = _focus_content_for_claim(
        claim["claim"],
        raw_content,
        title=title,
        max_chars=2200,
    )
    focus_claim_text = _claim_focus_text(claim["claim"])
    evidence_passages = extract_evidence_passages(
        focus_claim_text,
        content,
        title=title,
        max_passages=3,
    )
    snippet = (
        evidence_passages[0]["text"]
        if evidence_passages
        else extract_best_snippet(focus_claim_text, content, title=title)
    )
    domain = extract_domain(url)
    source_type = classify_source_type(domain)
    source_origin_profile = infer_source_origin(
        claim["claim"],
        domain,
        url=url,
        source_type=source_type,
    )
    authority_score = domain_authority_score(domain)
    relevance_score = compute_relevance_score(claim["claim"], title, snippet, content)
    recency_score = compute_recency_score(result.get("published_date"))
    overall_score = compute_overall_source_score(
        authority_score,
        relevance_score,
        recency_score,
        recency_sensitive=bool(claim.get("time_sensitive", False)),
    )
    best_passage_score = max(
        (float(passage.get("score", 0.0) or 0.0) for passage in evidence_passages),
        default=0.0,
    )
    if not evidence_passages and relevance_score < 0.5:
        return None
    if evidence_passages and best_passage_score < 0.5 and relevance_score < 0.5:
        return None

    source_snapshot = _source_snapshot(url, title, content, evidence_passages)

    return {
        "title": title,
        "url": url,
        "content": content[:700],
        "published_date": result.get("published_date", "unknown"),
        "published_label": format_date_label(result.get("published_date")),
        "domain": domain,
        "source_type": source_type,
        "source_origin": source_origin_profile["source_origin"],
        "source_origin_score": source_origin_profile["source_origin_score"],
        "primary_preferred": bool(source_origin_profile["primary_preferred"]),
        "independence_key": source_origin_profile["independence_key"],
        "snippet": snippet,
        "evidence_passages": evidence_passages,
        "authority_score": round(authority_score, 2),
        "relevance_score": round(relevance_score, 2),
        "recency_score": round(recency_score, 2),
        "overall_score": round(overall_score, 2),
        "query_objective": query.get("objective", "direct"),
        "query_phase": query.get("phase", "primary"),
        "source_snapshot": source_snapshot,
        "provider": provider,
        "source_intelligence": {
            **source_origin_profile,
            "source_origin_label": source_origin_label(source_origin_profile["source_origin"]),
        },
    }


def _seed_source_article(claim: dict, candidate_sources: dict[str, dict]) -> None:
    source_url = str(claim.get("source_url", "") or "").strip()
    source_text = str(claim.get("source_text", "") or "").strip()
    if not source_url or not source_text:
        return

    source = _build_source_record(
        claim,
        {
            "url": source_url,
            "title": _source_article_title(claim),
            "raw_content": source_text,
            "published_date": "unknown",
        },
        {
            "objective": "source_context",
            "phase": "source",
            "planner": "source",
        },
    )
    if source is None:
        return

    candidate_sources[normalize_url(source["url"])] = source


async def _execute_query_batch(
    claim: dict,
    queries: list[dict],
    candidate_sources: dict[str, dict],
    progress_callback: Optional[Callable[[dict], Any]] = None,
) -> tuple[list[str], list[str]]:
    query_errors = []
    empty_authoritative_queries = []

    async def _process_query(query: dict):
        if progress_callback:
            try:
                await progress_callback(
                    {
                        "type": "query_start",
                        "claim_id": claim.get("id"),
                        "query": query.get("query"),
                        "objective": query.get("objective"),
                        "phase": query.get("phase"),
                    }
                )
            except Exception:
                pass

        provider_attempts = []
        effective_attempt = None
        any_results = False

        results_from_providers = await _search_query_provider_attempts(
            query["query"],
            objective=str(query.get("objective", "direct") or "direct"),
            claim_time_sensitive=bool(claim.get("time_sensitive", False)),
        )

        query_had_error = False
        for attempt in results_from_providers:
            normalized_results = attempt["results"]
            any_results = any_results or bool(normalized_results)
            added_source_count = 0

            if attempt.get("error"):
                query_errors.append(str(attempt["error"]))
                query_had_error = True

            for result in normalized_results:
                if not _result_matches_query_constraints(result, query):
                    continue

                source = _build_source_record(
                    claim,
                    result,
                    query,
                    provider=attempt.get("provider", "unknown"),
                )
                if source is None:
                    continue

                normalized = normalize_url(source["url"])
                existing = candidate_sources.get(normalized)
                if existing is None or source["overall_score"] > existing["overall_score"]:
                    if existing is None:
                        added_source_count += 1
                    candidate_sources[normalized] = source

            provider_attempt = {
                "provider": attempt["provider"],
                "status": "error" if attempt.get("error") else ("ok" if normalized_results else "empty"),
                "result_count": len(normalized_results),
                "added_source_count": added_source_count,
                "fallback_used": bool(attempt.get("fallback_used")),
            }
            if attempt.get("warning"):
                provider_attempt["warning"] = attempt["warning"]
            if attempt.get("error"):
                provider_attempt["error"] = attempt["error"]
            provider_attempts.append(provider_attempt)

            if added_source_count > 0:
                if effective_attempt is None or provider_attempt["status"] == "ok":
                    effective_attempt = provider_attempt
            if normalized_results and effective_attempt is None:
                effective_attempt = provider_attempt

        if effective_attempt is None and provider_attempts:
            effective_attempt = provider_attempts[-1]

        query["provider_attempts"] = provider_attempts
        if effective_attempt is not None:
            prior_messages = [
                str(item.get("error") or item.get("warning") or "").strip()
                for item in provider_attempts
                if item is not effective_attempt and str(item.get("error") or item.get("warning") or "").strip()
            ]
            query["status"] = effective_attempt["status"]
            query["result_count"] = effective_attempt["result_count"]
            query["provider"] = effective_attempt["provider"]
            query["fallback_used"] = bool(effective_attempt.get("fallback_used"))
            query["added_source_count"] = effective_attempt["added_source_count"]
            
            warning_parts = [
                *prior_messages,
                *(
                    [str(effective_attempt["warning"]).strip()]
                    if str(effective_attempt.get("warning") or "").strip()
                    else []
                ),
            ]
            if warning_parts:
                query["warning"] = "; ".join(dict.fromkeys(warning_parts))
            if effective_attempt.get("error"):
                query["error"] = effective_attempt["error"]

        # Track evidence of absence for authoritative confirmation queries
        if (
            not any_results 
            and not query_had_error 
            and query.get("objective") == "authoritative"
            and ("site:" in query["query"] or "official" in query["query"].lower())
        ):
            empty_authoritative_queries.append(query["query"])

    await asyncio.gather(*[_process_query(q) for q in queries])
    return query_errors, empty_authoritative_queries


def _recovery_reasons(claim: dict, ranked_sources: list[dict]) -> list[str]:
    reasons = []
    top_source = ranked_sources[0] if ranked_sources else {}
    top_score = top_source.get("overall_score", 0.0)
    top_relevance = top_source.get("relevance_score", 0.0)
    distinct_domains = {source.get("domain", "") for source in ranked_sources if source.get("domain")}
    authoritative_count = sum(
        1 for source in ranked_sources if source.get("authority_score", 0.0) >= 0.82
    )
    grounded_count = sum(
        1
        for source in ranked_sources
        if (
            source.get("relevance_score", 0.0) >= MIN_RECOVERY_TOP_RELEVANCE
            or any(
                float(passage.get("score", 0.0) or 0.0) >= MIN_RECOVERY_TOP_RELEVANCE
                for passage in source.get("evidence_passages", []) or []
            )
        )
    )
    dated_count = sum(
        1 for source in ranked_sources if source.get("published_label") not in {"", None, "unknown"}
    )

    if (
        not claim.get("time_sensitive", False)
        and len(ranked_sources) >= MIN_RECOVERY_SOURCE_COUNT
        and len(distinct_domains) >= 2
        and grounded_count >= 2
        and top_score >= MIN_RECOVERY_TOP_SCORE
        and top_relevance >= MIN_RECOVERY_TOP_RELEVANCE
    ):
        return reasons

    if len(ranked_sources) < MIN_RECOVERY_SOURCE_COUNT:
        reasons.append("Sparse evidence coverage.")
    if ranked_sources and top_source.get("overall_score", 0.0) < MIN_RECOVERY_TOP_SCORE:
        reasons.append("Top evidence score or authority is too weak.")
    elif (
        ranked_sources
        and claim.get("time_sensitive", False)
        and top_source.get("authority_score", 0.0) < 0.6
    ):
        reasons.append("Top evidence score or authority is too weak.")
    if (
        ranked_sources 
        and top_source.get("relevance_score", 0.0) < MIN_RECOVERY_TOP_RELEVANCE
        and authoritative_count == 0
    ):
        reasons.append("Top evidence is only loosely matched and no authoritative sources found.")
    if ranked_sources and authoritative_count == 0 and claim.get("time_sensitive", False):
        reasons.append("No authoritative sources were retrieved for a time-sensitive claim.")
    if ranked_sources and len(distinct_domains) < 2 and len(ranked_sources) < 3:
        reasons.append("Evidence diversity is too narrow.")
    if claim.get("time_sensitive", False) and dated_count == 0:
        reasons.append("Time-sensitive claim has no dated evidence.")

    return reasons


def _build_heuristic_recovery_queries(
    claim: dict,
    attempted_queries: list[dict],
    ranked_sources: list[dict],
) -> list[dict]:
    claim_text = claim["claim"].strip()
    claim_type = str(claim.get("claim_type", "entity") or "entity")
    current_year = datetime.utcnow().year
    authoritative_count = sum(
        1 for source in ranked_sources if source.get("authority_score", 0.0) >= 0.82
    )
    dated_count = sum(
        1 for source in ranked_sources if source.get("published_label") not in {"", None, "unknown"}
    )
    top_score = ranked_sources[0].get("overall_score", 0.0) if ranked_sources else 0.0

    attempted = {str(query.get("query", "")).strip().lower() for query in attempted_queries}
    candidate_queries = _build_claim_specific_queries(
        claim,
        phase="recovery",
    ) + _build_source_context_queries(claim, phase="recovery")

    if claim_type == "numeric":
        candidate_queries.append(
            {
                "query": f"{claim_text} official statistics report dataset",
                "objective": "authoritative",
                "phase": "recovery",
                "planner": "heuristic",
            }
        )
    elif claim_type == "quote":
        candidate_queries.append(
            {
                "query": f'{claim_text} transcript official statement',
                "objective": "direct",
                "phase": "recovery",
                "planner": "heuristic",
            }
        )
    else:
        candidate_queries.append(
            {
                "query": f'"{claim_text}" source evidence',
                "objective": "direct",
                "phase": "recovery",
                "planner": "heuristic",
            }
        )

    if authoritative_count == 0 or top_score < MIN_RECOVERY_TOP_SCORE:
        candidate_queries.append(
            {
                "query": f"{claim_text} official site government university organization",
                "objective": "authoritative",
                "phase": "recovery",
                "planner": "heuristic",
            }
        )

    if claim.get("time_sensitive", False) or dated_count == 0:
        candidate_queries.append(
            {
                "query": f"{claim_text} {current_year} latest official update",
                "objective": "recency",
                "phase": "recovery",
                "planner": "heuristic",
            }
        )
    else:
        candidate_queries.append(
            {
                "query": f"{claim_text} contradiction fact check context",
                "objective": "recency",
                "phase": "recovery",
                "planner": "heuristic",
            }
        )

    return _dedupe_queries(candidate_queries, seen_queries=attempted)[:4]


def _build_recovery_queries(
    claim: dict,
    attempted_queries: list[dict],
    ranked_sources: list[dict],
) -> list[dict]:
    return _build_heuristic_recovery_queries(claim, attempted_queries, ranked_sources)


async def _plan_recovery_queries(
    claim: dict,
    attempted_queries: list[dict],
    ranked_sources: list[dict],
    recovery_reason: list[str],
) -> tuple[list[dict], dict]:
    heuristic_queries = _build_recovery_queries(claim, attempted_queries, ranked_sources)
    if not recovery_reason:
        return [], {
            "mode": "not_needed",
            "reasoning": "",
            "fallback_used": False,
        }

    if not ranked_sources:
        return heuristic_queries, {
            "mode": "heuristic",
            "reasoning": "No sources were retrieved in the first pass, so deterministic recovery queries were used.",
            "fallback_used": bool(heuristic_queries),
        }

    if llm is None:
        return heuristic_queries, {
            "mode": "heuristic",
            "reasoning": llm_descriptor.issue or "Recovery planner unavailable, so heuristic recovery queries were used.",
            "fallback_used": bool(heuristic_queries),
        }

    attempted_lines = "\n".join(
        f"- {query.get('phase', 'primary')}: {query.get('query', '')}"
        for query in attempted_queries
    ) or "- none"
    evidence_lines = "\n".join(
        f"- {source.get('title', 'Untitled source')} | {source.get('domain', 'unknown')} | "
        f"score={source.get('overall_score', 0.0)} | relevance={source.get('relevance_score', 0.0)} | "
        f"date={source.get('published_label', 'unknown')}"
        for source in ranked_sources[:4]
    ) or "- no sources"
    summary = summarize_retrieval(ranked_sources)
    user_message = (
        f"Claim: {claim['claim']}\n"
        f"Claim type: {claim.get('claim_type', 'entity')}\n"
        f"Time sensitive: {claim.get('time_sensitive', False)}\n"
        f"Recovery triggers:\n- " + "\n- ".join(recovery_reason) + "\n\n"
        f"Attempted queries:\n{attempted_lines}\n\n"
        f"Retrieval summary:\n"
        f"- sources: {summary.get('source_count', 0)}\n"
        f"- authoritative: {summary.get('authoritative_count', 0)}\n"
        f"- dated: {summary.get('dated_count', 0)}\n"
        f"- distinct domains: {summary.get('distinct_domain_count', 0)}\n"
        f"- freshest date: {summary.get('freshest_date', 'unknown')}\n\n"
        f"Evidence snapshot:\n{evidence_lines}"
    )

    try:
        async with _get_retriever_llm_lock():
            response = await llm.ainvoke(
                [
                    SystemMessage(content=RECOVERY_SYSTEM_PROMPT),
                    HumanMessage(content=user_message),
                ]
            )
        parsed = _parse_json_object(
            response.content if isinstance(response.content, str) else str(response.content)
        )
    except Exception as exc:
        return heuristic_queries, {
            "mode": "heuristic_fallback",
            "reasoning": f"Recovery planner failed, so heuristic recovery queries were used. {exc}",
            "fallback_used": bool(heuristic_queries),
        }

    decision = str(parsed.get("decision", "search")).strip().lower()
    reasoning = str(parsed.get("reasoning", "")).strip()
    planned_queries = []
    seen = {
        str(query.get("query", "")).strip().lower()
        for query in attempted_queries
        if str(query.get("query", "")).strip()
    }

    for item in parsed.get("queries", []):
        query_text = str(item.get("query", "")).strip()
        query_key = query_text.lower()
        if not query_text or query_key in seen:
            continue
        if _query_overlap_score(query_text, claim["claim"]) < 0.2:
            continue
        seen.add(query_key)
        planned_queries.append(
            {
                "query": query_text,
                "objective": _normalize_objective(item.get("objective")),
                "phase": "recovery",
                "planner": "llm",
            }
        )

    if decision == "stop":
        if heuristic_queries:
            return heuristic_queries, {
                "mode": "heuristic_after_llm_stop",
                "reasoning": reasoning or "The recovery planner declined another search, but deterministic recovery queries were still used because evidence remained weak.",
                "fallback_used": True,
            }
        return [], {
            "mode": "llm_stop",
            "reasoning": reasoning or "The recovery planner judged the first-pass evidence sufficient.",
            "fallback_used": False,
        }

    if planned_queries:
        return planned_queries[:4], {
            "mode": "llm_planner",
            "reasoning": reasoning or "The recovery planner proposed another search round.",
            "fallback_used": False,
        }

    return heuristic_queries, {
        "mode": "heuristic_fallback",
        "reasoning": reasoning or "The recovery planner did not return usable queries, so heuristic recovery queries were used.",
        "fallback_used": bool(heuristic_queries),
    }


async def retrieve_evidence(
    claim: dict,
    progress_callback: Optional[Callable[[dict], Any]] = None,
) -> dict:
    try:
        query_variants = await _generate_queries(claim)
        candidate_sources = {}
        _seed_source_article(claim, candidate_sources)
        
        all_empty_authoritative = []
        query_errors, empty_auth = await _execute_query_batch(
            claim, query_variants, candidate_sources, progress_callback=progress_callback
        )
        all_empty_authoritative.extend(empty_auth)

        ranked_sources = _select_diverse_sources(claim, list(candidate_sources.values()))
        recovery_reason = _recovery_reasons(claim, ranked_sources)
        recovery_queries: list[dict] = []
        recovery_plan = {
            "mode": "not_needed",
            "reasoning": "",
            "fallback_used": False,
        }

        if recovery_reason:
            recovery_queries, recovery_plan = await _plan_recovery_queries(
                claim,
                query_variants,
                ranked_sources,
                recovery_reason,
            )
            if recovery_queries:
                query_variants.extend(recovery_queries)
                errs, empty_auth = await _execute_query_batch(
                    claim, recovery_queries, candidate_sources, progress_callback=progress_callback
                )
                query_errors.extend(errs)
                all_empty_authoritative.extend(empty_auth)
                
                ranked_sources = _select_diverse_sources(claim, list(candidate_sources.values()))
                remaining_recovery_reason = _recovery_reasons(claim, ranked_sources)
                if remaining_recovery_reason and recovery_plan["mode"] in {
                    "llm_planner",
                    "llm_stop",
                    "heuristic_after_llm_stop",
                }:
                    heuristic_followup = _build_heuristic_recovery_queries(
                        claim,
                        query_variants,
                        ranked_sources,
                    )
                    if heuristic_followup:
                        query_variants.extend(heuristic_followup)
                        recovery_queries.extend(heuristic_followup)
                        errs, empty_auth = await _execute_query_batch(
                            claim,
                            heuristic_followup,
                            candidate_sources,
                            progress_callback=progress_callback,
                        )
                        query_errors.extend(errs)
                        all_empty_authoritative.extend(empty_auth)
                        
                        ranked_sources = _select_diverse_sources(claim, list(candidate_sources.values()))
                        recovery_plan = {
                            "mode": "heuristic_after_llm",
                            "reasoning": (
                                "LLM-planned recovery did not produce strong enough evidence, so deterministic recovery queries were added."
                            ),
                            "fallback_used": True,
                        }

        for index, source in enumerate(ranked_sources, start=1):
            source["id"] = f"S{index}"

        retrieval_summary = summarize_retrieval(ranked_sources)
        retrieval_summary["query_attempt_count"] = len(query_variants)
        retrieval_summary["failed_query_count"] = sum(
            1 for query in query_variants if query.get("status") == "error"
        )
        retrieval_summary["recovery_triggered"] = bool(recovery_queries)
        retrieval_summary["recovery_query_count"] = len(recovery_queries)
        retrieval_summary["recovery_reason"] = recovery_reason
        retrieval_summary["recovery_strategy"] = recovery_plan["mode"]
        retrieval_summary["recovery_planner_notes"] = recovery_plan["reasoning"]
        retrieval_summary["recovery_fallback_used"] = bool(recovery_plan["fallback_used"])

        return {
            "claim_id": claim["id"],
            "query_used": query_variants[0]["query"] if query_variants else "",
            "query_variants": query_variants,
            "retrieval_summary": retrieval_summary,
            "sources": ranked_sources,
            "empty_authoritative_queries": all_empty_authoritative,
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
                "dated_count": 0,
                "distinct_domain_count": 0,
                "freshest_date": "unknown",
                "domains": [],
                "query_attempt_count": 0,
                "failed_query_count": 0,
                "recovery_triggered": False,
                "recovery_query_count": 0,
                "recovery_reason": [],
                "recovery_strategy": "failed",
                "recovery_planner_notes": "",
                "recovery_fallback_used": False,
            },
            "sources": [],
            "error": str(exc),
        }
