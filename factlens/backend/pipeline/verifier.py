from __future__ import annotations

import asyncio
import ast
import json
import re
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from llm_provider import create_chat_model
from pipeline.scoring import (
    calibrate_verdict,
    normalize_stance,
    parse_published_date,
    summarize_conflict_profile,
    tokenize,
)

llm, llm_descriptor = create_chat_model("verifier", temperature=0.1, max_tokens=2048)


SYSTEM_PROMPT = """You are an elite investigative fact-checker. Your mission is 100% accuracy through rigorous logical deduction.

Core Mandates:
1. **Chain-of-Thought**: Document every logical pivot. 
2. **Logical Nuance**: Distinguish between "technically true but misleading" and "completely false." If a claim is a half-truth, classify the source as MIXED and explain the exact boundary.
3. **Hoax & AI Detection**: Be extremely alert for "AI-generated," "Deepfake," "Viral Hoax," or "Fabricated" signals. If a source reports that videos/images of an event are AI-generated, that source CONFLICTS with the claim that the event is real.
4. **Myth-Busting Awareness**: If a source identifies a claim as a "myth," "hoax," or "legend," or explicitly warns of "AI-generated fakes" circulating about this specific event, that is a direct CONFLICT with the claim's validity.
5. **Heuristic Suspicion**: If any source mentions "misinformation," "deepfakes," or "fabricated content" as a widespread issue for this claim, switch to a more skeptical stance. If no definitive non-fake evidence exists, the verdict MUST be UNVERIFIABLE or FALSE.
6. **No Unjustified Hedging**: Do not default to "Unverifiable" if multiple credible sources provide a clear, consistent contradiction. "False" is a valid and necessary verdict for debunked claims.
6. **Contextual Grounding**: Interpret the claim in its likely intended context. Use ONLY the provided passages.
7. **Consistency Check**: Consider multiple perspectives and ensure your reasoning is internally consistent.

Return ONLY valid JSON:
{
  "reasoning_steps": [
    "Step 1: Deconstruct claim into atomic parts.",
    "Step 2: Check for AI-generated/hoax debunking signals.",
    "Step 3: Analyze nuances (e.g., Vitamin A vs. night vision).",
    "Step 4: Resolve conflict vs. myth status.",
    "Step 5: Verify internal consistency of reasoning"
  ],
  "reasoning": "Synthesized logical conclusion.",
  "claim_requires_recency": true,
  "risk_flags": [],
  "self_reflection": "Sanity check: Does the evidence strictly support the stance? Did I miss any 'AI-generated' warnings? Is my reasoning consistent across different interpretations?",
  "source_assessments": [
    {
      "source_id": "S1",
      "stance": "SUPPORT|CONFLICT|MIXED|IRRELEVANT",
      "strength": 0.0,
      "summary": "Specific evidence quote/paraphrase...",
      "snippet_used": "..."
    }
  ]
}"""

CONFLICT_MARKERS = (
    " false ",
    " incorrect ",
    " inaccurate ",
    " not true ",
    " no evidence ",
    " debunk",
    " refut",
    " denied ",
    " deny ",
    " disputed ",
    " contradict",
    " hoax ",
    " deepfake ",
    " ai-generated ",
    " ai generated ",
    " fake ",
    " fabricated ",
)
HEDGE_MARKERS = (
    " while ",
    " although ",
    " whereas ",
    " may ",
    " might ",
    " could ",
    " appears ",
    " reportedly ",
    " allegedly ",
    " unclear ",
    " uncertain ",
    " disputed ",
)
OPINION_MARKERS = (
    " some people ",
    " many people ",
    " critics ",
    " fans ",
    " supporters ",
    " opponents ",
    " argue ",
    " argues ",
    " argued ",
    " opinion ",
    " preference ",
    " regarded as ",
    " widely regarded ",
    " considered ",
    " widely considered ",
)
SUBJECTIVE_CLAIM_MARKERS = (
    " best ",
    " worst ",
    " better than ",
    " worse than ",
    " superior to ",
    " inferior to ",
    " most beautiful ",
    " most interesting ",
    " most delicious ",
    " most enjoyable ",
)
CLAUSE_SIGNAL_PATTERN = re.compile(
    r"\b("
    r"is|are|was|were|has|have|had|said|announced|reported|reports|"
    r"approved|vetoed|won|lost|grew|fell|led|caused|contains|include|includes|"
    r"became|becomes|remains|remain|serves|serving|confirmed|denied|states|stated"
    r")\b",
    re.IGNORECASE,
)
CLAUSE_SPLIT_PATTERNS = (
    r"\s*;\s*",
    r"\s+\bbut\b\s+",
    r"\s+\bwhile\b\s+",
    r"\s+\bwhereas\b\s+",
    r"\s+\balthough\b\s+",
)
LOCATION_CONTAINMENT_PATTERN = re.compile(
    r"^\s*(.+?)\s+(?:is|are|was|were|lies|lie|found|stands|stood)\s+(?:located\s+|situated\s+)?in\s+([^.!?]+)[.!?]?\s*$",
    re.IGNORECASE,
)
ROLE_ASSIGNMENT_PATTERNS = (
    re.compile(
        r"^\s*(?:the\s+)?(?P<role>[A-Za-z][A-Za-z\s-]{2,40}?)\s+(?:of|in)\s+(?P<context>.+?)\s+"
        r"(?:is|was|are|were)\s+(?P<subject>.+?)[.!?]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?P<subject>.+?)\s+(?:is|was|are|were|became|becomes|remains)\s+(?:the\s+)?"
        r"(?P<role>[A-Za-z][A-Za-z\s-]{2,40}?)\s+(?:of|in)\s+(?P<context>.+?)[.!?]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?P<context>.+?)['’]s\s+(?P<role>[A-Za-z][A-Za-z\s-]{2,40}?)\s+"
        r"(?:is|was|are|were)\s+(?P<subject>.+?)[.!?]?\s*$",
        re.IGNORECASE,
    ),
)
GEO_DEMONYM_EQUIVALENTS = {
    "american": "united states",
    "australian": "australia",
    "british": "united kingdom",
    "canadian": "canada",
    "chinese": "china",
    "english": "england",
    "european": "europe",
    "french": "france",
    "german": "germany",
    "indian": "india",
    "italian": "italy",
    "japanese": "japan",
    "mexican": "mexico",
    "russian": "russia",
    "spanish": "spain",
}
GENERIC_LOCATION_TARGETS = {
    "capital",
    "city",
    "country",
    "district",
    "downtown",
    "east",
    "north",
    "northeast",
    "northwest",
    "province",
    "region",
    "south",
    "southeast",
    "southwest",
    "state",
    "west",
}
ROLE_EQUIVALENT_PATTERNS = {
    "capital": r"(?:capital(?:\s+city)?|seat\s+of\s+government|national\s+capital|federal\s+capital)",
    "largest_city": r"(?:(?:largest|biggest|most\s+populous)\s+city)",
    "smallest_city": r"(?:smallest\s+city)",
}


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
            raise ValueError("Could not parse verifier response.") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed


def _coerce_assessment(assessment: dict) -> dict:
    try:
        strength = float(assessment.get("strength", 0.5))
    except (TypeError, ValueError):
        strength = 0.5

    return {
        "source_id": str(assessment.get("source_id", "")).strip(),
        "stance": normalize_stance(assessment.get("stance")),
        "strength": max(0.0, min(1.0, strength)),
        "summary": str(assessment.get("summary", "")).strip(),
        "snippet_used": str(assessment.get("snippet_used", "")).strip(),
    }


def _natural_satellite_claim(claim: dict) -> bool:
    text = str(claim.get("claim", "")).lower()
    return "earth" in text and "natural satellite" in text


def _quasi_moon_only_signal(text: str) -> bool:
    lowered = text.lower()
    signals = (
        "quasi-moon",
        "quasi moon",
        "mini-moon",
        "mini moon",
        "temporary moon",
        "temporary mini-moon",
        "temporary mini moon",
        "temporary satellite",
        "captured asteroid",
        "sharing the earth's orbit",
        "sharing earth's orbit",
        "looks like it's going around the earth",
        "looks like it is going around the earth",
        "visitor within its orbit",
    )
    return any(signal in lowered for signal in signals)


def _location_claim_parts(claim: dict) -> tuple[str, str] | None:
    claim_text = str(claim.get("claim", "") or "").strip()
    match = LOCATION_CONTAINMENT_PATTERN.search(claim_text)
    if not match:
        return None

    subject = match.group(1).strip(" ,.")
    location = match.group(2).strip(" ,.")
    if len(tokenize(subject)) < 1 or len(tokenize(location)) < 1:
        return None
    return subject, location


def _normalize_location_label(value: str) -> str:
    normalized = re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", str(value or "").lower())).strip()
    normalized = re.sub(r"^(?:the|a|an)\s+", "", normalized)
    parts = [GEO_DEMONYM_EQUIVALENTS.get(part, part) for part in normalized.split()]
    return " ".join(part for part in parts if part).strip()


def _clean_location_candidate(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip(" ,.;:()[]"))
    cleaned = re.sub(r"^(?:the)\s+", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"^(?:is|was|are|were)\s+", "", cleaned, flags=re.IGNORECASE)


def _normalize_role_label(value: str) -> str:
    lowered = re.sub(r"\s+", " ", str(value or "").lower()).strip()
    for role_key, pattern in ROLE_EQUIVALENT_PATTERNS.items():
        if re.search(rf"\b{pattern}\b", lowered, re.IGNORECASE):
            return role_key
    return ""


def _role_label_text(role_key: str) -> str:
    labels = {
        "capital": "capital",
        "largest_city": "largest city",
        "smallest_city": "smallest city",
    }
    return labels.get(role_key, role_key.replace("_", " "))


def _clean_role_candidate(value: str) -> str:
    cleaned = _clean_location_candidate(value)
    cleaned = re.sub(r"\b(?:today|currently|now|officially)$", "", cleaned, flags=re.IGNORECASE).strip(" ,.")
    return cleaned


def _labels_match(left: str, right: str) -> bool:
    normalized_left = _normalize_location_label(left)
    normalized_right = _normalize_location_label(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True
    if normalized_left in normalized_right and (len(normalized_left) / len(normalized_right)) >= 0.55:
        return True
    if normalized_right in normalized_left and (len(normalized_right) / len(normalized_left)) >= 0.55:
        return True
    return False


def _role_assignment_claim_parts(claim: dict) -> tuple[str, str, str] | None:
    claim_text = str(claim.get("claim", "") or "").strip()
    for pattern in ROLE_ASSIGNMENT_PATTERNS:
        match = pattern.search(claim_text)
        if not match:
            continue
        role_key = _normalize_role_label(match.group("role"))
        if not role_key:
            continue
        subject = _clean_role_candidate(match.group("subject"))
        context = _clean_role_candidate(match.group("context"))
        if len(tokenize(subject)) < 1 or len(tokenize(context)) < 1:
            continue
        return subject, role_key, context
    return None


def _extract_role_assignments(role_key: str, text: str) -> list[tuple[str, str]]:
    normalized_text = " ".join(str(text or "").split())
    if not normalized_text:
        return []

    role_pattern = ROLE_EQUIVALENT_PATTERNS.get(role_key)
    if not role_pattern:
        return []

    patterns = (
        rf"\b(?P<subject>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)\s+"
        rf"(?:is|was|are|were|became|becomes|remains)\s+(?:the\s+)?{role_pattern}\s+(?:of|in)\s+"
        rf"(?P<context>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)(?:[,.;]|\s+and\b|\s+but\b|$)",
        rf"\b(?P<subject>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)\s+"
        rf"(?:is|was|are|were|became|becomes|remains)\s+(?P<context>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)['’]s\s+"
        rf"{role_pattern}(?:[,.;]|\s+and\b|\s+but\b|$)",
        rf"\b(?P<context>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)['’]s\s+{role_pattern}\s+"
        rf"(?:is|was|are|were)\s+(?P<subject>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)(?:[,.;]|\s+and\b|\s+but\b|$)",
        rf"\b(?P<subject>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?),\s+(?:the\s+)?{role_pattern}\s+(?:of|in)\s+"
        rf"(?P<context>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)(?:[,.;]|\s+and\b|\s+but\b|$)",
        rf"\b(?:the\s+)?{role_pattern}\s+(?:of|in)\s+(?P<context>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)\s+"
        rf"(?:is|was|are|were)\s+(?P<subject>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)(?:[,.;]|\s+and\b|\s+but\b|$)",
        rf"\b(?P<subject>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)\s+"
        rf"(?:to\s+become|became|becomes|remains)\s+(?P<context>[A-Za-z0-9][A-Za-z0-9 .'-]{{1,80}}?)['’]s\s+"
        rf"{role_pattern}(?:[,.;]|\s+by\b|$)",
    )

    assignments: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    segments = [
        segment.strip()
        for segment in re.split(r"(?<=[.!?])\s+|\n+", normalized_text)
        if segment.strip()
    ] or [normalized_text]
    for segment in segments:
        for pattern in patterns:
            for match in re.finditer(pattern, segment, re.IGNORECASE):
                subject = _clean_role_candidate(match.group("subject"))
                context = _clean_role_candidate(match.group("context"))
                if not subject or not context:
                    continue
                key = (_normalize_location_label(subject), _normalize_location_label(context))
                if not all(key) or key in seen:
                    continue
                seen.add(key)
                assignments.append((subject, context))
    return assignments


def _classify_role_assignment_relationship(claim: dict, source_text: str) -> tuple[str, str, str]:
    role_claim = _role_assignment_claim_parts(claim)
    if not role_claim:
        return "", "", ""

    claimed_subject, role_key, claimed_context = role_claim
    assignments = _extract_role_assignments(role_key, source_text)
    for candidate_subject, candidate_context in assignments:
        same_subject = _labels_match(candidate_subject, claimed_subject)
        same_context = _labels_match(candidate_context, claimed_context)
        if same_subject and same_context:
            return "support", candidate_subject, candidate_context
        if same_context and not same_subject:
            return "conflict", candidate_subject, candidate_context
        if same_subject and not same_context:
            return "conflict", candidate_subject, candidate_context
    return "", "", ""


def _extract_location_targets(subject: str, text: str) -> list[str]:
    normalized_text = " ".join(str(text or "").split())
    if not normalized_text:
        return []

    escaped_subject = re.escape(subject.strip())
    patterns = (
        rf"\b{escaped_subject}\b[^,.!?;\n]{{0,60}}?\b(?:is|are|was|were|lies|lie|found|stands|stood)\s+"
        rf"(?:located\s+|situated\s+)?in\s+([A-Za-z0-9][A-Za-z0-9 .'-]{{1,64}}?)(?:[,.;]|\s+and\s+|$)",
        rf"\b{escaped_subject}\b[^,.!?;\n]{{0,60}}?\b(?:capital|city|landmark)\b[^,.!?;\n]{{0,40}}?\bof\s+"
        rf"([A-Za-z0-9][A-Za-z0-9 .'-]{{1,64}}?)(?:[,.;]|$)",
        rf"\b{escaped_subject}\b[^,.!?;\n]{{0,60}}?\b(?:orbits|is a moon of|is a satellite of)\s+([A-Za-z0-9][A-Za-z0-9 .'-]{{1,64}}?)(?:[,.;]|$)",
        rf"\b{escaped_subject}\b[^,.!?;\n]{{0,60}}?\b(?:was born in|died in|occurred in|discovered in)\s+([A-Za-z0-9][A-Za-z0-9 .'-]{{1,64}}?)(?:[,.;]|$)",
        rf"\b{escaped_subject}\b[^,.!?;\n]{{0,60}}?\b([A-Za-z0-9][A-Za-z0-9 .'-]{{1,64}}?)['’]s\s+(?:capital|city|landmark|famous|iconic)\b",
        rf"\b([A-Za-z0-9][A-Za-z0-9 .'-]{{1,64}}?)\s+is\s+(?:home\s+to|where\s+.*is\s+located)\s+the\s+\b{escaped_subject}\b",
    )
    seen: set[str] = set()
    candidates: list[str] = []

    for pattern in patterns:
        for match in re.finditer(pattern, normalized_text, re.IGNORECASE):
            groups = [g for g in match.groups() if g]
            if not groups:
                continue
            candidate = _clean_location_candidate(groups[0])
            normalized = _normalize_location_label(candidate)
            if (
                not normalized
                or normalized in GENERIC_LOCATION_TARGETS
                or normalized == _normalize_location_label(subject)
                or normalized in seen
            ):
                continue
            seen.add(normalized)
            candidates.append(candidate)

    return candidates


def _classify_location_relationship(claim: dict, source_text: str) -> tuple[str, str]:
    location_parts = _location_claim_parts(claim)
    if not location_parts:
        return "", ""

    subject, claimed_location = location_parts
    # Also try without "The" if it starts with it
    subject_alt = subject[4:] if subject.lower().startswith("the ") else subject

    has_subject = re.search(rf"\b{re.escape(subject)}\b", str(source_text or ""), re.IGNORECASE) or \
                  re.search(rf"\b{re.escape(subject_alt)}\b", str(source_text or ""), re.IGNORECASE)
    
    if not has_subject:
        return "", ""

    claimed_normalized = _normalize_location_label(claimed_location)
    targets = _extract_location_targets(subject, source_text) or _extract_location_targets(subject_alt, source_text)
    
    for candidate in targets:
        candidate_normalized = _normalize_location_label(candidate)
        if not candidate_normalized:
            continue
        
        # Stricter matching: The candidate must be an excellent match for the claimed location.
        # "Paris" vs "Paris, France" -> Support.
        # "Berlin" vs "Berlin, Germany" -> Support.
        # BUT "Berlin" vs "Berlin, USA" -> Conflict (if we can be that precise).
        
        is_exact = candidate_normalized == claimed_normalized
        is_part_of = candidate_normalized in claimed_normalized and (len(candidate_normalized) / len(claimed_normalized) > 0.4)
        is_parent_of = claimed_normalized in candidate_normalized and (len(claimed_normalized) / len(candidate_normalized) > 0.4)

        if is_exact or is_part_of or is_parent_of:
            return "support", candidate
        
        return "conflict", candidate

    return "", ""


def _normalize_assessments_for_claim(
    claim: dict,
    assessments: list[dict],
    sources: list[dict],
) -> list[dict]:
    natural_satellite_claim = _natural_satellite_claim(claim)
    location_claim = _location_claim_parts(claim)
    role_assignment_claim = _role_assignment_claim_parts(claim)
    if not natural_satellite_claim and not location_claim and not role_assignment_claim:
        return assessments

    source_map = {
        str(source.get("id", "")).strip(): source
        for source in sources
        if str(source.get("id", "")).strip()
    }
    normalized = []

    for assessment in assessments:
        source = source_map.get(assessment["source_id"], {})
        source_text = " ".join(
            [
                str(assessment.get("summary", "")).strip(),
                str(assessment.get("snippet_used", "")).strip(),
                str(source.get("title", "")).strip(),
                str(source.get("snippet", "")).strip(),
                " ".join(
                    str(passage.get("text", "")).strip()
                    for passage in source.get("evidence_passages", [])
                    if str(passage.get("text", "")).strip()
                ),
            ]
        )

        if natural_satellite_claim and assessment["stance"] in {"CONFLICT", "MIXED"} and _quasi_moon_only_signal(source_text):
            adjusted = dict(assessment)
            adjusted["stance"] = "IRRELEVANT"
            adjusted["summary"] = (
                adjusted["summary"]
                or "Discusses a quasi-moon or temporary mini-moon, not a second natural satellite."
            )
            normalized.append(adjusted)
            continue

        if role_assignment_claim:
            claimed_subject, role_key, claimed_context = role_assignment_claim
            relationship, related_subject, related_context = _classify_role_assignment_relationship(claim, source_text)
            base_strength = max(
                float(assessment.get("strength", 0.5) or 0.5),
                float(source.get("overall_score", 0.0) or 0.0),
                float(source.get("relevance_score", 0.0) or 0.0),
                max(
                    (float(passage.get("score", 0.0) or 0.0) for passage in source.get("evidence_passages", []) or []),
                    default=0.0,
                ),
            )
            adjusted = dict(assessment)
            if relationship == "support":
                adjusted["stance"] = "SUPPORT"
                adjusted["strength"] = max(0.74, min(base_strength, 0.92))
                adjusted["summary"] = (
                    f"Directly identifies {claimed_subject} as the {_role_label_text(role_key)} of {claimed_context}."
                )
                normalized.append(adjusted)
                continue
            if relationship == "conflict":
                adjusted["stance"] = "CONFLICT"
                adjusted["strength"] = max(0.74, min(base_strength, 0.9))
                if _labels_match(related_context, claimed_context) and not _labels_match(related_subject, claimed_subject):
                    adjusted["summary"] = (
                        f"Directly identifies {related_subject}, not {claimed_subject}, as the {_role_label_text(role_key)} of {claimed_context}."
                    )
                elif _labels_match(related_subject, claimed_subject) and not _labels_match(related_context, claimed_context):
                    adjusted["summary"] = (
                        f"Directly says {claimed_subject} is the {_role_label_text(role_key)} of {related_context}, not {claimed_context}."
                    )
                else:
                    adjusted["summary"] = (
                        f"Directly conflicts with the claimed {_role_label_text(role_key)} relationship."
                    )
                normalized.append(adjusted)
                continue
            if adjusted.get("stance") != "IRRELEVANT":
                adjusted["stance"] = "IRRELEVANT"
                adjusted["strength"] = min(float(adjusted.get("strength", 0.45) or 0.45), 0.45)
                adjusted["summary"] = (
                    "Mentions the named entity, but does not directly ground the claimed role assignment."
                )
                normalized.append(adjusted)
                continue

        if location_claim:
            subject, claimed_location = location_claim
            relationship, related_location = _classify_location_relationship(claim, source_text)
            base_strength = max(
                float(assessment.get("strength", 0.5) or 0.5),
                float(source.get("overall_score", 0.0) or 0.0),
                float(source.get("relevance_score", 0.0) or 0.0),
                max(
                    (float(passage.get("score", 0.0) or 0.0) for passage in source.get("evidence_passages", []) or []),
                    default=0.0,
                ),
            )
            adjusted = dict(assessment)
            if relationship == "support":
                adjusted["stance"] = "SUPPORT"
                adjusted["strength"] = max(0.74, min(base_strength, 0.92))
                adjusted["summary"] = (
                    f"Directly places {subject} in {claimed_location}."
                )
                normalized.append(adjusted)
                continue
            if relationship == "conflict":
                adjusted["stance"] = "CONFLICT"
                adjusted["strength"] = max(0.74, min(base_strength, 0.9))
                adjusted["summary"] = (
                    f"Directly places {subject} in {related_location}, not {claimed_location}."
                )
                normalized.append(adjusted)
                continue
            if adjusted.get("stance") != "IRRELEVANT":
                adjusted["stance"] = "IRRELEVANT"
                adjusted["strength"] = min(float(adjusted.get("strength", 0.45) or 0.45), 0.45)
                adjusted["summary"] = (
                    "Mentions the entity, but does not directly ground its geographic location."
                )
                normalized.append(adjusted)
                continue

        normalized.append(assessment)

    return normalized


def _normalized_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%.-]", " ", str(value or "").lower())).strip()


def _marker_normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%]", " ", str(value or "").lower())).strip()


def _claim_numbers(value: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", str(value or "")))


def _heuristic_overlap(claim_text: str, evidence_text: str) -> float:
    claim_tokens = set(tokenize(claim_text))
    evidence_tokens = set(tokenize(evidence_text))
    if not claim_tokens or not evidence_tokens:
        return 0.0
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def _best_source_snippet(source: dict) -> str:
    passages = source.get("evidence_passages", []) or []
    if passages:
        best = max(passages, key=lambda item: float(item.get("score", 0.0) or 0.0))
        if str(best.get("text", "")).strip():
            return str(best["text"]).strip()
    return str(source.get("snippet") or "").strip()


def _source_evidence_text(source: dict) -> str:
    passage_text = " ".join(
        str(passage.get("text", "")).strip()
        for passage in source.get("evidence_passages", []) or []
        if str(passage.get("text", "")).strip()
    )
    return " ".join(
        part
        for part in [
            str(source.get("title", "")).strip(),
            str(source.get("snippet", "")).strip(),
            passage_text,
        ]
        if part
    ).strip()


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = f" {_marker_normalized_text(text)} "
    return any(f" {_marker_normalized_text(marker)} " in lowered for marker in markers if marker)


def _source_signal_strength(source: dict) -> float:
    passage_score = max(
        (float(passage.get("score", 0.0) or 0.0) for passage in source.get("evidence_passages", []) or []),
        default=0.0,
    )
    return max(
        float(source.get("relevance_score", 0.0) or 0.0),
        float(source.get("overall_score", 0.0) or 0.0),
        float(source.get("authority_score", 0.0) or 0.0),
        passage_score,
    )


def _claim_is_subjective(claim: dict) -> bool:
    claim_text = f" {_marker_normalized_text(claim.get('claim', ''))} "
    return any(marker in claim_text for marker in SUBJECTIVE_CLAIM_MARKERS)


def _source_has_direct_grounding(source: dict) -> bool:
    return bool(
        float(source.get("relevance_score", 0.0) or 0.0) >= 0.52
        or any(
            float(passage.get("score", 0.0) or 0.0) >= 0.52
            for passage in source.get("evidence_passages", []) or []
        )
    )


def _reflection_can_harden_verdict(result: dict, suggested_verdict: str) -> bool:
    if suggested_verdict not in {"TRUE", "FALSE"}:
        return True

    aligned_sources = (
        result.get("supporting_evidence", [])
        if suggested_verdict == "TRUE"
        else result.get("conflicting_evidence", [])
    )
    opposing_sources = (
        result.get("conflicting_evidence", [])
        if suggested_verdict == "TRUE"
        else result.get("supporting_evidence", [])
    )
    mixed_sources = result.get("mixed_evidence", [])
    direct_count = sum(1 for source in aligned_sources if _source_has_direct_grounding(source))
    authoritative_direct_count = sum(
        1
        for source in aligned_sources
        if _source_has_direct_grounding(source) and float(source.get("authority_score", 0.0) or 0.0) >= 0.82
    )

    # Evidence of Absence signal
    empty_auth = result.get("empty_authoritative_queries", [])
    has_absence_signal = len(empty_auth) > 0
    
    # Check if the auditor is correcting based on known myths or blatant contradictions
    is_authoritative_debunk = suggested_verdict == "FALSE" and (has_absence_signal or authoritative_direct_count > 0)

    max_overall = max((float(source.get("overall_score", 0.0) or 0.0) for source in aligned_sources), default=0.0)

    # Allow hardening if opposing sources are weak or few
    has_strong_opposition = any(
        float(s.get("strength", 0.0) or 0.0) >= 0.65 # Strong opposition
        for s in opposing_sources
    )
    if has_strong_opposition and not is_authoritative_debunk:
        return False
    
    # Allow hardening if we have a solid consensus on one side
    # NEW: Much more aggressive for FALSE cases where we have absence signals or material conflict
    if suggested_verdict == "FALSE":
        if has_absence_signal:
            return True
        # Check if mixed evidence has a conflict lean
        leaning_negative = any(
            float(s.get("strength", 0.0) or 0.0) >= 0.4 and s.get("stance") == "MIXED"
            for s in mixed_sources
        )
        if (len(aligned_sources) >= 1 or leaning_negative) and (authoritative_direct_count >= 1 or max_overall >= 0.75):
            return True
    
    if (len(aligned_sources) >= 1 and authoritative_direct_count >= 1) or (len(aligned_sources) >= 1 and max_overall >= 0.9):
        return True
    if len(aligned_sources) >= 2 and direct_count >= 1:
        return True
    if len(aligned_sources) >= 2 and direct_count >= 2 and max_overall >= 0.78 and not mixed_sources:
        return True
    if len(aligned_sources) == 1 and authoritative_direct_count >= 1 and max_overall >= 0.9 and not mixed_sources:
        return True
    
    return False


def _heuristic_assessment_for_source(claim: dict, source: dict) -> dict:
    claim_text = str(claim.get("claim", "")).strip()
    evidence_text = _source_evidence_text(source)
    overlap = _heuristic_overlap(claim_text, evidence_text)
    claim_numbers = _claim_numbers(claim_text)
    evidence_numbers = _claim_numbers(evidence_text)
    numeric_alignment = (
        len(claim_numbers & evidence_numbers) / len(claim_numbers)
        if claim_numbers
        else 0.0
    )
    exact_match = bool(
        claim_text
        and _normalized_phrase(claim_text) in _normalized_phrase(evidence_text)
    )
    conflict_marker = _contains_marker(evidence_text, CONFLICT_MARKERS)
    hedge_marker = _contains_marker(evidence_text, HEDGE_MARKERS)
    opinion_marker = _contains_marker(evidence_text, OPINION_MARKERS)
    subjective_claim = _claim_is_subjective(claim)
    snippet_used = _best_source_snippet(source)
    passage_score = max(
        (float(passage.get("score", 0.0) or 0.0) for passage in source.get("evidence_passages", []) or []),
        default=0.0,
    )
    base_strength = max(
        float(source.get("relevance_score", 0.0) or 0.0),
        float(source.get("overall_score", 0.0) or 0.0),
        passage_score,
    )

    # Space and Location Entity Guards
    space_entities = {"moon", "mars", "earth", "venus", "jupiter", "saturn", "mercury", "sun", "pluto"}
    location_entities = {"delhi", "agra", "mumbai", "kolkata", "new delhi"}
    
    # Simple word-based check for common hallucinations
    norm_claim = claim_text.lower()
    norm_evidence = evidence_text.lower()
    
    found_space_in_claim = {e for e in space_entities if f" {e} " in f" {norm_claim} " or norm_claim.startswith(f"{e} ") or norm_claim.endswith( f" {e}")}
    found_space_in_evidence = {e for e in space_entities if f" {e} " in f" {norm_evidence} " or norm_evidence.startswith(f"{e} ") or norm_evidence.endswith( f" {e}")}
    
    space_conflict = bool(found_space_in_claim and found_space_in_evidence and found_space_in_claim != found_space_in_evidence)
    
    # Specialized Location check
    found_loc_in_claim = {e for e in location_entities if e in norm_claim}
    found_loc_in_evidence = {e for e in location_entities if e in norm_evidence}
    loc_conflict = bool(found_loc_in_claim and found_loc_in_evidence and found_loc_in_claim != found_loc_in_evidence)

    stance = "IRRELEVANT"
    strength = min(base_strength, 0.45)
    summary = "The grounded passage did not clearly resolve the claim."

    if space_conflict or loc_conflict:
        stance = "CONFLICT"
        strength = max(0.82, base_strength)
        summary = "Entity mismatch: Claim and evidence discuss different celestial bodies or locations."
    elif claim_numbers and overlap >= 0.45:
        if numeric_alignment >= 1.0 and not conflict_marker:
            stance = "SUPPORT"
            strength = max(0.72, base_strength)
            summary = "The grounded passage matches the claim's key numeric detail."
        elif numeric_alignment == 0.0 and evidence_numbers and not hedge_marker:
            stance = "CONFLICT"
            strength = max(0.68, min(base_strength, 0.88))
            summary = "The grounded passage discusses the same claim but with different numeric detail."
        elif evidence_numbers:
            stance = "MIXED"
            strength = max(0.58, min(base_strength, 0.82))
            summary = "The grounded passage overlaps the claim but qualifies or varies the numeric detail."
    is_question = "?" in snippet_used or snippet_used.lower().startswith("what ") or snippet_used.lower().startswith("how ")

    if is_question:
        stance = "IRRELEVANT"
        strength = 0.0
        summary = "The snippet is a question and does not make a factual assertion."
    elif stance == "IRRELEVANT" and subjective_claim and overlap >= 0.45 and not conflict_marker:
        stance = "MIXED"
        strength = max(0.54, min(base_strength, 0.72))
        summary = (
            "The grounded passage expresses a value judgment or opinion, so it cannot fully verify "
            "this subjective claim."
        )
    elif stance == "IRRELEVANT" and exact_match and not conflict_marker and not hedge_marker and not opinion_marker:
        stance = "SUPPORT"
        strength = max(0.76, base_strength)
        summary = "The grounded passage directly states the claim."
    elif (
        stance == "IRRELEVANT"
        and overlap >= 0.8
        and passage_score >= 0.72
        and not conflict_marker
        and not hedge_marker
        and not opinion_marker
    ):
        stance = "SUPPORT"
        strength = max(0.7, min(base_strength, 0.88))
        summary = "The grounded passage closely paraphrases the claim."
    elif (
        stance == "IRRELEVANT"
        and overlap >= 0.92
        and not conflict_marker
        and not hedge_marker
        and not opinion_marker
    ): # Increased overlap from 0.85
        stance = "SUPPORT"
        strength = max(0.66, min(base_strength, 0.86))
        summary = "The grounded passage very strongly overlaps the claim."
    elif stance == "IRRELEVANT" and overlap >= 0.58 and conflict_marker:
        stance = "CONFLICT"
        strength = max(0.62, min(base_strength, 0.84))
        summary = "The grounded passage discusses the claim but frames it as false or disputed."
    elif stance == "IRRELEVANT" and overlap >= 0.45:
        stance = "MIXED" if hedge_marker else "IRRELEVANT"
        strength = max(0.5, min(base_strength, 0.72)) if stance == "MIXED" else min(base_strength, 0.45)
        summary = (
            "The grounded passage is related but hedged or only partially aligned with the claim."
            if stance == "MIXED"
            else summary
        )

    return {
        "source_id": str(source.get("id", "")).strip(),
        "stance": stance,
        "strength": max(0.0, min(strength, 1.0)),
        "summary": summary,
        "snippet_used": snippet_used,
    }


def _build_heuristic_assessments(claim: dict, sources: list[dict]) -> list[dict]:
    return [
        _heuristic_assessment_for_source(claim, source)
        for source in sources
        if str(source.get("id", "")).strip()
    ]


def _stance_is_relevant(stance: str) -> bool:
    return normalize_stance(stance) in {"SUPPORT", "CONFLICT", "MIXED"}


def _merge_assessment_with_heuristic(existing: dict, heuristic: dict) -> dict:
    if not existing:
        return dict(heuristic)

    existing_stance = normalize_stance(existing.get("stance"))
    heuristic_stance = normalize_stance(heuristic.get("stance"))

    try:
        existing_strength = float(existing.get("strength", 0.5) or 0.5)
    except (TypeError, ValueError):
        existing_strength = 0.5
    try:
        heuristic_strength = float(heuristic.get("strength", 0.5) or 0.5)
    except (TypeError, ValueError):
        heuristic_strength = 0.5

    if existing_stance == "IRRELEVANT" and heuristic_stance != "IRRELEVANT":
        return dict(heuristic)

    if {existing_stance, heuristic_stance} == {"SUPPORT", "CONFLICT"}:
        return {
            "source_id": str(existing.get("source_id") or heuristic.get("source_id") or "").strip(),
            "stance": "MIXED",
            "strength": max(0.58, min(max(existing_strength, heuristic_strength), 0.82)),
            "summary": "Model and heuristic disagree significantly; FactLens defaulted to mixed to be safe.",
            "snippet_used": str(existing.get("snippet_used") or heuristic.get("snippet_used") or "").strip(),
        }

    if (
        "MIXED" in {existing_stance, heuristic_stance}
        and _stance_is_relevant(existing_stance)
        and _stance_is_relevant(heuristic_stance)
        and existing_stance != heuristic_stance
    ):
        mixed_strength = max(
            strength
            for stance, strength in (
                (existing_stance, existing_strength),
                (heuristic_stance, heuristic_strength),
            )
            if stance == "MIXED"
        )
        definitive_stance = (
            existing_stance
            if existing_stance in {"SUPPORT", "CONFLICT"}
            else heuristic_stance
        )
        definitive_strength = (
            existing_strength
            if existing_stance == definitive_stance
            else heuristic_strength
        )
        if mixed_strength < 0.6 and definitive_strength >= 0.82:
            return existing if existing_stance == definitive_stance else dict(heuristic)
        return {
            "source_id": str(existing.get("source_id") or heuristic.get("source_id") or "").strip(),
            "stance": "MIXED",
            "strength": max(0.58, min(max(existing_strength, heuristic_strength), 0.82)),
            "summary": (
                "The model-guided and heuristic checks disagree on how this source should be interpreted, "
                "so FactLens treated it as mixed evidence."
            ),
            "snippet_used": str(existing.get("snippet_used") or heuristic.get("snippet_used") or "").strip(),
        }

    if existing_stance == heuristic_stance and heuristic_strength > existing_strength:
        merged = dict(existing)
        merged["strength"] = max(0.0, min(heuristic_strength, 1.0))
        if not str(merged.get("summary", "")).strip():
            merged["summary"] = str(heuristic.get("summary", "")).strip()
        if not str(merged.get("snippet_used", "")).strip():
            merged["snippet_used"] = str(heuristic.get("snippet_used", "")).strip()
        return merged

    return existing


def _combine_assessments_with_heuristics(
    assessments: list[dict],
    heuristic_assessments: list[dict],
) -> list[dict]:
    merged: dict[str, dict] = {}

    for assessment in assessments:
        source_id = str(assessment.get("source_id", "")).strip()
        if not source_id:
            continue
        merged[source_id] = dict(assessment)

    for heuristic in heuristic_assessments:
        source_id = str(heuristic.get("source_id", "")).strip()
        if not source_id:
            continue
        merged[source_id] = _merge_assessment_with_heuristic(
            merged.get(source_id, {}),
            heuristic,
        )

    return list(merged.values())


def _assessment_alignment_profile(
    llm_assessments: list[dict],
    heuristic_assessments: list[dict],
) -> dict:
    llm_by_id = {
        str(item.get("source_id", "")).strip(): normalize_stance(item.get("stance"))
        for item in llm_assessments
        if str(item.get("source_id", "")).strip()
    }
    heuristic_by_id = {
        str(item.get("source_id", "")).strip(): normalize_stance(item.get("stance"))
        for item in heuristic_assessments
        if str(item.get("source_id", "")).strip()
    }

    compared_count = 0
    disagreement_count = 0
    hard_conflict_count = 0
    relevance_mismatch_count = 0

    for source_id, llm_stance in llm_by_id.items():
        heuristic_stance = heuristic_by_id.get(source_id)
        if not heuristic_stance:
            continue
        compared_count += 1
        if llm_stance == heuristic_stance:
            continue
        disagreement_count += 1
        if {llm_stance, heuristic_stance} == {"SUPPORT", "CONFLICT"}:
            hard_conflict_count += 1
        if _stance_is_relevant(llm_stance) != _stance_is_relevant(heuristic_stance):
            relevance_mismatch_count += 1

    disagreement_ratio = (
        disagreement_count / compared_count
        if compared_count
        else 0.0
    )

    return {
        "compared_count": compared_count,
        "disagreement_count": disagreement_count,
        "hard_conflict_count": hard_conflict_count,
        "relevance_mismatch_count": relevance_mismatch_count,
        "disagreement_ratio": disagreement_ratio,
    }


def _apply_assessment_cross_check(
    calibration: dict,
    *,
    llm_assessments: list[dict],
    heuristic_assessments: list[dict],
    heuristic_calibration: dict | None,
) -> tuple[dict, list[str]]:
    if not llm_assessments or not heuristic_assessments:
        return calibration, []

    profile = _assessment_alignment_profile(llm_assessments, heuristic_assessments)
    if profile["compared_count"] == 0:
        return calibration, []

    adjusted = dict(calibration)
    adjusted["confidence_breakdown"] = dict(calibration.get("confidence_breakdown", {}))
    adjusted["confidence_breakdown"]["cross_check_agreement"] = round(
        max(0.0, 1.0 - profile["disagreement_ratio"]),
        2,
    )

    risk_flags: list[str] = []
    if profile["disagreement_count"]:
        risk_flags.append(
            f"LLM and heuristic source assessment disagreed on {profile['disagreement_count']} of "
            f"{profile['compared_count']} compared sources."
        )

    confidence_penalty = 0.0
    if profile["disagreement_ratio"] >= 0.5:
        confidence_penalty += 0.06
    elif profile["disagreement_ratio"] >= 0.25:
        confidence_penalty += 0.03
    if profile["hard_conflict_count"] > 0:
        confidence_penalty += 0.06
    elif profile["relevance_mismatch_count"] > 0:
        confidence_penalty += 0.04

    if heuristic_calibration:
        heuristic_verdict = str(heuristic_calibration.get("verdict", "")).strip().upper()
        current_verdict = str(adjusted.get("verdict", "")).strip().upper()
        if heuristic_verdict and heuristic_verdict != current_verdict:
            risk_flags.append(
                f"Heuristic cross-check resolved this claim as {heuristic_verdict}, so FactLens lowered confidence in the primary verdict."
            )
            confidence_penalty += 0.05

    adjusted["confidence"] = round(
        max(0.05, min(0.97, float(adjusted.get("confidence", 0.0) or 0.0) - confidence_penalty)),
        2,
    )
    return adjusted, risk_flags


def _contains_clause_signal(text: str) -> bool:
    normalized = str(text or "").strip()
    return len(tokenize(normalized)) >= 2 and bool(CLAUSE_SIGNAL_PATTERN.search(normalized))


def _split_compound_claim_text(claim_text: str, *, max_parts: int = 4) -> list[str]:
    parts = [re.sub(r"\s+", " ", str(claim_text or "").strip())]
    if not parts[0]:
        return []

    changed = True
    while changed and len(parts) < max_parts:
        changed = False
        next_parts: list[str] = []

        for part in parts:
            split_parts = None
            for pattern in CLAUSE_SPLIT_PATTERNS:
                candidates = [
                    candidate.strip(" ,.")
                    for candidate in re.split(pattern, part)
                    if candidate.strip(" ,.")
                ]
                if len(candidates) > 1 and all(_contains_clause_signal(candidate) for candidate in candidates):
                    split_parts = candidates
                    break

            if split_parts is None:
                candidates = [
                    candidate.strip(" ,.")
                    for candidate in re.split(r"\s+\band\b\s+", part)
                    if candidate.strip(" ,.")
                ]
                if len(candidates) == 2 and all(_contains_clause_signal(candidate) for candidate in candidates):
                    split_parts = candidates

            if split_parts and len(split_parts) > 1:
                next_parts.extend(split_parts)
                changed = True
            else:
                next_parts.append(part.strip(" ,."))

        parts = next_parts[:max_parts]

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = re.sub(r"\s+", " ", part.strip(" ,."))
        key = normalized.lower()
        if len(tokenize(normalized)) < 2 or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)

    return deduped if len(deduped) > 1 else []


def _fallback_response(claim: dict, evidence: dict, message: str) -> dict:
    risk_flags = [message]
    if evidence.get("error"):
        risk_flags.append(f"Retrieval warning: {evidence['error']}")
    neutral_sources = evidence.get("sources", [])
    temporal_context = _build_temporal_context(
        neutral_sources,
        claim_time_sensitive=bool(claim.get("time_sensitive", False)),
        claim_requires_recency=False,
    )

    return {
        "claim_id": claim["id"],
        "claim": claim["claim"],
        "claim_type": claim.get("claim_type", "entity"),
        "time_sensitive": claim.get("time_sensitive", False),
        "claim_requires_recency": False,
        "verdict": "UNVERIFIABLE",
        "confidence": 0.0,
        "reasoning": message,
        "supporting_sources": [],
        "conflicting_sources": [],
        "conflict_detected": False,
        "supporting_evidence": [],
        "conflicting_evidence": [],
        "mixed_evidence": [],
        "neutral_evidence": neutral_sources,
        "conflict_summary": {
            "summary": "",
            "drivers": [],
            "contradiction_types": [],
            "primary_contradiction_type": "",
            "supporting_count": 0,
            "conflicting_count": 0,
            "mixed_count": 0,
            "supporting_newest": "unknown",
            "conflicting_newest": "unknown",
            "supporting_avg_authority": 0.0,
            "conflicting_avg_authority": 0.0,
        },
        "confidence_breakdown": {
            "evidence_coverage": 0.0,
            "source_quality": 0.0,
            "freshness": 0.0,
            "clarity": 0.0,
            "support_score": 0.0,
            "conflict_score": 0.0,
        },
        "risk_flags": risk_flags,
        "query_variants": evidence.get("query_variants", []),
        "retrieval_summary": evidence.get("retrieval_summary", {}),
        "evidence_used": neutral_sources,
        "evidence_provenance": _build_evidence_provenance(neutral_sources),
        "temporal_context": temporal_context,
        "subclaim_results": [],
        "subclaim_summary": {
            "count": 0,
            "mixed_support": False,
            "verdict_breakdown": {},
            "synthesis_note": "",
        },
        "base_source_assessments": [],
        "manual_override": None,
    }


def _default_reasoning(verdict: str, confidence_breakdown: dict) -> str:
    if verdict == "TRUE":
        return (
            "High-quality sources consistently support the claim, and the weighted support score "
            f"({confidence_breakdown['support_score']}) clearly exceeds conflicting evidence."
        )
    if verdict == "FALSE":
        return (
            "The strongest available evidence contradicts the claim, and the weighted conflict score "
            f"({confidence_breakdown['conflict_score']}) clearly dominates."
        )
    if verdict == "PARTIALLY_TRUE":
        return (
            "The evidence is mixed: some sources support important parts of the claim while others "
            "contradict or qualify it, so the result is only partially reliable."
        )
    return "The retrieved sources were too weak, too sparse, or too conflicting to justify a firmer verdict."


def _reasoning_overstates_verdict(reasoning: str, verdict: str) -> bool:
    lowered = (reasoning or "").lower()
    if not lowered:
        return False

    supportive_phrases = (
        "supported by multiple sources",
        "evidence clusters around the claim being true",
        "evidence suggests that the claim is true",
        "evidence suggests the claim is true",
        "explicitly state",
        "supports the claim",
    )
    weak_phrases = (
        "too weak",
        "too sparse",
        "unverifiable",
        "could not be verified",
    )

    if verdict == "UNVERIFIABLE":
        return any(phrase in lowered for phrase in supportive_phrases)
    if verdict == "TRUE":
        return any(phrase in lowered for phrase in weak_phrases)
    if verdict == "FALSE":
        return "supports the claim" in lowered and "does not support" not in lowered
    return False


def _resolved_reasoning(reasoning: str, verdict: str, confidence_breakdown: dict) -> str:
    cleaned = str(reasoning or "").strip()
    if not cleaned or _reasoning_overstates_verdict(cleaned, verdict):
        return _default_reasoning(verdict, confidence_breakdown)
    return cleaned


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_sources(sources: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}

    for source in sources:
        source_id = str(source.get("id", "")).strip()
        source_url = str(source.get("url", "")).strip()
        key = source_id or source_url
        if not key:
            continue

        existing = deduped.get(key)
        if existing is None or float(source.get("overall_score", 0.0) or 0.0) > float(
            existing.get("overall_score", 0.0) or 0.0
        ):
            deduped[key] = dict(source)

    return list(deduped.values())


def _result_sources(result: dict) -> list[dict]:
    evidence_used = result.get("evidence_used") or []
    if evidence_used:
        return _dedupe_sources([dict(source) for source in evidence_used])

    return _dedupe_sources(
        [
            *[dict(source) for source in result.get("supporting_evidence", [])],
            *[dict(source) for source in result.get("conflicting_evidence", [])],
            *[dict(source) for source in result.get("mixed_evidence", [])],
            *[dict(source) for source in result.get("neutral_evidence", [])],
        ]
    )


def _build_evidence_provenance(sources: list[dict], *, max_sources: int = 3, max_passages: int = 2) -> list[dict]:
    provenance = []

    ranked_sources = sorted(
        (dict(source) for source in sources),
        key=lambda source: float(source.get("overall_score", 0.0) or 0.0),
        reverse=True,
    )

    for source in ranked_sources:
        snapshot = source.get("source_snapshot") or {}
        passages = sorted(
            (
                {
                    "id": str(passage.get("id", "")).strip(),
                    "text": str(passage.get("text", "")).strip(),
                    "score": round(float(passage.get("score", 0.0) or 0.0), 2),
                    "kind": str(passage.get("kind", "")).strip() or "passage",
                }
                for passage in source.get("evidence_passages", []) or []
                if str(passage.get("text", "")).strip()
            ),
            key=lambda passage: float(passage.get("score", 0.0) or 0.0),
            reverse=True,
        )[:max_passages]
        primary_quote = passages[0]["text"] if passages else str(
            source.get("snippet_used") or source.get("snippet") or ""
        ).strip()

        if not primary_quote and not snapshot:
            continue

        provenance.append(
            {
                "source_id": str(source.get("id", "")).strip(),
                "source_title": str(source.get("title", "")).strip() or "Untitled source",
                "url": str(source.get("url", "")).strip(),
                "domain": str(source.get("domain", "")).strip(),
                "stance": normalize_stance(source.get("stance")),
                "published_label": str(source.get("published_label", "")).strip() or "unknown",
                "overall_score": round(float(source.get("overall_score", 0.0) or 0.0), 2),
                "primary_quote": primary_quote,
                "top_passages": passages,
                "snapshot_id": str(snapshot.get("snapshot_id", "")).strip(),
                "captured_at": str(snapshot.get("captured_at", "")).strip(),
                "content_hash": str(snapshot.get("content_hash", "")).strip(),
            }
        )
        if len(provenance) >= max_sources:
            break

    return provenance


def _build_temporal_context(
    sources: list[dict],
    *,
    claim_time_sensitive: bool,
    claim_requires_recency: bool,
) -> dict:
    requires_recency = bool(claim_time_sensitive or claim_requires_recency)
    dated_values = [
        parse_published_date(source.get("published_date"))
        for source in sources
        if parse_published_date(source.get("published_date")) is not None
    ]
    dated_sources = [value for value in dated_values if value is not None]
    freshest = max(dated_sources) if dated_sources else None
    oldest = min(dated_sources) if dated_sources else None
    freshest_label = freshest.date().isoformat() if freshest else "unknown"
    oldest_label = oldest.date().isoformat() if oldest else "unknown"

    if requires_recency and freshest is None:
        status = "dated_evidence_missing"
        summary = "This claim is time-sensitive, but the retrieved evidence does not include any reliable publication dates."
    elif requires_recency and freshest is not None:
        age_days = max((datetime.now(timezone.utc) - freshest).days, 0)
        if age_days > 365:
            status = "stale"
            summary = f"This claim is time-sensitive, and the newest dated evidence is from {freshest_label}, so the verdict may already be stale."
        elif age_days > 90:
            status = "aging"
            summary = f"This claim is time-sensitive; the newest dated evidence is from {freshest_label}, so the verdict should be treated as aging."
        else:
            status = "current"
            summary = f"This claim is time-sensitive, and the verdict is grounded in dated evidence through {freshest_label}."
    elif freshest is not None:
        status = "dated_but_not_required"
        summary = f"Dated evidence was available through {freshest_label}, although this claim is not strongly time-sensitive."
    else:
        status = "timeless"
        summary = "This claim is not strongly time-sensitive, so the verdict does not depend on dated evidence."

    return {
        "status": status,
        "requires_recency": requires_recency,
        "dated_source_count": len(dated_sources),
        "freshest_date": freshest_label,
        "oldest_date": oldest_label,
        "summary": summary,
    }


def _promote_sparse_subclaim_calibration(
    calibration: dict,
    assessments: list[dict],
    sources: list[dict],
    *,
    claim_time_sensitive: bool,
    claim_requires_recency: bool,
) -> dict:
    if calibration.get("verdict") != "UNVERIFIABLE" or calibration.get("conflict_detected"):
        return calibration
    if calibration.get("mixed_evidence"):
        return calibration

    supporting = calibration.get("supporting_evidence", []) or []
    conflicting = calibration.get("conflicting_evidence", []) or []
    if bool(supporting) == bool(conflicting):
        return calibration

    decisive_evidence = supporting or conflicting
    if len(decisive_evidence) != 1:
        return calibration

    decisive_source = decisive_evidence[0]
    source_id = str(decisive_source.get("id", "")).strip()
    assessment = next(
        (item for item in assessments if str(item.get("source_id", "")).strip() == source_id),
        None,
    )
    if assessment is None:
        return calibration

    assessment_strength = float(assessment.get("strength", 0.0) or 0.0)
    signal_strength = _source_signal_strength(decisive_source)
    has_grounded_passage = any(
        float(passage.get("score", 0.0) or 0.0) >= 0.72
        for passage in decisive_source.get("evidence_passages", []) or []
    )
    if assessment_strength < 0.78 or signal_strength < 0.78 or not has_grounded_passage:
        return calibration

    if (claim_time_sensitive or claim_requires_recency) and parse_published_date(
        decisive_source.get("published_date")
    ) is None:
        return calibration

    verdict = "TRUE" if supporting else "FALSE"
    base_confidence = max(
        float(calibration.get("confidence", 0.0) or 0.0),
        0.46
        + (0.15 * signal_strength)
        + (0.14 * assessment_strength)
        + (0.07 * float(decisive_source.get("authority_score", 0.0) or 0.0)),
    )
    confidence = round(min(max(base_confidence, 0.58), 0.72), 2)
    risk_flags = list(
        dict.fromkeys(
            [
                *(calibration.get("risk_flags", []) or []),
                "Subclaim verdict rests on one decisive grounded source.",
            ]
        )
    )

    return {
        **calibration,
        "verdict": verdict,
        "confidence": confidence,
        "risk_flags": risk_flags,
    }


def _build_subclaim_results(
    claim: dict,
    sources: list[dict],
    *,
    claim_requires_recency: bool = False,
    empty_authoritative_queries: list[str] = None,
) -> tuple[list[dict], dict]:
    subclaim_texts = _split_compound_claim_text(str(claim.get("claim", "") or ""))
    if not subclaim_texts:
        return [], {
            "count": 0,
            "mixed_support": False,
            "verdict_breakdown": {},
            "synthesis_note": "",
        }

    subclaim_results = []
    for index, subclaim_text in enumerate(subclaim_texts, start=1):
        subclaim = {
            "id": f"{claim.get('id', 'claim')}-sub{index}",
            "claim": subclaim_text,
            "claim_type": claim.get("claim_type", "entity"),
            "time_sensitive": bool(claim.get("time_sensitive", False)),
        }
        assessments = _normalize_assessments_for_claim(
            subclaim,
            _build_heuristic_assessments(subclaim, sources),
            sources,
        )
        if not assessments:
            continue

        calibration = calibrate_verdict(
            assessments=assessments,
            sources=sources,
            claim_text=subclaim_text,
            claim_time_sensitive=bool(claim.get("time_sensitive", False)),
            claim_requires_recency=claim_requires_recency,
            empty_authoritative_queries=empty_authoritative_queries,
        )
        calibration = _promote_sparse_subclaim_calibration(
            calibration,
            assessments,
            sources,
            claim_time_sensitive=bool(claim.get("time_sensitive", False)),
            claim_requires_recency=claim_requires_recency,
        )
        evidence_used = sorted(
            (
                calibration["supporting_evidence"]
                + calibration["conflicting_evidence"]
                + calibration["mixed_evidence"]
                + calibration["neutral_evidence"]
            ),
            key=lambda source: source.get("overall_score", 0.0),
            reverse=True,
        )
        subclaim_results.append(
            {
                "subclaim_id": subclaim["id"],
                "claim": subclaim_text,
                "verdict": calibration["verdict"],
                "confidence": calibration["confidence"],
                "conflict_detected": calibration["conflict_detected"],
                "supporting_source_count": len(calibration["supporting_evidence"]),
                "conflicting_source_count": len(calibration["conflicting_evidence"]),
                "mixed_source_count": len(calibration["mixed_evidence"]),
                "risk_flags": calibration["risk_flags"],
                "evidence_provenance": _build_evidence_provenance(evidence_used, max_sources=2, max_passages=1),
            }
        )

    verdict_breakdown: dict[str, int] = {}
    for item in subclaim_results:
        verdict = str(item.get("verdict", "UNVERIFIABLE"))
        verdict_breakdown[verdict] = verdict_breakdown.get(verdict, 0) + 1

    mixed_support = len(verdict_breakdown) > 1
    synthesis_note = (
        "Subclaim review found that different parts of this claim resolve differently."
        if mixed_support
        else (
            f"All {len(subclaim_results)} subclaims resolved the same way."
            if subclaim_results
            else ""
        )
    )

    return subclaim_results, {
        "count": len(subclaim_results),
        "mixed_support": mixed_support,
        "verdict_breakdown": verdict_breakdown,
        "synthesis_note": synthesis_note,
    }


def _apply_subclaim_synthesis(result: dict, subclaim_results: list[dict], subclaim_summary: dict) -> dict:
    result["subclaim_results"] = subclaim_results
    result["subclaim_summary"] = subclaim_summary
    if not subclaim_results:
        return result

    has_true = any(item.get("verdict") == "TRUE" for item in subclaim_results)
    has_false = any(item.get("verdict") == "FALSE" for item in subclaim_results)
    has_partial = any(item.get("verdict") == "PARTIALLY_TRUE" for item in subclaim_results)
    has_unverifiable = any(item.get("verdict") == "UNVERIFIABLE" for item in subclaim_results)
    synthesis_note = str(subclaim_summary.get("synthesis_note", "")).strip()

    if subclaim_summary.get("mixed_support") and synthesis_note:
        result["risk_flags"] = list(dict.fromkeys([*result.get("risk_flags", []), synthesis_note]))

    decisive_parent = result.get("verdict") in {"TRUE", "FALSE"}
    should_downgrade = (
        decisive_parent
        and (
            (result.get("verdict") == "TRUE" and (has_false or has_partial or has_unverifiable))
            or (result.get("verdict") == "FALSE" and (has_true or has_partial or has_unverifiable))
            or (has_true and has_false)
        )
    )
    should_promote_partial = (
        result.get("verdict") == "UNVERIFIABLE"
        and has_true
        and (has_false or has_partial)
    )
    if should_downgrade or should_promote_partial:
        result["verdict"] = "PARTIALLY_TRUE"
        current_confidence = float(result.get("confidence", 0.0) or 0.0)
        result["confidence"] = (
            min(current_confidence, 0.74)
            if should_downgrade
            else max(min(current_confidence, 0.68), 0.52)
        )
        if synthesis_note:
            result["reasoning"] = f"{result.get('reasoning', '').strip()} {synthesis_note}".strip()

    return result


def _assessment_snapshot(result: dict) -> list[dict]:
    existing = result.get("base_source_assessments") or result.get("source_assessments") or []
    if existing:
        return [
            {
                "source_id": str(item.get("source_id", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "stance": normalize_stance(item.get("stance")),
                "strength": max(0.0, min(float(item.get("strength", 0.5) or 0.5), 1.0)),
                "summary": str(item.get("summary", "")).strip(),
                "snippet_used": str(item.get("snippet_used", "")).strip(),
            }
            for item in existing
            if str(item.get("source_id", "")).strip() or str(item.get("url", "")).strip()
        ]

    return [
        {
            "source_id": str(source.get("id", "")).strip(),
            "url": str(source.get("url", "")).strip(),
            "stance": normalize_stance(source.get("stance")),
            "strength": max(0.0, min(float(source.get("strength", 0.5) or 0.5), 1.0)),
            "summary": str(source.get("assessment_summary", "")).strip(),
            "snippet_used": str(source.get("snippet_used") or source.get("snippet") or "").strip(),
        }
        for source in _result_sources(result)
        if str(source.get("id", "")).strip() or str(source.get("url", "")).strip()
    ]


def _manual_override_reasoning(
    *,
    override_count: int,
    verdict: str,
    confidence_breakdown: dict,
) -> str:
    prefix = (
        f"Verdict recalculated after manually reclassifying {override_count} source"
        f"{'' if override_count == 1 else 's'}."
    )
    return f"{prefix} {_default_reasoning(verdict, confidence_breakdown)}"


def recalculate_claim_result(claim: dict, result: dict, overrides: dict[str, str] | None = None) -> dict:
    sources = _result_sources(result)
    if not sources:
        raise ValueError("This claim does not have any evidence sources to recalculate.")

    base_assessments = _assessment_snapshot(result)
    if not base_assessments:
        raise ValueError("This claim does not have any source assessments to recalculate.")

    overrides = {
        str(key).strip(): normalize_stance(value)
        for key, value in (overrides or {}).items()
        if str(key).strip()
    }

    source_keys = {
        key
        for assessment in base_assessments
        for key in (assessment.get("source_id"), assessment.get("url"))
        if str(key or "").strip()
    }
    unknown_keys = sorted(key for key in overrides if key not in source_keys)
    if unknown_keys:
        raise ValueError("One or more source overrides did not match this claim.")

    effective_assessments = []
    applied_overrides = []

    for assessment in base_assessments:
        source_id = str(assessment.get("source_id", "")).strip()
        source_url = str(assessment.get("url", "")).strip()
        original_stance = normalize_stance(assessment.get("stance"))
        effective_stance = normalize_stance(
            overrides.get(source_id) or overrides.get(source_url) or original_stance
        )
        effective_assessment = {
            "source_id": source_id,
            "stance": effective_stance,
            "strength": max(0.0, min(float(assessment.get("strength", 0.5) or 0.5), 1.0)),
            "summary": str(assessment.get("summary", "")).strip(),
            "snippet_used": str(assessment.get("snippet_used", "")).strip(),
        }
        effective_assessments.append(effective_assessment)

        if effective_stance != original_stance:
            applied_overrides.append(
                {
                    "source_id": source_id,
                    "url": source_url,
                    "from_stance": original_stance,
                    "to_stance": effective_stance,
                }
            )

    calibration = calibrate_verdict(
        assessments=effective_assessments,
        sources=sources,
        claim_text=claim.get("claim", ""),
        claim_time_sensitive=bool(claim.get("time_sensitive", False)),
        claim_requires_recency=bool(result.get("claim_requires_recency", False)),
        empty_authoritative_queries=result.get("empty_authoritative_queries", []),
    )
    conflict_summary = summarize_conflict_profile(
        claim,
        calibration["supporting_evidence"],
        calibration["conflicting_evidence"],
        calibration["mixed_evidence"],
    )
    evidence_used = sorted(
        (
            calibration["supporting_evidence"]
            + calibration["conflicting_evidence"]
            + calibration["mixed_evidence"]
            + calibration["neutral_evidence"]
        ),
        key=lambda source: source.get("overall_score", 0.0),
        reverse=True,
    )
    temporal_sources = (
        calibration["supporting_evidence"]
        + calibration["conflicting_evidence"]
        + calibration["mixed_evidence"]
    ) or evidence_used

    retrieval_warnings = [
        str(flag).strip()
        for flag in result.get("risk_flags", [])
        if str(flag).strip().startswith("Retrieval warning:")
    ]
    if applied_overrides:
        retrieval_warnings.append(
            f"Manual review changed {len(applied_overrides)} source stance"
            f"{'' if len(applied_overrides) == 1 else 's'}."
        )
    prior_override = result.get("manual_override") or {}

    next_result = {
        **result,
        "claim": claim.get("claim", result.get("claim", "")),
        "claim_type": claim.get("claim_type", result.get("claim_type", "entity")),
        "time_sensitive": bool(claim.get("time_sensitive", result.get("time_sensitive", False))),
        "supporting_sources": [source["url"] for source in calibration["supporting_evidence"]],
        "conflicting_sources": [source["url"] for source in calibration["conflicting_evidence"]],
        "supporting_evidence": calibration["supporting_evidence"],
        "conflicting_evidence": calibration["conflicting_evidence"],
        "mixed_evidence": calibration["mixed_evidence"],
        "neutral_evidence": calibration["neutral_evidence"],
        "conflict_detected": calibration["conflict_detected"],
        "conflict_summary": conflict_summary,
        "confidence_breakdown": calibration["confidence_breakdown"],
        "confidence": calibration["confidence"],
        "verdict": calibration["verdict"],
        "risk_flags": list(dict.fromkeys(calibration["risk_flags"] + retrieval_warnings)),
        "evidence_used": evidence_used,
        "evidence_provenance": _build_evidence_provenance(evidence_used),
        "temporal_context": _build_temporal_context(
            temporal_sources,
            claim_time_sensitive=bool(claim.get("time_sensitive", False)),
            claim_requires_recency=bool(result.get("claim_requires_recency", False)),
        ),
        "base_source_assessments": base_assessments,
        "manual_override": (
            {
                "active": True,
                "updated_at": _utc_now(),
                "override_count": len(applied_overrides),
                "overrides": applied_overrides,
                "base_verdict": prior_override.get("base_verdict", result.get("verdict")),
                "base_confidence": prior_override.get(
                    "base_confidence",
                    result.get("confidence"),
                ),
            }
            if applied_overrides
            else None
        ),
    }
    next_result["reasoning"] = (
        _manual_override_reasoning(
            override_count=len(applied_overrides),
            verdict=next_result["verdict"],
            confidence_breakdown=next_result["confidence_breakdown"],
        )
        if applied_overrides
        else _resolved_reasoning(
            result.get("reasoning", ""),
            next_result["verdict"],
            next_result["confidence_breakdown"],
        )
    )
    subclaim_results, subclaim_summary = _build_subclaim_results(
        claim,
        sources,
        claim_requires_recency=bool(result.get("claim_requires_recency", False)),
    )
    next_result = _apply_subclaim_synthesis(next_result, subclaim_results, subclaim_summary)
    return next_result


async def _reflect_on_verdict(claim: dict, result: dict, session_claims: list[dict] | None = None) -> dict:
    """A secondary reflection agent to check for hallucinations and logical consistency."""
    if llm is None:
        return result

    context_claims = ""
    if session_claims:
        other_claims = [c['claim'] for c in session_claims if c['id'] != claim['id']]
        if other_claims:
            context_claims = "Other claims in this document for context:\n- " + "\n- ".join(other_claims[:5])

    user_message = (
        f"Claim Under Review: {claim['claim']}\n"
        f"Proposed Verdict: {result['verdict']}\n"
        f"Proposed Reasoning: {result['reasoning']}\n\n"
        f"{context_claims}\n\n"
        "Critically evaluate if this verdict is logically sound and consistent with the provided evidence. "
        "Pay special attention to whether this claim's verdict creates a logical contradiction with the context of other claims. "
        "IMPORTANT: The 'suggested_verdict' MUST be one of: 'TRUE', 'FALSE', 'PARTIALLY_TRUE', 'UNVERIFIABLE'."
        "\n\nReturn JSON: {'correction_needed': bool, 'suggested_verdict': 'TRUE'|'FALSE'|'PARTIALLY_TRUE'|'UNVERIFIABLE', 'reasoning': '...'}"
    )

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content="You are a skeptical fact-check auditor."),
                HumanMessage(content=user_message),
            ]
        )
        reflection = _parse_json_object(
            response.content if isinstance(response.content, str) else str(response.content)
        )
        if reflection.get("correction_needed") and reflection.get("suggested_verdict"):
            suggested = str(reflection["suggested_verdict"]).strip().upper()
            if suggested in {"TRUE", "FALSE", "PARTIALLY_TRUE", "UNVERIFIABLE"}:
                reasoning = reflection.get("reasoning", "")
                if (
                    suggested in {"TRUE", "FALSE"}
                    and suggested != str(result.get("verdict", "")).strip().upper()
                    and not _reflection_can_harden_verdict(result, suggested)
                ):
                    result["risk_flags"].append(
                        f"Reflection Auditor suggested {suggested}, but FactLens kept the calibrated verdict because the direct evidence was not strong enough."
                    )
                    return result
                result["risk_flags"].append(f"Reflection Auditor corrected the initial verdict: {reasoning}")
                result["verdict"] = suggested
                result["reasoning"] = f"{result['reasoning']} (Logic Audit: {reasoning})"
                # If the auditor is correcting an UNVERIFIABLE to something decisive, 
                # we should indicate moderate confidence in that logic.
                if result["verdict"] in {"TRUE", "FALSE"}:
                    result["confidence"] = max(result["confidence"], 0.62)
        return result
    except Exception:
        return result


async def cross_claim_audit(results: list[dict]) -> list[dict]:
    """
    Perform a final session-wide audit to ensure logical consistency between ALL results.
    If Claim A is TRUE and contradicts Claim B, Claim B must be corrected.
    """
    if llm is None or not results or len(results) < 2:
        return results

    results_summary = "\n".join(
        f"Result {r['claim_id']}: '{r['claim']}' is {r['verdict']}."
        for r in results
    )

    user_message = (
        "You are the Lead Fact-Check Editor. Review these verified claims for the SAME document.\n\n"
        f"{results_summary}\n\n"
        "Identify any logical contradictions. For example, if one claim says an entity is in Location A and it is VERIFIED TRUE, "
        "but another claim says the SAME entity is in Location B, the second claim MUST BE FACTUALLY FALSE.\n\n"
        "Focus on: \n"
        "1. Location contradictions for unique landmarks/entities.\n"
        "2. Numeric contradictions (Statistics that cannot both be true simultaneously).\n"
        "3. Temporal contradictions.\n\n"
        "If you find a contradiction where one result is more definitive (TRUE/FALSE) than another (PARTIALLY_TRUE/UNVERIFIABLE), "
        "the definitive one should dictate the correction for the others.\n\n"
        "Return JSON: {'corrections': [{'claim_id': '...', 'new_verdict': '...', 'reasoning': '...'}]}"
    )

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content="You are a senior fact-checking editor ensuring document-wide consistency."),
                HumanMessage(content=user_message),
            ]
        )
        audit = _parse_json_object(
            response.content if isinstance(response.content, str) else str(response.content)
        )
        
        corrections = audit.get("corrections", [])
        if not corrections:
            return results

        updated_results = []
        for result in results:
            updated = dict(result)
            for corr in corrections:
                if str(corr.get("claim_id")) == str(result.get("claim_id")):
                    new_verdict = str(corr.get("new_verdict", "")).upper()
                    if new_verdict in {"TRUE", "FALSE", "PARTIALLY_TRUE", "UNVERIFIABLE"} and new_verdict != result["verdict"]:
                        reasoning = corr.get("reasoning", "Document-wide consistency check.")
                        updated["verdict"] = new_verdict
                        updated["reasoning"] = f"{updated['reasoning']} (Cross-Claim Audit: {reasoning})"
                        updated["risk_flags"].append(f"Global Audit corrected this result for consistency: {reasoning}")
                        if new_verdict in {"TRUE", "FALSE"}:
                            updated["confidence"] = max(updated["confidence"], 0.75)
            updated_results.append(updated)
        
        return updated_results
    except Exception:
        return results


async def verify_claim(claim: dict, evidence: dict, session_claims: list[dict] | None = None) -> dict:
    empty_authoritative_queries = evidence.get("empty_authoritative_queries", [])
    if not evidence["sources"]:
        # NEW: Even if no sources, if we have empty authoritative queries, 
        # it might be FALSE instead of just UNVERIFIABLE.
        if empty_authoritative_queries:
            # We'll continue to calibrate_verdict which now handles this
            pass
        else:
            return _fallback_response(
                claim,
                evidence,
                "No evidence could be retrieved for this claim.",
            )

    parsed: dict = {}
    llm_failure: str | None = None
    llm_assessments: list[dict] = []

    if llm is not None:
        evidence_block = "".join(
            f"Source {source['id']}\n"
            f"Title: {source['title']}\n"
            f"URL: {source['url']}\n"
            f"Domain: {source['domain']}\n"
            f"Published: {source['published_label']}\n"
            f"Authority score: {source['authority_score']}\n"
            f"Relevance score: {source['relevance_score']}\n"
            + "".join(
                f"Grounded passage {index}: {passage.get('text', '')}\n"
                for index, passage in enumerate(source.get("evidence_passages", []), start=1)
                if passage.get("text")
            )
            + f"Snippet fallback: {source['snippet']}\n\n"
            for source in evidence["sources"]
        )

        context_snippet = ""
        if session_claims:
            other_claims = [c['claim'] for c in session_claims if c['id'] != claim['id']]
            if other_claims:
                context_snippet = "BROADER CONTEXT (Other claims in document):\n- " + "\n- ".join(other_claims[:5]) + "\n\n"

        user_message = (
            f"{context_snippet}"
            f"TARGET CLAIM: {claim['claim']}\n"
            f"Claim type: {claim.get('claim_type', 'entity')}\n"
            f"Time sensitive: {claim.get('time_sensitive', False)}\n\n"
            f"EVIDENCE PASSAGES:\n{evidence_block}"
        )

        # Self-consistency approach: run verification multiple times and aggregate results (PARALLELIZED)
        async def _run_single_verification():
            try:
                response = await llm.ainvoke(
                    [
                        SystemMessage(content=SYSTEM_PROMPT),
                        HumanMessage(content=user_message),
                    ]
                )
                try:
                    return _parse_json_object(
                        response.content if isinstance(response.content, str) else str(response.content)
                    )
                except Exception:
                    retry_response = await llm.ainvoke(
                        [
                            SystemMessage(content=SYSTEM_PROMPT),
                            HumanMessage(
                                content=(
                                    f"{user_message}\n\n"
                                    "Return strict JSON with double-quoted keys and values. "
                                    "Do not include raw quoted passages inside the JSON."
                                )
                            ),
                        ]
                    )
                    return _parse_json_object(
                        retry_response.content
                        if isinstance(retry_response.content, str)
                        else str(retry_response.content)
                    )
            except Exception as exc:
                nonlocal llm_failure
                if not llm_failure:
                    llm_failure = str(exc)
                return None

        # Execute 3 runs in parallel
        raw_results = await asyncio.gather(*[_run_single_verification() for _ in range(3)])
        verification_results = [r for r in raw_results if r is not None]
        
        # Aggregate results from multiple runs
        if verification_results:
            # Combine source assessments from all runs
            all_assessments = []
            for result in verification_results:
                assessments = [
                    _coerce_assessment(item)
                    for item in result.get("source_assessments", [])
                    if str(item.get("source_id", "")).strip()
                ]
                all_assessments.extend(assessments)
            
            # Deduplicate and combine assessments by source_id
            assessments_by_source = {}
            for assessment in all_assessments:
                source_id = assessment.get("source_id")
                if source_id not in assessments_by_source:
                    assessments_by_source[source_id] = []
                assessments_by_source[source_id].append(assessment)
            
            # Average the strength values
            llm_assessments = []
            for source_id, assessments_list in assessments_by_source.items():
                if not assessments_list:
                    continue
                
                total_strength = sum(a.get("strength", 0.0) for a in assessments_list)
                avg_strength = total_strength / len(assessments_list)
                
                # Use the most common stance
                stances = [a.get("stance", "IRRELEVANT") for a in assessments_list]
                stance = max(set(stances), key=stances.count) if stances else "IRRELEVANT"
                
                # Combine summaries (use the first one or concatenate if different)
                summaries = [a.get("summary", "") for a in assessments_list if a.get("summary")]
                summary = summaries[0] if summaries else ""
                if len(summaries) > 1 and len(set(summaries)) > 1:
                    summary = f"Multiple assessments: {'; '.join(summaries[:2])}"
                
                # Combine snippets (use the first one)
                snippets = [a.get("snippet_used", "") for a in assessments_list if a.get("snippet_used")]
                snippet_used = snippets[0] if snippets else ""
                
                llm_assessments.append({
                    "source_id": source_id,
                    "stance": stance,
                    "strength": avg_strength,
                    "summary": summary,
                    "snippet_used": snippet_used,
                })
            # Use the first successful parsed result for other metadata like claim_requires_recency
            parsed = verification_results[0] if verification_results else {}
        else:
            # All runs failed, fall back to single attempt
            try:
                response = await llm.ainvoke(
                    [
                        SystemMessage(content=SYSTEM_PROMPT),
                        HumanMessage(content=user_message),
                    ]
                )
                try:
                    parsed = _parse_json_object(
                        response.content if isinstance(response.content, str) else str(response.content)
                    )
                except Exception:
                    retry_response = await llm.ainvoke(
                        [
                            SystemMessage(content=SYSTEM_PROMPT),
                            HumanMessage(
                                content=(
                                    f"{user_message}\n\n"
                                    "Return strict JSON with double-quoted keys and values. "
                                    "Do not include raw quoted passages inside the JSON."
                                )
                            ),
                        ]
                    )
                    parsed = _parse_json_object(
                        retry_response.content
                        if isinstance(retry_response.content, str)
                        else str(retry_response.content)
                    )

                llm_assessments = [
                    _coerce_assessment(item)
                    for item in parsed.get("source_assessments", [])
                    if str(item.get("source_id", "")).strip()
                ]
            except Exception as exc:
                llm_failure = str(exc)
    else:
        llm_failure = llm_descriptor.issue or "No verification model is configured."

    heuristic_assessments = _normalize_assessments_for_claim(
        claim,
        _build_heuristic_assessments(claim, evidence["sources"]),
        evidence["sources"],
    )
    normalized_llm_assessments = (
        _normalize_assessments_for_claim(claim, llm_assessments, evidence["sources"])
        if llm_assessments
        else []
    )
    if normalized_llm_assessments:
        assessments = _combine_assessments_with_heuristics(
            normalized_llm_assessments,
            heuristic_assessments,
        )
    else:
        assessments = heuristic_assessments

    assessments = _normalize_assessments_for_claim(claim, assessments, evidence["sources"])
    if not assessments:
        return _fallback_response(
            claim,
            evidence,
            "Verification could not classify any of the retrieved sources.",
        )

    calibration = calibrate_verdict(
        assessments=assessments,
        sources=evidence["sources"],
        claim_text=claim.get("claim", ""),
        claim_time_sensitive=claim.get("time_sensitive", False),
        claim_requires_recency=bool(parsed.get("claim_requires_recency", False)),
        empty_authoritative_queries=empty_authoritative_queries,
    )
    heuristic_calibration = None
    if normalized_llm_assessments and heuristic_assessments:
        heuristic_calibration = calibrate_verdict(
            heuristic_assessments,
            evidence["sources"],
            claim_text=claim.get("claim", ""),
            claim_time_sensitive=claim.get("time_sensitive", False),
            claim_requires_recency=bool(parsed.get("claim_requires_recency", False)),
            empty_authoritative_queries=empty_authoritative_queries,
        )
        calibration, cross_check_flags = _apply_assessment_cross_check(
            calibration,
            llm_assessments=normalized_llm_assessments,
            heuristic_assessments=heuristic_assessments,
            heuristic_calibration=heuristic_calibration,
        )
    else:
        cross_check_flags = []

    llm_risk_flags = [
        str(flag).strip()
        for flag in parsed.get("risk_flags", [])
        if str(flag).strip()
    ]
    if llm_failure:
        llm_risk_flags.append(
            "Verification model output was unavailable or unusable, so FactLens used conservative heuristic source assessment."
        )
    if evidence.get("error"):
        llm_risk_flags.append(f"Retrieval warning: {evidence['error']}")

    combined_risk_flags = list(
        dict.fromkeys(calibration["risk_flags"] + cross_check_flags + llm_risk_flags)
    )
    base_source_assessments = [
        {
            "source_id": assessment["source_id"],
            "url": next(
                (
                    str(source.get("url", "")).strip()
                    for source in evidence["sources"]
                    if source.get("id") == assessment["source_id"]
                ),
                "",
            ),
            "stance": assessment["stance"],
            "strength": assessment["strength"],
            "summary": assessment["summary"],
            "snippet_used": assessment["snippet_used"],
        }
        for assessment in assessments
    ]
    conflict_summary = summarize_conflict_profile(
        claim,
        calibration["supporting_evidence"],
        calibration["conflicting_evidence"],
        calibration["mixed_evidence"],
    )
    final_result = _assemble_final_result(
        claim=claim,
        calibration=calibration,
        parsed=parsed,
        evidence=evidence,
        base_source_assessments=base_source_assessments,
        combined_risk_flags=combined_risk_flags,
        conflict_summary=conflict_summary,
        cross_check_flags=cross_check_flags,
    )

    subclaim_results, subclaim_summary = _build_subclaim_results(
        claim,
        evidence["sources"],
        claim_requires_recency=bool(parsed.get("claim_requires_recency", False)),
        empty_authoritative_queries=empty_authoritative_queries,
    )
    final_result["subclaim_results"] = subclaim_results
    final_result["subclaim_summary"] = subclaim_summary
    final_result = _apply_subclaim_synthesis(final_result, subclaim_results, subclaim_summary)

    # Run Reflection Auditor for high-stakes claims or low confidence
    if final_result["confidence"] < 0.7 or final_result["conflict_detected"]:
        final_result = await _reflect_on_verdict(claim, final_result, session_claims=session_claims)

    return final_result


def _build_reasoning_steps(
    claim: dict,
    calibration: dict,
    parsed: dict,
    evidence: dict,
    base_source_assessments: list,
    cross_check_flags: list,
) -> list[str]:
    """Build a chain-of-thought step list from calibration data when the LLM does not provide one."""
    steps: list[str] = []
    claim_text = str(claim.get("claim", "")).strip()
    source_count = len(evidence.get("sources", []))
    breakdown = calibration.get("confidence_breakdown", {})
    support_score = round(breakdown.get("support_score", 0.0), 2)
    conflict_score = round(breakdown.get("conflict_score", 0.0), 2)
    verdict = calibration.get("verdict", "UNVERIFIABLE")
    confidence = calibration.get("confidence", 0.0)
    conflict_detected = calibration.get("conflict_detected", False)

    # Step 1: Claim parsing
    claim_type = str(claim.get("claim_type", "entity")).lower()
    steps.append(f"Parsed the claim as a {claim_type} assertion and identified key entities for evidence lookup.")

    # Step 2: Evidence retrieval
    q_count = len(evidence.get("query_variants", []))
    steps.append(
        f"Issued {q_count} search {'query' if q_count == 1 else 'queries'} across multiple providers "
        f"and retrieved {source_count} distinct source{'s' if source_count != 1 else ''}."
    )

    # Step 3: Per-source assessment summary
    support_sources = [a for a in base_source_assessments if a.get("stance") == "SUPPORT"]
    conflict_sources = [a for a in base_source_assessments if a.get("stance") == "CONFLICT"]
    mixed_sources = [a for a in base_source_assessments if a.get("stance") == "MIXED"]
    irrelevant_sources = [a for a in base_source_assessments if a.get("stance") == "IRRELEVANT"]
    assessment_parts = []
    if support_sources:
        assessment_parts.append(f"{len(support_sources)} supporting")
    if conflict_sources:
        assessment_parts.append(f"{len(conflict_sources)} conflicting")
    if mixed_sources:
        assessment_parts.append(f"{len(mixed_sources)} mixed")
    if irrelevant_sources:
        assessment_parts.append(f"{len(irrelevant_sources)} irrelevant")
    assessment_summary = ", ".join(assessment_parts) if assessment_parts else "no clearly relevant"
    steps.append(f"Assessed each source against the claim: {assessment_summary} source(s) found.")

    # Step 4: Scoring
    steps.append(
        f"Computed weighted evidence scores — support: {support_score:.2f}, conflict: {conflict_score:.2f}. "
        + ("Evidence conflict was detected." if conflict_detected else "No significant evidence conflict detected.")
    )

    # Step 5: Auditor / reflection
    reflection_text = str(parsed.get("self_reflection", "")).strip()
    auditor_suggestion = "No reflection override was applied."
    if cross_check_flags:
        for flag in cross_check_flags:
            if "Reflection Auditor" in flag or "auditor" in flag.lower():
                auditor_suggestion = flag
                break
    if reflection_text:
        steps.append(f"Self-reflection: {reflection_text[:200].rstrip()}")
    else:
        steps.append(f"Reflection Auditor checked for contradictions. {auditor_suggestion}")

    # Step 6: Final verdict
    verdict_label = {
        "TRUE": "TRUE",
        "FALSE": "FALSE",
        "PARTIALLY_TRUE": "PARTIALLY TRUE",
        "UNVERIFIABLE": "UNVERIFIABLE",
    }.get(verdict, verdict)
    steps.append(
        f"Final verdict: {verdict_label} (confidence {round(confidence * 100)}%). "
        f"{'Conflict in evidence led to a nuanced assessment.' if conflict_detected else 'Evidence was consistent with this verdict.'}"
    )

    return steps


def _assemble_final_result(
    claim: dict,
    calibration: dict,
    parsed: dict,
    evidence: dict,
    base_source_assessments: list,
    combined_risk_flags: list,
    conflict_summary: dict,
    cross_check_flags: list,
) -> dict:
    """Assemble the final verification result dict."""
    reasoning = _resolved_reasoning(
        str(parsed.get("reasoning", "")).strip(),
        calibration["verdict"],
        calibration["confidence_breakdown"],
    )

    # Use LLM-provided steps if available, otherwise build them from calibration data
    llm_steps = [str(s).strip() for s in parsed.get("reasoning_steps", []) if str(s).strip()]
    reasoning_steps = llm_steps or _build_reasoning_steps(
        claim, calibration, parsed, evidence, base_source_assessments, cross_check_flags
    )

    temporal_sources = (
        calibration["supporting_evidence"]
        + calibration["conflicting_evidence"]
        + calibration["mixed_evidence"]
    ) or (
        calibration["supporting_evidence"]
        + calibration["conflicting_evidence"]
        + calibration["mixed_evidence"]
        + calibration["neutral_evidence"]
    )

    evidence_used = sorted(
        (
            calibration["supporting_evidence"]
            + calibration["conflicting_evidence"]
            + calibration["mixed_evidence"]
            + calibration["neutral_evidence"]
        ),
        key=lambda source: source.get("overall_score", 0.0),
        reverse=True,
    )

    return {
        "claim_id": claim["id"],
        "claim": claim["claim"],
        "claim_type": claim.get("claim_type", "entity"),
        "time_sensitive": claim.get("time_sensitive", False),
        "claim_requires_recency": bool(parsed.get("claim_requires_recency", False)),
        "verdict": calibration["verdict"],
        "confidence": calibration["confidence"],
        "reasoning": reasoning,
        "reasoning_steps": reasoning_steps,
        "self_reflection": parsed.get("self_reflection", ""),
        "supporting_sources": [source["url"] for source in calibration["supporting_evidence"]],
        "conflicting_sources": [source["url"] for source in calibration["conflicting_evidence"]],
        "conflict_detected": calibration["conflict_detected"],
        "supporting_evidence": calibration["supporting_evidence"],
        "conflicting_evidence": calibration["conflicting_evidence"],
        "mixed_evidence": calibration["mixed_evidence"],
        "neutral_evidence": calibration["neutral_evidence"],
        "conflict_summary": conflict_summary,
        "confidence_breakdown": calibration["confidence_breakdown"],
        "risk_flags": combined_risk_flags,
        "query_variants": evidence.get("query_variants", []),
        "retrieval_summary": evidence.get("retrieval_summary", {}),
        "evidence_used": evidence_used,
        "evidence_provenance": _build_evidence_provenance(evidence_used),
        "temporal_context": _build_temporal_context(
            temporal_sources,
            claim_time_sensitive=bool(claim.get("time_sensitive", False)),
            claim_requires_recency=bool(parsed.get("claim_requires_recency", False)),
        ),
        "base_source_assessments": base_source_assessments,
        "empty_authoritative_queries": calibration.get("empty_authoritative_queries", []),
        "subclaim_results": [],
        "subclaim_summary": {
            "count": 0,
            "mixed_support": False,
            "verdict_breakdown": {},
            "synthesis_note": "",
        },
        "manual_override": None,
    }
