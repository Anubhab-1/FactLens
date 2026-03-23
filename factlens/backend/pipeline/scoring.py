from __future__ import annotations

from collections import Counter
import hashlib
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
    "aljazeera.com": 0.83,
    "bbc.com": 0.90,
    "britannica.com": 0.86,
    "cdc.gov": 0.99,
    "ec.europa.eu": 0.96,
    "economist.com": 0.91,
    "factcheck.org": 0.91,
    "fda.gov": 0.99,
    "ft.com": 0.89,
    "hindustandtimes.com": 0.78,
    "indianexpress.com": 0.84,
    "ndtv.com": 0.78,
    "nature.com": 0.94,
    "nasa.gov": 0.99,
    "nih.gov": 0.99,
    "npr.org": 0.88,
    "nytimes.com": 0.88,
    "pib.gov.in": 0.96,
    "reuters.com": 0.94,
    "science.org": 0.93,
    "scroll.in": 0.76,
    "snopes.com": 0.87,
    "statista.com": 0.72,
    "theatlantic.com": 0.87,
    "thehindu.com": 0.86,
    "theprint.in": 0.75,
    "theguardian.com": 0.87,
    "thewire.in": 0.75,
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
    "aljazeera.com",
    "apnews.com",
    "bbc.com",
    "economist.com",
    "ft.com",
    "hindustandtimes.com",
    "indianexpress.com",
    "ndtv.com",
    "npr.org",
    "nytimes.com",
    "reuters.com",
    "scroll.in",
    "theatlantic.com",
    "thehindu.com",
    "theprint.in",
    "theguardian.com",
    "thewire.in",
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
    "as of",
    "updated",
    "modified",
    "revised",
    "amended",
    "effective",
    "expires",
    "deadline",
    "scheduled",
    "planned",
    "expected",
    "forecast",
    "projected",
    "estimated",
    "approximate",
    "roughly",
    "about",
    "around",
    "approximately",
    "circa",
    "sometime",
    "sometime in",
    "sometime during",
}

EXACT_VALUE_HINTS = {
    "abbreviation",
    "acronym",
    "code",
    "codename",
    "formula",
    "initialism",
    "initials",
    "symbol",
    "ticker",
}

MULTIPART_PUBLIC_SUFFIXES = {
    "ac.uk",
    "co.in",
    "co.jp",
    "co.uk",
    "com.au",
    "com.br",
    "com.cn",
    "com.mx",
    "edu.au",
    "gov.au",
    "gov.in",
    "gov.uk",
    "org.au",
    "org.in",
    "org.uk",
}

ENTITY_TOKEN_STOPWORDS = STOPWORDS | {
    "approved",
    "budget",
    "capital",
    "ceo",
    "chemical",
    "chief",
    "city",
    "claim",
    "current",
    "currently",
    "evidence",
    "executive",
    "formula",
    "government",
    "is",
    "largest",
    "latest",
    "leader",
    "leadership",
    "minister",
    "natural",
    "ocean",
    "official",
    "officer",
    "one",
    "president",
    "prime",
    "recent",
    "satellite",
    "source",
    "statement",
    "symbol",
    "the",
    "update",
}

OFFICIAL_SOURCE_TYPES = {"government", "academic", "international"}
PRIMARY_PREFERRED_ORIGINS = {"official", "first_party", "reference"}
SOURCE_ORIGIN_SCORES = {
    "official": 1.0,
    "first_party": 0.92,
    "reference": 0.8,
    "secondary": 0.64,
    "web": 0.5,
    "social": 0.2,
    "unknown": 0.35,
}
OFFICIAL_PATH_HINTS = {
    "/about",
    "/company",
    "/facts",
    "/investor",
    "/leadership",
    "/newsroom",
    "/official",
    "/press",
    "/team",
}
KNOWN_NETWORK_GROUPS = {
    "abcnews.go.com": "abcnews",
    "apnews.com": "apnews",
    "bbc.co.uk": "bbc",
    "bbc.com": "bbc",
    "go.com": "abcnews",
    "reuters.com": "reuters",
    "wikimedia.org": "wikipedia",
    "wikipedia.org": "wikipedia",
}
DEBUNKING_MARKERS = (
    " false ",
    " not true ",
    " incorrect ",
    " inaccurate ",
    " debunk",
    " refut",
    " hoax ",
    " myth ",
    " fake ",
    " fabricated ",
    " denied ",
    " deny ",
)
SCOPE_QUALIFIER_MARKERS = (
    " partly ",
    " partial ",
    " only ",
    " some ",
    " subset ",
    " in some cases ",
    " not directly ",
    " under certain conditions ",
    " qualified ",
    " context ",
    " caveat ",
)
CONTRADICTION_TYPE_META = {
    "direct_debunking": {
        "label": "Direct debunking",
        "summary": "Conflicting sources explicitly call the claim false, fabricated, or debunked.",
    },
    "entity_mismatch": {
        "label": "Entity mismatch",
        "summary": "The disagreement centers on a different person, place, organization, or named entity.",
    },
    "metric_mismatch": {
        "label": "Metric mismatch",
        "summary": "Supporting and conflicting sources disagree on the core numeric value or measurement.",
    },
    "date_drift": {
        "label": "Date drift",
        "summary": "The evidence clusters around materially different dates or time windows.",
    },
    "scope_mismatch": {
        "label": "Scope mismatch",
        "summary": "Sources agree on part of the claim but differ on qualifiers, conditions, or causal scope.",
    },
}
ENTITY_MISMATCH_IGNORE_TOKENS = {
    "analysis",
    "earlier",
    "estimate",
    "estimates",
    "government",
    "latest",
    "market",
    "official",
    "officials",
    "report",
    "reporting",
    "source",
    "sources",
    "statement",
    "updated",
}
ALIAS_EQUIVALENCE_GROUPS = (
    ("World Health Organization", "WHO"),
    ("United Nations", "UN"),
    ("European Union", "EU"),
    ("United States", "US", "U.S.", "USA", "U.S.A."),
    ("United Kingdom", "UK", "U.K."),
    ("United Arab Emirates", "UAE", "U.A.E."),
    ("Centers for Disease Control and Prevention", "CDC"),
    ("Food and Drug Administration", "FDA"),
    ("National Aeronautics and Space Administration", "NASA"),
    ("International Monetary Fund", "IMF"),
    ("North Atlantic Treaty Organization", "NATO"),
    ("World Trade Organization", "WTO"),
    ("public health emergency of international concern", "PHEIC"),
    ("chief executive officer", "CEO"),
    ("prime minister", "PM"),
)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _alias_normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(value or "").lower())).strip()


def _marker_text(value: str) -> str:
    return f" {_alias_normalized_text(value)} "


def _stable_hash(*parts: object, prefix: str = "") -> str:
    digest = hashlib.sha1(
        "||".join(_normalized_text(str(part or "")) for part in parts).encode("utf-8")
    ).hexdigest()[:12]
    return f"{prefix}{digest}" if prefix else digest


def _raw_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text or "")


def tokenize(text: str, *, preserve_terms: set[str] | None = None) -> list[str]:
    preserved = {term.lower() for term in (preserve_terms or set()) if term}
    return [
        token
        for raw_token in _raw_tokens(text)
        for token in [raw_token.lower()]
        if (
            (token in preserved and token not in STOPWORDS)
            or (len(token) > 2 and token not in STOPWORDS)
        )
    ]


def _claim_has_exact_value_hint(claim: str) -> bool:
    lowered = (claim or "").lower()
    return any(hint in lowered for hint in EXACT_VALUE_HINTS)


def _claim_exact_terms(claim: str) -> set[str]:
    if not _claim_has_exact_value_hint(claim):
        return set()

    return {
        token.lower()
        for token in _raw_tokens(claim)
        if token and len(token) <= 3 and token.lower() not in STOPWORDS
    }


def claim_alias_phrases(claim_text: str, *, max_aliases: int = 4) -> list[str]:
    normalized_claim = _alias_normalized_text(claim_text)
    if not normalized_claim:
        return []

    aliases: list[str] = []
    seen = {normalized_claim}

    def contains(alias: str) -> bool:
        candidate = _alias_normalized_text(alias)
        return bool(candidate) and f" {candidate} " in f" {normalized_claim} "

    def add(alias: str) -> None:
        normalized_alias = _alias_normalized_text(alias)
        if not normalized_alias or normalized_alias in seen:
            return
        seen.add(normalized_alias)
        aliases.append(alias)

    for group in ALIAS_EQUIVALENCE_GROUPS:
        if not any(contains(member) for member in group):
            continue
        if not contains(group[0]):
            add(group[0])
            continue
        for alias in group[1:]:
            if not contains(alias):
                add(alias)
                break
        if len(aliases) >= max_aliases:
            break

    return aliases[:max_aliases]


def _alias_pattern(alias: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in re.findall(r"[A-Za-z0-9]+", alias or "")]
    if not parts:
        return re.compile(r"$^")
    return re.compile(r"\b" + r"[\W_]+".join(parts) + r"\b", re.IGNORECASE)


def claim_alias_variants(claim_text: str, *, max_variants: int = 4) -> list[str]:
    normalized_claim = _alias_normalized_text(claim_text)
    if not normalized_claim:
        return []

    variants: list[str] = []
    seen = {normalized_claim}

    def add(candidate: str) -> None:
        normalized_candidate = _alias_normalized_text(candidate)
        if not normalized_candidate or normalized_candidate in seen:
            return
        seen.add(normalized_candidate)
        variants.append(candidate)

    for group in ALIAS_EQUIVALENCE_GROUPS:
        for index, member in enumerate(group):
            pattern = _alias_pattern(member)
            if not pattern.search(claim_text):
                continue
            if index == 0:
                for alias in group[1:]:
                    add(pattern.sub(alias, claim_text, count=1))
                    break
            else:
                add(pattern.sub(group[0], claim_text, count=1))
            if len(variants) >= max_variants:
                return variants[:max_variants]
            break

    return variants[:max_variants]


def _claim_text_variants(claim: str, *, max_variants: int = 4) -> list[str]:
    variants: list[str] = []
    seen: set[str] = set()
    for candidate in [claim, *claim_alias_variants(claim, max_variants=max_variants - 1)]:
        normalized_candidate = _alias_normalized_text(candidate)
        if not normalized_candidate or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        variants.append(candidate)
    return variants


def _variant_overlap_ratio(
    claim_variants: list[str],
    text: str,
    *,
    exact_terms: set[str] | None = None,
) -> float:
    text_tokens = set(tokenize(text, preserve_terms=exact_terms))
    if not text_tokens:
        return 0.0

    best = 0.0
    for variant in claim_variants:
        variant_tokens = set(tokenize(variant, preserve_terms=exact_terms))
        if not variant_tokens:
            continue
        best = max(best, len(variant_tokens & text_tokens) / len(variant_tokens))
    return best


def _variant_phrase_bonus(claim_variants: list[str], text: str) -> float:
    lowered_text = (text or "").lower()
    return 1.0 if any((variant or "").lower() in lowered_text for variant in claim_variants) else 0.0


def _claim_token_bundle(claim: str) -> tuple[set[str], set[str]]:
    exact_terms = _claim_exact_terms(claim)
    return set(tokenize(claim, preserve_terms=exact_terms)), exact_terms


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
    """
    Determine if a claim is time-sensitive (likely to change over time).
    Enhanced to better handle temporal ambiguity and provide more nuanced detection.
    """
    if not claim:
        return False
        
    lowered = claim.lower()
    
    # Check for explicit time-sensitive hints
    if any(hint in lowered for hint in TIME_SENSITIVE_HINTS):
        return True
    
    # Check for years (recent years are more likely to be time-sensitive)
    year_matches = re.findall(r"\b(20\d{2}|19\d{2})\b", lowered)
    if year_matches:
        # Recent years (last 5 years) are more likely to be time-sensitive
        current_year = datetime.now(timezone.utc).year
        for year_str in year_matches:
            year = int(year_str)
            if current_year - year <= 5:  # Within last 5 years
                return True
            # Also consider years that are very recent (like last year) as sensitive
            if current_year - year == 1:
                return True
    
    # Check for relative time phrases that indicate changeability
    relative_time_patterns = [
        r"\b(is|was|were|has been|have been|has|have)\s+(?:the\s+)?(?:current|latest|newest|most recent)\b",
        r"\b(just\s+)?(recently|lately)\s+(?:is|was|were|has|have)\b",
        r"\b(as\s+of\s+|since\s+|until\s+|till\s+|through\s+)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b(in\s+|during\s+|over\s+|throughout\s+)\s+(?:the\s+)?(?:past|last)\s+\d+\s+(?:day|week|month|year)s?\b",
        r"\b(upcoming|forthcoming|impending|pending|scheduled|planned|expected)\b",
        r"\b(breaking\s+news|developing\s+story|ongoing\s+|live\s+)\b",
    ]
    
    for pattern in relative_time_patterns:
        if re.search(pattern, lowered):
            return True
            
    # Check for volatile subjects that commonly change
    volatile_subjects = [
        "price", "stock", "share", "value", "cost", "rate", "percentage",
        "poll", "survey", "rating", "ranking", "standing", "position",
        "weather", "temperature", "forecast", "score", "result",
        "leader", "winner", "champion", "record", "best", "worst",
        "ceo", "president", "prime minister", "minister", "director",
        "head", "chief", "captain", "manager", "coach"
    ]
    
    for subject in volatile_subjects:
        if subject in lowered:
            # If it's a volatile subject and we have action verbs, likely time-sensitive
            action_verbs = ["is", "was", "were", "has", "have", "became", "equals", "equals"]
            if any(verb in lowered for verb in action_verbs):
                return True
    
    return False


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


def registered_domain(domain_or_url: str) -> str:
    value = str(domain_or_url or "").strip().lower()
    if not value:
        return ""

    domain = extract_domain(value) if "://" in value or "/" in value else value
    parts = [part for part in domain.split(".") if part]
    if len(parts) <= 2:
        return domain

    suffix = ".".join(parts[-2:])
    if suffix in MULTIPART_PUBLIC_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _normalized_domain(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    if not cleaned:
        return ""
    if "://" in cleaned or "/" in cleaned:
        return extract_domain(cleaned)
    return cleaned[4:] if cleaned.startswith("www.") else cleaned


def source_network_key(domain: str) -> str:
    normalized_domain = _normalized_domain(domain)
    if not normalized_domain:
        return ""

    registered = registered_domain(normalized_domain)
    for marker, group in KNOWN_NETWORK_GROUPS.items():
        if (
            normalized_domain == marker
            or normalized_domain.endswith(f".{marker}")
            or registered == marker
        ):
            return group
    return registered or normalized_domain


def _claim_identity_tokens(claim_text: str) -> set[str]:
    tokens = set()
    for raw_token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", claim_text or ""):
        normalized = raw_token.lower()
        if normalized in ENTITY_TOKEN_STOPWORDS:
            continue
        if raw_token[0].isupper() or len(normalized) >= 7:
            tokens.add(normalized)
    return tokens


def _domain_identity_tokens(domain: str) -> set[str]:
    normalized = registered_domain(domain)
    tokens = set()
    for raw_token in re.findall(r"[A-Za-z0-9]+", normalized.replace(".", " ")):
        token = raw_token.lower()
        if len(token) < 4 or token in {"com", "edu", "gov", "int", "net", "org"}:
            continue
        tokens.add(token)
    return tokens


def infer_source_origin(
    claim_text: str,
    domain: str,
    *,
    url: str = "",
    source_type: str | None = None,
) -> dict:
    normalized_domain = _normalized_domain(domain)
    source_type = source_type or classify_source_type(normalized_domain)
    network_key = source_network_key(normalized_domain)
    claim_tokens = _claim_identity_tokens(claim_text)
    domain_tokens = _domain_identity_tokens(normalized_domain)
    path_lower = urlparse(url or "").path.lower()
    has_official_path_cue = any(marker in path_lower for marker in OFFICIAL_PATH_HINTS)

    overlap_score = 0.0
    for claim_token in claim_tokens:
        for domain_token in domain_tokens:
            if claim_token == domain_token:
                overlap_score = max(overlap_score, 1.0)
            elif len(domain_token) >= 5 and (
                claim_token.startswith(domain_token) or domain_token.startswith(claim_token)
            ):
                overlap_score = max(overlap_score, 0.84)

    if source_type in OFFICIAL_SOURCE_TYPES:
        origin = "official"
        reason = "Government, academic, or international primary source."
    elif source_type == "reference":
        origin = "reference"
        reason = "Reference or fact-checking source."
    elif source_type in {"commercial", "organization"} and overlap_score >= 0.84:
        origin = "first_party"
        reason = "Domain appears to match the main entity in the claim."
    elif source_type == "news":
        origin = "secondary"
        reason = "Independent reporting source."
    elif source_type == "social":
        origin = "social"
        reason = "Social or user-generated source."
    elif source_type in {"commercial", "organization"}:
        origin = "secondary"
        reason = "Organization or company page without a strong first-party match."
    elif source_type == "web":
        origin = "web"
        reason = "General web source."
    else:
        origin = "unknown"
        reason = "Source origin could not be confidently classified."

    return {
        "source_origin": origin,
        "source_origin_score": round(SOURCE_ORIGIN_SCORES.get(origin, 0.35), 2),
        "primary_preferred": origin in PRIMARY_PREFERRED_ORIGINS,
        "independence_key": network_key or normalized_domain,
        "entity_overlap": round(overlap_score, 2),
        "official_path_hint": has_official_path_cue,
        "reason": reason,
    }


def source_origin_label(value: object) -> str:
    origin = str(value or "").strip().lower()
    if origin == "first_party":
        return "first-party"
    if origin == "official":
        return "official"
    if origin == "reference":
        return "reference"
    if origin == "secondary":
        return "secondary"
    if origin == "social":
        return "social"
    if origin == "web":
        return "web"
    return "unknown"


def _overlap_ratio(claim_tokens: set[str], text: str, *, exact_terms: set[str] | None = None) -> float:
    if not claim_tokens:
        return 0.0
    text_tokens = set(tokenize(text, preserve_terms=exact_terms))
    if not text_tokens:
        return 0.0
    return len(claim_tokens & text_tokens) / len(claim_tokens)


def _exact_term_alignment(exact_terms: set[str], text: str) -> float:
    if not exact_terms:
        return 0.0

    text_tokens = set(tokenize(text, preserve_terms=exact_terms))
    if not text_tokens:
        return 0.0

    return len(exact_terms & text_tokens) / len(exact_terms)


def _myth_aware_boost(text: str) -> float:
    lowered = (text or "").lower()
    myth_keywords = {
        "myth", "debunk", "falsehood", "misconception", "legend", 
        "popular belief", "contrary to", "actually", "in reality", "untrue",
        "hoax", "deepfake", "ai-generated", "fabricated", "conspiracy"
    }
    found = sum(1 for word in myth_keywords if word in lowered)
    if found >= 2:
        return 0.38
    if found >= 1:
        return 0.22
    return 0.0


def _numeric_alignment(claim: str, text: str) -> float:
    claim_numbers = set(re.findall(r"\d+(?:\.\d+)?", claim or ""))
    if not claim_numbers:
        return 0.0
    text_numbers = set(re.findall(r"\d+(?:\.\d+)?", text or ""))
    return len(claim_numbers & text_numbers) / len(claim_numbers) if text_numbers else 0.0


def extract_best_snippet(claim: str, content: str, title: str = "", max_chars: int = 260) -> str:
    candidate_text = _normalized_text(content or title)
    if not candidate_text:
        return ""

    claim_variants = _claim_text_variants(claim)
    _claim_tokens, exact_terms = _claim_token_bundle(claim)
    parts = [
        _normalized_text(part)
        for part in re.split(r"(?<=[.!?])\s+|\n+|(?<=:)\s+", candidate_text)
        if _normalized_text(part)
    ]
    if not parts:
        parts = [candidate_text]

    def score(part: str) -> float:
        overlap = _variant_overlap_ratio(claim_variants, part, exact_terms=exact_terms)
        exact_bonus = 0.15 * _variant_phrase_bonus(claim_variants, part)
        exact_term_bonus = 0.18 * _exact_term_alignment(exact_terms, part)
        numeric_bonus = 0.2 * _numeric_alignment(claim, part)
        return overlap + exact_bonus + exact_term_bonus + numeric_bonus

    best = max(parts, key=score)
    if len(best) <= max_chars:
        return best

    truncated = best[: max_chars - 3].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{truncated}..."


def extract_evidence_passages(
    claim: str,
    content: str,
    *,
    title: str = "",
    max_passages: int = 3,
    min_score: float = 0.2,
    max_chars: int = 280,
) -> list[dict]:
    candidate_text = _normalized_text(content)
    if not candidate_text:
        return []

    claim_variants = _claim_text_variants(claim)
    _claim_tokens, exact_terms = _claim_token_bundle(claim)
    if not _claim_tokens:
        return []

    raw_parts = [
        _normalized_text(part)
        for part in re.split(r"(?<=[.!?])\s+|\n+", candidate_text)
        if _normalized_text(part)
    ]

    parts = []
    seen_parts = set()
    for part in raw_parts:
        lowered = part.lower()
        if lowered in seen_parts:
            continue
        seen_parts.add(lowered)
        parts.append(part)

    if not parts:
        parts = [candidate_text]

    candidates: list[tuple[str, str]] = []
    seen_candidates = set()

    def add_candidate(text: str, kind: str) -> None:
        normalized = _normalized_text(text)
        lowered = normalized.lower()
        if len(normalized) < 30 or lowered in seen_candidates:
            return
        seen_candidates.add(lowered)
        candidates.append((normalized, kind))

    for index, part in enumerate(parts):
        add_candidate(part, "sentence")
        if index + 1 < len(parts):
            add_candidate(f"{part} {parts[index + 1]}", "window")

    if not candidates:
        add_candidate(candidate_text, "summary")

    title_overlap = _variant_overlap_ratio(claim_variants, title, exact_terms=exact_terms)
    scored_candidates = []
    for text, kind in candidates:
        overlap = _variant_overlap_ratio(claim_variants, text, exact_terms=exact_terms)
        numeric_alignment = _numeric_alignment(claim, text)
        exact_bonus = 0.22 * _variant_phrase_bonus(claim_variants, text)
        exact_term_bonus = 0.16 * _exact_term_alignment(exact_terms, text)
        myth_boost = _myth_aware_boost(text)
        score = clamp(
            (0.55 * overlap)
            + (0.22 * numeric_alignment)
            + (0.08 * title_overlap)
            + exact_bonus
            + exact_term_bonus
            + myth_boost
        )
        if score < min_score:
            continue
        scored_candidates.append((score, text, kind))

    scored_candidates.sort(key=lambda item: (item[0], -len(item[1])), reverse=True)

    selected: list[dict] = []
    selected_texts: list[str] = []
    for score, text, kind in scored_candidates:
        lowered = text.lower()
        if any(
            lowered in existing.lower() or existing.lower() in lowered
            for existing in selected_texts
        ):
            continue

        trimmed = text if len(text) <= max_chars else f"{text[: max_chars - 3].rstrip()}..."
        selected.append(
            {
                "id": _stable_hash(claim, kind, trimmed, prefix="passage-"),
                "text": trimmed,
                "score": round(score, 2),
                "kind": kind,
                "char_count": len(trimmed),
            }
        )
        selected_texts.append(trimmed)
        if len(selected) >= max_passages:
            break

    return selected


def compute_relevance_score(claim: str, title: str, snippet: str, content: str) -> float:
    claim_variants = _claim_text_variants(claim)
    _claim_tokens, exact_terms = _claim_token_bundle(claim)
    if not _claim_tokens:
        return 0.0

    snippet_overlap = _variant_overlap_ratio(claim_variants, snippet, exact_terms=exact_terms)
    title_overlap = _variant_overlap_ratio(claim_variants, title, exact_terms=exact_terms)
    content_overlap = _variant_overlap_ratio(claim_variants, content, exact_terms=exact_terms)
    exact_term_alignment = _exact_term_alignment(exact_terms, f"{title} {snippet} {content}")
    numeric_alignment = _numeric_alignment(claim, f"{title} {snippet} {content}")
    phrase_bonus = _variant_phrase_bonus(claim_variants, f"{title} {content}")
    exact_claim_bonus = 0.05 if exact_terms and exact_term_alignment >= 1.0 else 0.0

    myth_boost = _myth_aware_boost(f"{title} {snippet} {content}")
    return clamp(
        (0.4 * snippet_overlap)
        + (0.18 * title_overlap)
        + (0.18 * content_overlap)
        + (0.09 * exact_term_alignment)
        + (0.1 * numeric_alignment)
        + (0.05 * phrase_bonus)
        + exact_claim_bonus
        + myth_boost
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
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            pass

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
    authority_score: float,
    relevance_score: float,
    recency_score: float,
    *,
    recency_sensitive: bool = False,
) -> float:
    if recency_sensitive:
        return clamp((0.4 * authority_score) + (0.36 * relevance_score) + (0.24 * recency_score))

    return clamp((0.46 * authority_score) + (0.46 * relevance_score) + (0.08 * recency_score))


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
    origin_counts = Counter(
        source_origin_label(
            source.get("source_origin")
            or (
                "official"
                if str(source.get("source_type") or classify_source_type(source.get("domain", ""))) in OFFICIAL_SOURCE_TYPES
                else "reference"
                if str(source.get("source_type") or classify_source_type(source.get("domain", ""))) == "reference"
                else "secondary"
                if str(source.get("source_type") or classify_source_type(source.get("domain", ""))) in {"news", "commercial", "organization"}
                else "social"
                if str(source.get("source_type") or classify_source_type(source.get("domain", ""))) == "social"
                else "web"
            )
        )
        for source in source_list
    )
    independence_keys = {
        str(
            source.get("independence_key")
            or source_network_key(source.get("domain", ""))
            or source.get("domain", "")
            or source.get("url", "")
        ).strip()
        for source in source_list
        if str(
            source.get("independence_key")
            or source_network_key(source.get("domain", ""))
            or source.get("domain", "")
            or source.get("url", "")
        ).strip()
    }

    return {
        "source_count": len(source_list),
        "authoritative_count": len(authoritative),
        "recent_count": len(recent),
        "dated_count": dated_count,
        "distinct_domain_count": len(
            {source.get("domain", "") for source in source_list if source.get("domain")}
        ),
        "independent_source_count": len(independence_keys),
        "official_source_count": origin_counts.get("official", 0),
        "first_party_count": origin_counts.get("first-party", 0),
        "primary_source_count": (
            origin_counts.get("official", 0)
            + origin_counts.get("first-party", 0)
            + origin_counts.get("reference", 0)
        ),
        "source_origin_breakdown": dict(sorted(origin_counts.items())),
        "freshest_date": max(valid_dates).date().isoformat() if valid_dates else "unknown",
        "domains": sorted({source.get("domain", "") for source in source_list if source.get("domain")}),
    }


def _source_summary_text(item: dict) -> str:
    return " ".join(
        str(item.get(field, "") or "")
        for field in ("snippet_used", "snippet", "assessment_summary", "title")
        if str(item.get(field, "") or "").strip()
    ).strip()


def _collect_identity_tokens(items: Iterable[dict]) -> set[str]:
    tokens: set[str] = set()
    for item in items:
        text = " ".join(
            str(item.get(field, "") or "")
            for field in ("snippet_used", "snippet", "assessment_summary")
            if str(item.get(field, "") or "").strip()
        )
        tokens.update(_claim_identity_tokens(text))
    return tokens


def _contains_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = _marker_text(text)
    return any(_marker_text(marker) in lowered for marker in markers if marker)


def _contradiction_entry(type_id: str) -> dict:
    meta = CONTRADICTION_TYPE_META[type_id]
    return {
        "id": type_id,
        "label": meta["label"],
        "summary": meta["summary"],
    }


def summarize_conflict_profile(
    claim: dict,
    supporting_evidence: Iterable[dict],
    conflicting_evidence: Iterable[dict],
    mixed_evidence: Iterable[dict],
) -> dict:
    support_items = list(supporting_evidence)
    conflict_items = list(conflicting_evidence)
    mixed_items = list(mixed_evidence)

    profile = {
        "summary": "",
        "drivers": [],
        "contradiction_types": [],
        "primary_contradiction_type": "",
        "supporting_count": len(support_items),
        "conflicting_count": len(conflict_items),
        "mixed_count": len(mixed_items),
        "supporting_newest": "unknown",
        "conflicting_newest": "unknown",
        "supporting_avg_authority": 0.0,
        "conflicting_avg_authority": 0.0,
    }

    summary_support_items = support_items or mixed_items
    summary_conflict_items = conflict_items or mixed_items
    has_sided_disagreement = bool(
        summary_support_items
        and summary_conflict_items
        and (support_items or conflict_items)
    )
    if not has_sided_disagreement:
        return profile

    def average_score(items: list[dict], key: str) -> float:
        values = [float(item.get(key, 0.0) or 0.0) for item in items]
        return round(sum(values) / len(values), 2) if values else 0.0

    def newest_label(items: list[dict]) -> str:
        dated_items = [
            parse_published_date(item.get("published_date"))
            for item in items
            if parse_published_date(item.get("published_date")) is not None
        ]
        return max(dated_items).date().isoformat() if dated_items else "unknown"

    def collect_numbers(items: list[dict]) -> set[str]:
        numbers = set()
        for item in items:
            text = _source_summary_text(item)
            numbers.update(re.findall(r"\d+(?:\.\d+)?", text))
        return numbers

    drivers = []
    contradiction_types: list[dict] = []
    support_newest = newest_label(summary_support_items)
    conflict_newest = newest_label(summary_conflict_items)
    support_avg_authority = average_score(summary_support_items, "authority_score")
    conflict_avg_authority = average_score(summary_conflict_items, "authority_score")
    claim_text = str(claim.get("claim", "") or "")
    support_text = " ".join(_source_summary_text(item) for item in summary_support_items)
    conflict_text = " ".join(_source_summary_text(item) for item in summary_conflict_items)
    claim_entities = _claim_identity_tokens(claim_text)
    support_entities = _collect_identity_tokens(summary_support_items)
    conflict_entities = _collect_identity_tokens(summary_conflict_items)

    support_dates = [
        parse_published_date(item.get("published_date"))
        for item in summary_support_items
        if parse_published_date(item.get("published_date")) is not None
    ]
    conflict_dates = [
        parse_published_date(item.get("published_date"))
        for item in summary_conflict_items
        if parse_published_date(item.get("published_date")) is not None
    ]
    if support_dates and conflict_dates:
        latest_gap_days = abs((max(support_dates) - max(conflict_dates)).days)
        if latest_gap_days >= 30:
            contradiction_types.append(_contradiction_entry("date_drift"))
            drivers.append("temporal drift")
    elif claim.get("time_sensitive", False):
        drivers.append("temporal uncertainty")

    if abs(support_avg_authority - conflict_avg_authority) >= 0.12:
        drivers.append("authority imbalance")

    claim_numbers = set(re.findall(r"\d+(?:\.\d+)?", claim_text))
    if claim_numbers:
        support_numbers = collect_numbers(summary_support_items)
        conflict_numbers = collect_numbers(summary_conflict_items)
        if support_numbers and conflict_numbers and support_numbers != conflict_numbers:
            contradiction_types.append(_contradiction_entry("metric_mismatch"))
            drivers.append("numeric disagreement")

    if _contains_any_marker(conflict_text, DEBUNKING_MARKERS):
        contradiction_types.append(_contradiction_entry("direct_debunking"))
        drivers.append("direct debunking")

    conflict_only_entities = {
        token
        for token in conflict_entities - claim_entities
        if len(token) >= 4 and token not in ENTITY_MISMATCH_IGNORE_TOKENS
    }
    if (
        str(claim.get("claim_type", "") or "entity") in {"entity", "comparison", "quote", "causal", "date"}
        and claim_entities
        and (claim_entities & conflict_entities)
        and conflict_only_entities
    ):
        contradiction_types.append(_contradiction_entry("entity_mismatch"))
        drivers.append("entity mismatch")

    if (
        mixed_items
        or str(claim.get("claim_type", "")) in {"comparison", "causal", "quote"}
        or _contains_any_marker(f"{support_text} {conflict_text}", SCOPE_QUALIFIER_MARKERS)
    ):
        contradiction_types.append(_contradiction_entry("scope_mismatch"))
        drivers.append("scope mismatch")

    ordered_types: list[dict] = []
    seen_type_ids: set[str] = set()
    for item in contradiction_types:
        type_id = str(item.get("id", "")).strip()
        if not type_id or type_id in seen_type_ids:
            continue
        seen_type_ids.add(type_id)
        ordered_types.append(item)

    ordered_drivers = list(dict.fromkeys(drivers))
    profile["drivers"] = ordered_drivers
    profile["contradiction_types"] = ordered_types
    profile["primary_contradiction_type"] = ordered_types[0]["id"] if ordered_types else ""
    profile["supporting_newest"] = support_newest
    profile["conflicting_newest"] = conflict_newest
    profile["supporting_avg_authority"] = support_avg_authority
    profile["conflicting_avg_authority"] = conflict_avg_authority

    summary_parts = ["Supporting and conflicting sources disagree"]
    if ordered_types:
        summary_parts.append(
            "mainly because of "
            + ", ".join(str(item["label"]).lower() for item in ordered_types)
            + "."
        )
    elif ordered_drivers:
        summary_parts.append("mainly because of " + ", ".join(ordered_drivers) + ".")
    else:
        summary_parts.append("even though they appear to address the same claim.")

    if support_newest != "unknown" and conflict_newest != "unknown" and support_newest != conflict_newest:
        summary_parts.append(
            f"Supporting evidence is newest on {support_newest}, while conflicting evidence is newest on {conflict_newest}."
        )

    if support_avg_authority != conflict_avg_authority:
        stronger_side = "supporting" if support_avg_authority > conflict_avg_authority else "conflicting"
        summary_parts.append(
            f"The {stronger_side} side has the higher average authority score."
        )

    profile["summary"] = " ".join(summary_parts).strip()
    return profile


def calibrate_verdict(
    assessments: Iterable[dict],
    sources: Iterable[dict],
    claim_time_sensitive: bool = False,
    claim_requires_recency: bool = False,
    auditor_decision: str = None,
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
        independence_weight = clamp(float(source.get("independence_weight", 1.0) or 1.0), 0.45, 1.0)
        source["stance"] = stance
        source["strength"] = round(strength, 2)
        source["independence_weight"] = round(independence_weight, 2)
        source["assessment_summary"] = assessment.get("summary", "")
        source["snippet_used"] = assessment.get("snippet_used") or source.get("snippet", "")
        weighted_score = (
            source.get("overall_score", 0.0)
            * independence_weight
            * (0.35 + (0.65 * strength))
        )

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
    support_count = len(support_items)
    conflict_count = len(conflict_items)
    authoritative_support_count = sum(
        1 for source in support_items if source.get("authority_score", 0.0) >= 0.85
    )
    authoritative_conflict_count = sum(
        1 for source in conflict_items if source.get("authority_score", 0.0) >= 0.85
    )
    strong_support_count = sum(
        1 for source in support_items if source.get("overall_score", 0.0) >= 0.52
    )
    strong_conflict_count = sum(
        1 for source in conflict_items if source.get("overall_score", 0.0) >= 0.52
    )
    grounded_support_count = sum(
        1
        for source in support_items
        if source.get("relevance_score", 0.0) >= 0.52
        or any(passage.get("score", 0.0) >= 0.52 for passage in source.get("evidence_passages", []))
    )
    grounded_conflict_count = sum(
        1
        for source in conflict_items
        if source.get("relevance_score", 0.0) >= 0.52
        or any(passage.get("score", 0.0) >= 0.52 for passage in source.get("evidence_passages", []))
    )
    authoritative_relevant_count = sum(
        1 for source in relevant_sources if source.get("authority_score", 0.0) >= 0.85
    )
    max_support_authority = max(
        (float(source.get("authority_score", 0.0) or 0.0) for source in support_items),
        default=0.0,
    )
    max_conflict_authority = max(
        (float(source.get("authority_score", 0.0) or 0.0) for source in conflict_items),
        default=0.0,
    )
    dated_relevant_count = sum(
        1 for source in relevant_sources if parse_published_date(source.get("published_date")) is not None
    )
    freshness = (
        max(source.get("recency_score", 0.45) for source in relevant_sources)
        if relevant_sources
        else 0.45
    )
    independent_relevant_count = len(
        {
            str(
                source.get("independence_key")
                or source_network_key(source.get("domain", ""))
                or source.get("domain", "")
                or source.get("id", "")
            ).strip()
            for source in relevant_sources
            if str(
                source.get("independence_key")
                or source_network_key(source.get("domain", ""))
                or source.get("domain", "")
                or source.get("id", "")
            ).strip()
        }
    )
    effective_freshness = freshness if (claim_time_sensitive or claim_requires_recency) else max(freshness, 0.72)
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
    elif independent_relevant_count < 2:
        heuristic_flags.append("Most relevant sources trace back to the same source network.")
    if avg_quality < 0.62 and relevant_count and authoritative_relevant_count == 0:
        heuristic_flags.append("Most relevant sources were medium or low authority.")
    if material_conflict:
        heuristic_flags.append("Credible sources disagree on at least part of the claim.")
    if recency_sensitive and dated_relevant_count == 0:
        heuristic_flags.append("The claim appears time-sensitive but none of the relevant sources were date-stamped.")
    elif recency_sensitive and freshness < 0.76:
        heuristic_flags.append("The claim appears time-sensitive but the evidence is not recent enough.")

    clean_support_consensus = (
        support_count >= 2
        and strong_support_count >= 2
        and grounded_support_count >= 1
        and (
            authoritative_support_count >= 1
            or (avg_quality >= 0.67 and max_support_authority >= 0.72)
        )
        and conflict_count == 0
        and conflict_score <= max(0.12, support_score * 0.15)
        and support_score >= 1.0
    )
    clean_conflict_consensus = (
        conflict_count >= 2
        and strong_conflict_count >= 2
        and grounded_conflict_count >= 1
        and (
            authoritative_conflict_count >= 1
            or (avg_quality >= 0.67 and max_conflict_authority >= 0.72)
        )
        and support_count == 0
        and support_score <= max(0.12, conflict_score * 0.15)
        and conflict_score >= 1.0
    )

    # Relax thresholds for definitive verdicts when we have strong indicators
    has_myth_signal = any(_myth_aware_boost(s.get("snippet", "")) > 0 for s in relevant_sources)
    has_hoax_critical_signal = any(
        any(word in str(s.get("snippet", "")).lower() for word in {"deepfake", "hoax", "fabricated", "fake"})
        and _myth_aware_boost(s.get("snippet", "")) > 0
        for s in relevant_sources
    )

    if has_hoax_critical_signal:
        # Heavily penalize confidence and force verification into a more skeptical mode
        clarity = clamp(clarity * 0.5)
        avg_quality = clamp(avg_quality * 0.8)
        # If we have hoax signals, increase the conflict score's weight
        conflict_score += 0.5
    
    if relevant_count == 0 or max_score < 0.38: # Raised floor from 0.28 to prevent noise-based TRUE/FALSE
        verdict = "UNVERIFIABLE"
    elif lacks_temporal_grounding and material_conflict:
        verdict = "UNVERIFIABLE"
    elif lacks_temporal_grounding:
        verdict = "PARTIALLY_TRUE" if max_score >= 0.8 and not material_conflict else "UNVERIFIABLE"
    elif material_conflict:
        verdict = "PARTIALLY_TRUE"
    elif clean_support_consensus:
        verdict = "TRUE"
    elif clean_conflict_consensus:
        verdict = "FALSE"
    # New: Decisive path for authoritative sparse evidence
    elif support_score >= 0.4 and conflict_score == 0.0: # Definitive path for zero-competition TRUE
        verdict = "TRUE"
    elif conflict_score >= 0.4 and support_score == 0.0: # Definitive path for zero-competition FALSE
        verdict = "FALSE"
    # NEW: Trust the auditor for simple false claims with minor noise
    elif auditor_decision == "FALSE" and conflict_score >= 0.55 and conflict_score > (support_score * 1.4):
        verdict = "FALSE"
    # Updated: Allow more leakage (0.3 instead of 0.1 ratio) when the opposition is very weak (< 0.3)
    elif support_score >= 0.6 and (conflict_score <= support_score * 0.15 or conflict_score < 0.3) and max_support_authority >= 0.65:
        verdict = "TRUE"
    elif conflict_score >= 0.6 and (support_score <= conflict_score * 0.15 or support_score < 0.3) and max_conflict_authority >= 0.65:
        verdict = "FALSE"
    elif support_score >= 0.8 and conflict_score <= support_score * 0.25: 
        verdict = "TRUE"
    elif conflict_score >= 0.8 and support_score <= conflict_score * 0.25: 
        verdict = "FALSE"
    elif has_myth_signal and conflict_score >= 0.5 and support_score <= 0.25: 
        verdict = "FALSE" 
    elif relevant_count >= 1 and not conflict_detected and max_score >= 0.6: # Lowered from 0.65
        verdict = "TRUE" if support_score > conflict_score else "FALSE"
    elif relevant_count >= 2 and (conflict_detected and margin < 0.5): # Use material conflict threshold
        verdict = "PARTIALLY_TRUE"
    else:
        verdict = "UNVERIFIABLE"

    confidence = (
        0.28
        + (0.24 * avg_quality)
        + (0.18 * evidence_coverage)
        + (0.17 * clarity)
        + (0.13 * effective_freshness)
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
            "freshness": round(effective_freshness, 2),
            "clarity": round(clarity, 2),
            "support_score": round(support_score, 2),
            "conflict_score": round(conflict_score, 2),
            "independent_sources": independent_relevant_count,
        },
        "supporting_evidence": support_items,
        "conflicting_evidence": conflict_items,
        "mixed_evidence": mixed_items,
        "neutral_evidence": neutral_items,
        "risk_flags": heuristic_flags,
    }
