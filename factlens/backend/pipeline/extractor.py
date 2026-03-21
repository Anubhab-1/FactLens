from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from pipeline.scoring import classify_claim_type, infer_time_sensitivity

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

SYSTEM_PROMPT = """You are a precise fact-checking assistant. Your job is to extract every
verifiable, atomic factual claim from the provided text.

Rules you must follow:
1. Each claim must be a single, independently verifiable statement of fact.
2. Do NOT include opinions, predictions, or subjective statements.
3. Do NOT rephrase -- preserve the original meaning exactly.
4. If a claim is time-sensitive (mentions current leaders, prices, rankings,
   recent events), add 'time_sensitive: true' in the object.
5. Return ONLY a valid JSON array. No explanation, no markdown, no preamble.

Output format:
[
  {
    'id': '1',
    'claim': 'The exact verifiable statement',
    'context': 'The surrounding sentence for reference',
    'time_sensitive': false
  }
]"""

SUBJECTIVE_PREFIXES = (
    "i think",
    "i believe",
    "in my opinion",
    "it seems",
    "it feels",
    "hopefully",
    "maybe",
    "perhaps",
)


def _non_empty_lines(text: str) -> list[str]:
    return [line.strip(" -•\t") for line in (text or "").splitlines() if line.strip()]


def _looks_like_outline(text: str) -> bool:
    lines = _non_empty_lines(text)
    if len(lines) < 5:
        return False

    short_line_ratio = sum(1 for line in lines if len(line) <= 60) / len(lines)
    no_punctuation_ratio = sum(1 for line in lines if not re.search(r"[.!?]$", line)) / len(lines)
    title_like_ratio = sum(
        1
        for line in lines
        if line == line.title() or re.fullmatch(r"[A-Za-z0-9 /,&()'-]+", line)
    ) / len(lines)
    verb_like_ratio = sum(
        1
        for line in lines
        if re.search(
            r"\b(is|was|were|are|has|have|had|contains|includes|became|causes|caused|"
            r"won|lost|ranked|announced|reported|stated|measured|recorded)\b",
            line.lower(),
        )
    ) / len(lines)

    return (
        short_line_ratio >= 0.75
        and no_punctuation_ratio >= 0.75
        and title_like_ratio >= 0.6
        and verb_like_ratio <= 0.3
    )


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
            raise ValueError("Could not parse claim extractor response.") from exc

    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array of claims.")
    return parsed


def _normalize_claims(claims: list[dict]) -> list[dict]:
    normalized_claims = []

    for index, claim in enumerate(claims, start=1):
        claim_text = str(claim.get("claim", "")).strip()
        context = str(claim.get("context", claim_text)).strip()
        if not claim_text:
            continue

        normalized_claims.append(
            {
                "id": str(claim.get("id", index)),
                "claim": claim_text,
                "context": context or claim_text,
                "time_sensitive": bool(
                    claim.get("time_sensitive", False) or infer_time_sensitivity(claim_text)
                ),
                "claim_type": claim.get("claim_type") or classify_claim_type(claim_text),
            }
        )

    return normalized_claims


def _split_candidate_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return []

    parts = [
        sentence.strip(" -•\t")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", normalized)
        if sentence.strip()
    ]

    candidates = []
    seen = set()
    for part in parts:
        if len(part) < 24 or len(part) > 400:
            continue

        key = part.lower()
        if key in seen:
            continue

        seen.add(key)
        candidates.append(part)

    return candidates


def _looks_verifiable(sentence: str) -> bool:
    lowered = sentence.lower().strip()
    if not lowered or lowered.endswith("?"):
        return False
    if any(lowered.startswith(prefix) for prefix in SUBJECTIVE_PREFIXES):
        return False
    if re.search(r"\b(should|could|would|might|may|opinion|best|worst)\b", lowered):
        return False
    if not re.search(r"[A-Za-z]", sentence):
        return False

    factual_signal = re.search(
        r"\b(is|was|were|are|has|have|had|contains|includes|became|won|lost|ranked|"
        r"announced|reported|said|states|measured|recorded|increased|decreased)\b",
        lowered,
    )
    numeric_signal = re.search(r"\b\d[\d,]*(\.\d+)?(%| million| billion| trillion)?\b", lowered)
    entity_signal = re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b", sentence)
    return bool(factual_signal or numeric_signal or entity_signal)


def _heuristic_extract_claims(text: str, max_claims: int = 12) -> list[dict]:
    fallback_claims = []

    for index, sentence in enumerate(_split_candidate_sentences(text), start=1):
        if not _looks_verifiable(sentence):
            continue

        fallback_claims.append(
            {
                "id": str(index),
                "claim": sentence,
                "context": sentence,
                "time_sensitive": infer_time_sensitivity(sentence),
                "claim_type": classify_claim_type(sentence),
            }
        )

        if len(fallback_claims) >= max_claims:
            break

    return fallback_claims


async def _invoke_extractor(user_message: str) -> str:
    if llm is None:
        raise RuntimeError("NVIDIA_API_KEY is not configured.")

    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]
    )
    return response.content if isinstance(response.content, str) else str(response.content)


async def extract_claims(text: str) -> list[dict]:
    if not (text or "").strip():
        return []

    if _looks_like_outline(text):
        return []

    if llm is None:
        return _heuristic_extract_claims(text)

    user_message = f"Extract all verifiable claims from this text:\n\n{text}"

    try:
        initial_response = await _invoke_extractor(user_message)
        normalized = _normalize_claims(_parse_json_array(initial_response))
        return normalized or _heuristic_extract_claims(text)
    except (json.JSONDecodeError, ValueError):
        try:
            retry_response = await _invoke_extractor(
                f"{user_message}\n\nReturn only valid JSON, no markdown code blocks."
            )
            normalized = _normalize_claims(_parse_json_array(retry_response))
            return normalized or _heuristic_extract_claims(text)
        except Exception:
            return _heuristic_extract_claims(text)
    except Exception:
        return _heuristic_extract_claims(text)
