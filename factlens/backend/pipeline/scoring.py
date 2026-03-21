from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urlparse, urlunparse


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
}

KNOWN_DOMAIN_SCORES = {
    "apnews.com": 0.92,
    "bbc.com": 0.9,
    "britannica.com": 0.86,
    "cdc.gov": 0.99,
    "ec.europa.eu": 0.96,
    "factcheck.org": 0.91,
    "fda.gov": 0.99,
    "ft.com": 0.89,
    "nature.com": 0.94,
    "nasa.gov": 0.99,
    "nih.gov": 0.99,
    "npr.org": 0.88,
    "nytimes.com": 0.88,
    "reuters.com": 0.94,
    "science.org": 0.93,
    "snopes.com": 0.87,
    "statista.com": 0.72,
    "theguardian.com": 0.87,
    "un.org": 0.98,
    "washingtonpost.com": 0.88,
    "webmd.com": 0.74,
    "who.int": 0.99,
    "wikipedia.org": 0.74,
    "worldbank.org": 0.96,
}

SOCIAL_HOSTS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "reddit.com",
    "tiktok.com",
    "x.com",
    "youtube.com",
}

NEWS_HOSTS = {
    "apnews.com",
    "bbc.com",
    "ft.com",
    "npr.org",
    "nytimes.com",
    "reuters.com",
    "theguardian.com",
    "washingtonpost.com",
}

REFERENCE_HOSTS = {
    "britannica.com",
    "factcheck.org",
    "snopes.com",
    "statista.com",
    "wikipedia.org",
}

TIME_SENSITIVE_HINTS = {
    "current",
    "currently",
    "latest",
    "recent",
    "recently",
    "today",
    "yesterday",
    "this year",
    "this month",
    "this week",
    "now",
    "president",
    "prime minister",
    "ceo",
    "ranking",
    "ranked",
    "price",
    "worth",
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def extract_domain(url: str) -> str:
    parsed = urlparse(url or "")
    domain = parsed.netloc.lower()
    return domain[4:] if domain.startswith("www.") else domain


def normalize_url(url: str) -> str:
    parsed = urlparse(url or "")
    normalized = parsed._replace(query="", fragment="")
    path = normalized.path.rstrip("/")
    return urlunparse(
        (
            normalized.scheme or "https",
            normalized.netloc.lower(),
            path,
            "",
            "",
            "",
        )
    )


def classify_claim_type(claim: str) -> str:
    lowered = (claim or "").lower()

    if '"' in lowered or "“" in lowered or "”" in lowered:
        return "quote"
    if re.search(r"\b(\d+(\.\d+)?%|\d[\d,]*(\.\d+)?|million|billion|trillion)\b", lowered):
        return "numeric"
    if re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
        r"\d{4}|today|yesterday|tomorrow)\b",
        lowered,
    ):
        return "date"
    if re.search(r"\b(more than|less than|higher than|lower than|ranked|largest|smallest|compared to)\b", lowered):
        return "comparison"
    if re.search(r"\b(because|caused|causes|led to|results in|due to|triggered)\b", lowered):
        return "causal"
    if re.search(r"\b(said|announced|stated|claimed|according to)\b", lowered):
        return "quote"
    return "entity"


def infer_time_sensitivity(claim: str) -> bool:
    lowered = (claim or "").lower()
    return any(hint in lowered for hint in TIME_SENSITIVE_HINTS) or bool(
        re.search(r"\b(20\d{2}|19\d{2})\b", lowered)
    )


def classify_source_type(domain: str) -> str:
    if not domain:
        return "unknown"
    if domain.endswith(".gov"):
        return "government"
    if domain.endswith(".edu"):
        return "academic"
    if any(domain == host or domain.endswith(f".{host}") for host in SOCIAL_HOSTS):
        return "social"
    if any(domain == host or domain.endswith(f".{host}") for host in REFERENCE_HOSTS):
        return "reference"
    if any(domain == host or domain.endswith(f".{host}") for host in NEWS_HOSTS):
        return "news"
    if domain.endswith(".org"):
        return "organization"
    if domain.endswith(".int"):
        return "international"
    if domain.endswith(".com"):
        return "commercial"
    return "web"


def domain_authority_score(domain: str) -> float:
    if not domain:
        return 0.3

    for host, score in KNOWN_DOMAIN_SCORES.items():
        if domain == host or domain.endswith(f".{host}"):
            return score

    source_type = classify_source_type(domain)
    defaults = {
        "government": 0.97,
        "academic": 0.91,
        "international": 0.94,
        "reference": 0.76,
        "news": 0.82,
        "organization": 0.72,
        "commercial": 0.55,
        "social": 0.22,
        "web": 0.48,
        "unknown": 0.3,
    }
    return defaults.get(source_type, 0.45)


def _overlap_ratio(claim_tokens: set[str], text: str) -> float:
    if not claim_tokens:
        return 0.0
    text_tokens = set(tokenize(text))
    if not text_tokens:
        return 0.0
    return len(claim_tokens & text_tokens) / len(claim_tokens)


def _numeric_alignment(claim: str, text: str) -> float:
    claim_numbers = set(re.findall(r"\d+(?:\.\d+)?", claim or ""))
    if not claim_numbers:
        return 0.5
    text_numbers = set(re.findall(r"\d+(?:\.\d+)?", text or ""))
    return len(claim_numbers & text_numbers) / len(claim_numbers) if text_numbers else 0.0


def extract_best_snippet(claim: str, content: str, title: str = "", max_chars: int = 260) -> str:
    candidate_text = _normalized_text(content or title)
    if not candidate_text:
        return ""

    claim_tokens = set(tokenize(claim))
    parts = [
        _normalized_text(part)
        for part in re.split(r"(?<=[.!?])\s+|\n+|(?<=:)\s+", candidate_text)
        if _normalized_text(part)
    ]
    if not parts:
        parts = [candidate_text]

    def score(part: str) -> float:
        overlap = _overlap_ratio(claim_tokens, part)
        exact_bonus = 0.15 if (claim or "").lower() in part.lower() else 0.0
        numeric_bonus = 0.2 * _numeric_alignment(claim, part)
        return overlap + exact_bonus + numeric_bonus

    best = max(parts, key=score)
    if len(best) <= max_chars:
        return best

    truncated = best[: max_chars - 3].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{truncated}..."


def compute_relevance_score(claim: str, title: str, snippet: str, content: str) -> float:
    claim_tokens = set(tokenize(claim))
    if not claim_tokens:
        return 0.0

    snippet_overlap = _overlap_ratio(claim_tokens, snippet)
    title_overlap = _overlap_ratio(claim_tokens, title)
    content_overlap = _overlap_ratio(claim_tokens, content)
    numeric_alignment = _numeric_alignment(claim, f"{title} {snippet} {content}")
    phrase_bonus = 1.0 if (claim or "").lower() in f"{title} {content}".lower() else 0.0

    return clamp(
        (0.45 * snippet_overlap)
        + (0.2 * title_overlap)
        + (0.2 * content_overlap)
        + (0.1 * numeric_alignment)
        + (0.05 * phrase_bonus)
    )


def parse_published_date(value: object) -> Optional[datetime]:
    if value in (None, "", "unknown"):
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    formats = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%B %d, %Y",
        "%d %B %Y",
        "%b %d, %Y",
    )

    for date_format in formats:
        try:
            parsed = datetime.strptime(normalized, date_format)
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    match = re.search(r"(20\d{2}|19\d{2})-(\d{2})-(\d{2})", normalized)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return datetime(year, month, day, tzinfo=timezone.utc)

    year_match = re.search(r"\b(20\d{2}|19\d{2})\b", normalized)
    if year_match:
        return datetime(int(year_match.group(1)), 1, 1, tzinfo=timezone.utc)

    return None


def compute_recency_score(published_date: object) -> float:
    parsed = parse_published_date(published_date)
    if parsed is None:
        return 0.45

    age_days = max((datetime.now(timezone.utc) - parsed).days, 0)
    if age_days <= 7:
        return 0.98
    if age_days <= 30:
        return 0.9
    if age_days <= 180:
        return 0.76
    if age_days <= 365:
        return 0.63
    if age_days <= 730:
        return 0.5
    return 0.34


def format_date_label(published_date: object) -> str:
    parsed = parse_published_date(published_date)
    return parsed.date().isoformat() if parsed else "unknown"


def compute_overall_source_score(
    authority_score: float, relevance_score: float, recency_score: float
) -> float:
    return clamp((0.42 * authority_score) + (0.4 * relevance_score) + (0.18 * recency_score))


def normalize_stance(value: object) -> str:
    normalized = str(value or "IRRELEVANT").strip().upper().replace("-", "_").replace(" ", "_")
    if normalized in {"SUPPORTS", "SUPPORTED"}:
        normalized = "SUPPORT"
    if normalized in {"CONTRADICTS", "CONFLICTS", "REFUTE"}:
        normalized = "CONFLICT"
    return normalized if normalized in {"SUPPORT", "CONFLICT", "MIXED", "IRRELEVANT"} else "IRRELEVANT"


def summarize_retrieval(sources: Iterable[dict]) -> dict:
    source_list = list(sources)
    authoritative = [source for source in source_list if source.get("authority_score", 0) >= 0.82]
    recent = [source for source in source_list if source.get("recency_score", 0) >= 0.76]
    dates = [parse_published_date(source.get("published_date")) for source in source_list]
    valid_dates = [date for date in dates if date is not None]
    dated_count = sum(1 for date in dates if date is not None)

    return {
        "source_count": len(source_list),
        "authoritative_count": len(authoritative),
        "recent_count": len(recent),
        "dated_count": dated_count,
        "distinct_domain_count": len(
            {source.get("domain", "") for source in source_list if source.get("domain")}
        ),
        "freshest_date": max(valid_dates).date().isoformat() if valid_dates else "unknown",
        "domains": sorted({source.get("domain", "") for source in source_list if source.get("domain")}),
    }


def calibrate_verdict(
    assessments: Iterable[dict],
    sources: Iterable[dict],
    claim_time_sensitive: bool = False,
    claim_requires_recency: bool = False,
) -> dict:
    sources_by_id = {source["id"]: dict(source) for source in sources}
    support_score = 0.0
    conflict_score = 0.0
    relevant_sources = []
    support_items = []
    conflict_items = []
    mixed_items = []
    neutral_items = []

    for assessment in assessments:
        source = sources_by_id.get(assessment.get("source_id"))
        if not source:
            continue

        stance = normalize_stance(assessment.get("stance"))
        strength = clamp(float(assessment.get("strength", 0.5) or 0.5))
        source["stance"] = stance
        source["strength"] = round(strength, 2)
        source["assessment_summary"] = assessment.get("summary", "")
        source["snippet_used"] = assessment.get("snippet_used") or source.get("snippet", "")
        weighted_score = source.get("overall_score", 0.0) * (0.35 + (0.65 * strength))

        if stance == "SUPPORT":
            support_score += weighted_score
            support_items.append(source)
            relevant_sources.append(source)
        elif stance == "CONFLICT":
            conflict_score += weighted_score
            conflict_items.append(source)
            relevant_sources.append(source)
        elif stance == "MIXED":
            support_score += weighted_score * 0.55
            conflict_score += weighted_score * 0.45
            mixed_items.append(source)
            relevant_sources.append(source)
        else:
            neutral_items.append(source)

    used_ids = {source["id"] for source in relevant_sources + neutral_items}
    for source in sources_by_id.values():
        if source["id"] not in used_ids:
            source["stance"] = "IRRELEVANT"
            source["strength"] = 0.0
            neutral_items.append(source)

    relevant_count = len(relevant_sources)
    max_score = max(support_score, conflict_score)
    margin = abs(support_score - conflict_score)
    avg_quality = (
        sum(source.get("overall_score", 0.0) for source in relevant_sources) / relevant_count
        if relevant_count
        else 0.0
    )
    dated_relevant_count = sum(
        1 for source in relevant_sources if parse_published_date(source.get("published_date")) is not None
    )
    freshness = (
        max(source.get("recency_score", 0.45) for source in relevant_sources)
        if relevant_sources
        else 0.45
    )
    evidence_coverage = clamp(relevant_count / 4.0)
    clarity = clamp(margin / max(max_score, 1.0))
    conflict_detected = (
        (support_score >= 0.75 and conflict_score >= 0.75)
        or (bool(support_items) and bool(conflict_items))
        or (bool(conflict_items) and bool(mixed_items))
    )
    material_conflict = conflict_detected and min(support_score, conflict_score) >= 0.45
    recency_sensitive = claim_time_sensitive or claim_requires_recency
    lacks_temporal_grounding = recency_sensitive and (
        dated_relevant_count == 0 or freshness < 0.76
    )

    heuristic_flags = []
    if relevant_count == 0:
        heuristic_flags.append("No relevant evidence survived stance filtering.")
    if relevant_count < 2:
        heuristic_flags.append("The verdict relies on sparse evidence coverage.")
    if avg_quality < 0.62 and relevant_count:
        heuristic_flags.append("Most relevant sources were medium or low authority.")
    if material_conflict:
        heuristic_flags.append("Credible sources disagree on at least part of the claim.")
    if recency_sensitive and dated_relevant_count == 0:
        heuristic_flags.append("The claim appears time-sensitive but none of the relevant sources were date-stamped.")
    elif recency_sensitive and freshness < 0.76:
        heuristic_flags.append("The claim appears time-sensitive but the evidence is not recent enough.")

    if relevant_count == 0 or max_score < 0.65:
        verdict = "UNVERIFIABLE"
    elif lacks_temporal_grounding and material_conflict:
        verdict = "UNVERIFIABLE"
    elif lacks_temporal_grounding:
        verdict = "PARTIALLY_TRUE" if max_score >= 1.4 and not material_conflict else "UNVERIFIABLE"
    elif material_conflict:
        verdict = "PARTIALLY_TRUE"
    elif support_score >= 1.2 and conflict_score <= support_score * 0.25:
        verdict = "TRUE"
    elif conflict_score >= 1.2 and support_score <= conflict_score * 0.25:
        verdict = "FALSE"
    elif relevant_count >= 2 and (conflict_detected or margin < 0.55):
        verdict = "PARTIALLY_TRUE"
    else:
        verdict = "UNVERIFIABLE"

    confidence = (
        0.28
        + (0.24 * avg_quality)
        + (0.18 * evidence_coverage)
        + (0.17 * clarity)
        + (0.13 * freshness)
    )
    if material_conflict:
        confidence -= 0.18
    if verdict == "PARTIALLY_TRUE":
        confidence -= 0.08
    if verdict == "UNVERIFIABLE":
        confidence = min(confidence, 0.46)
    if lacks_temporal_grounding:
        confidence -= 0.18
    if relevant_count < 2:
        confidence -= 0.08
    confidence = clamp(confidence, 0.05, 0.97)

    if verdict in {"TRUE", "FALSE"} and relevant_count >= 2 and avg_quality >= 0.72 and not lacks_temporal_grounding:
        confidence = max(confidence, 0.68)

    return {
        "verdict": verdict,
        "confidence": round(confidence, 2),
        "conflict_detected": conflict_detected,
        "support_score": round(support_score, 2),
        "conflict_score": round(conflict_score, 2),
        "confidence_breakdown": {
            "evidence_coverage": round(evidence_coverage, 2),
            "source_quality": round(avg_quality, 2),
            "freshness": round(freshness, 2),
            "clarity": round(clarity, 2),
            "support_score": round(support_score, 2),
            "conflict_score": round(conflict_score, 2),
        },
        "supporting_evidence": support_items,
        "conflicting_evidence": conflict_items,
        "mixed_evidence": mixed_items,
        "neutral_evidence": neutral_items,
        "risk_flags": heuristic_flags,
    }
