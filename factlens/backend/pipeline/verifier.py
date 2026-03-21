from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from pipeline.scoring import calibrate_verdict, normalize_stance

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

SYSTEM_PROMPT = """You are an evidence triage analyst inside a fact-checking engine.
Your task is NOT to guess the final verdict from memory. Your task is only to
classify how each provided source relates to the claim, using only the supplied
metadata and snippets.

Rules:
1. Judge each source independently.
2. Use only the provided snippets and metadata.
3. If a source supports only part of the claim, mark it as MIXED.
4. If a source is off-topic or too vague, mark it as IRRELEVANT.
5. Flag whether the claim requires recent evidence to be judged safely.
6. Return ONLY valid JSON, with no markdown.

Return this exact shape:
{
  'reasoning': '2-4 sentence explanation of how the evidence clusters',
  'claim_requires_recency': true,
  'risk_flags': ['risk 1', 'risk 2'],
  'source_assessments': [
    {
      'source_id': 'S1',
      'stance': 'SUPPORT|CONFLICT|MIXED|IRRELEVANT',
      'strength': 0.0,
      'summary': 'One sentence about the source'
    }
  ]
}"""


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


def _fallback_response(claim: dict, evidence: dict, message: str) -> dict:
    return {
        "claim_id": claim["id"],
        "claim": claim["claim"],
        "claim_type": claim.get("claim_type", "entity"),
        "time_sensitive": claim.get("time_sensitive", False),
        "verdict": "UNVERIFIABLE",
        "confidence": 0.0,
        "reasoning": message,
        "supporting_sources": [],
        "conflicting_sources": [],
        "conflict_detected": False,
        "supporting_evidence": [],
        "conflicting_evidence": [],
        "mixed_evidence": [],
        "neutral_evidence": evidence.get("sources", []),
        "confidence_breakdown": {
            "evidence_coverage": 0.0,
            "source_quality": 0.0,
            "freshness": 0.0,
            "clarity": 0.0,
            "support_score": 0.0,
            "conflict_score": 0.0,
        },
        "risk_flags": [message],
        "query_variants": evidence.get("query_variants", []),
        "retrieval_summary": evidence.get("retrieval_summary", {}),
        "evidence_used": evidence.get("sources", []),
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


async def verify_claim(claim: dict, evidence: dict) -> dict:
    if not evidence["sources"]:
        return _fallback_response(
            claim,
            evidence,
            "No evidence could be retrieved for this claim.",
        )

    if llm is None:
        return _fallback_response(
            claim,
            evidence,
            "NVIDIA_API_KEY is not configured.",
        )

    evidence_block = "".join(
        f"Source {source['id']}\n"
        f"Title: {source['title']}\n"
        f"URL: {source['url']}\n"
        f"Domain: {source['domain']}\n"
        f"Published: {source['published_label']}\n"
        f"Authority score: {source['authority_score']}\n"
        f"Relevance score: {source['relevance_score']}\n"
        f"Snippet: {source['snippet']}\n\n"
        for source in evidence["sources"]
    )

    user_message = (
        f"Claim: {claim['claim']}\n"
        f"Claim type: {claim.get('claim_type', 'entity')}\n"
        f"Time sensitive: {claim.get('time_sensitive', False)}\n\n"
        f"Evidence:\n{evidence_block}"
    )

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
        assessments = [
            _coerce_assessment(item)
            for item in parsed.get("source_assessments", [])
            if str(item.get("source_id", "")).strip()
        ]
        calibration = calibrate_verdict(
            assessments,
            evidence["sources"],
            claim_time_sensitive=claim.get("time_sensitive", False),
            claim_requires_recency=bool(parsed.get("claim_requires_recency", False)),
        )
    except Exception as exc:
        return _fallback_response(
            claim,
            evidence,
            f"Verification failed: {exc}",
        )

    llm_risk_flags = [
        str(flag).strip()
        for flag in parsed.get("risk_flags", [])
        if str(flag).strip()
    ]
    if evidence.get("error"):
        llm_risk_flags.append(f"Retrieval warning: {evidence['error']}")

    combined_risk_flags = list(
        dict.fromkeys(calibration["risk_flags"] + llm_risk_flags)
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

    reasoning = str(parsed.get("reasoning", "")).strip() or _default_reasoning(
        calibration["verdict"], calibration["confidence_breakdown"]
    )

    return {
        "claim_id": claim["id"],
        "claim": claim["claim"],
        "claim_type": claim.get("claim_type", "entity"),
        "time_sensitive": claim.get("time_sensitive", False),
        "verdict": calibration["verdict"],
        "confidence": calibration["confidence"],
        "reasoning": reasoning,
        "supporting_sources": [source["url"] for source in calibration["supporting_evidence"]],
        "conflicting_sources": [source["url"] for source in calibration["conflicting_evidence"]],
        "conflict_detected": calibration["conflict_detected"],
        "supporting_evidence": calibration["supporting_evidence"],
        "conflicting_evidence": calibration["conflicting_evidence"],
        "mixed_evidence": calibration["mixed_evidence"],
        "neutral_evidence": calibration["neutral_evidence"],
        "confidence_breakdown": calibration["confidence_breakdown"],
        "risk_flags": combined_risk_flags,
        "query_variants": evidence.get("query_variants", []),
        "retrieval_summary": evidence.get("retrieval_summary", {}),
        "evidence_used": evidence_used,
    }
