from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone


CONSERVATIVE_VERDICTS = {"PARTIALLY_TRUE", "UNVERIFIABLE"}
CONTRADICTION_DRIVER_IDS = {
    "direct debunking": "direct_debunking",
    "entity mismatch": "entity_mismatch",
    "numeric disagreement": "metric_mismatch",
    "scope mismatch": "scope_mismatch",
    "temporal drift": "date_drift",
}
HIGH_CONFIDENCE_THRESHOLD = 0.8
LOW_CONFIDENCE_THRESHOLD = 0.6


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 2) if denominator else 0.0


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _title_from_identifier(value: str) -> str:
    words = str(value or "").strip().replace("-", "_").split("_")
    return " ".join(word.capitalize() for word in words if word)


def _normalize_contradiction_types(result: dict) -> list[dict]:
    summary = result.get("conflict_summary") or {}
    raw_items = summary.get("contradiction_types") or []
    normalized = []
    seen: set[str] = set()

    for item in raw_items:
        type_id = str(item.get("id", "")).strip()
        if not type_id or type_id in seen:
            continue
        seen.add(type_id)
        normalized.append(
            {
                "id": type_id,
                "label": str(item.get("label", "")).strip() or _title_from_identifier(type_id),
            }
        )

    if normalized:
        return normalized

    for driver in summary.get("drivers") or []:
        type_id = CONTRADICTION_DRIVER_IDS.get(str(driver or "").strip().lower())
        if not type_id or type_id in seen:
            continue
        seen.add(type_id)
        normalized.append({"id": type_id, "label": _title_from_identifier(type_id)})

    return normalized


def build_report_diagnostics(report: dict, *, generated_at: str | None = None) -> dict:
    claims = list(report.get("claims") or [])
    results = list(report.get("results") or [])
    claim_extraction = dict(report.get("claim_extraction") or {})

    total_claims = len(claims)
    verified_claims = len(results)
    confidences = [_safe_float(result.get("confidence")) for result in results]
    conflict_claim_count = sum(1 for result in results if result.get("conflict_detected"))
    conservative_claim_count = sum(
        1 for result in results if str(result.get("verdict", "")).strip().upper() in CONSERVATIVE_VERDICTS
    )
    time_sensitive_claim_count = sum(
        1
        for claim, result in zip(claims, results)
        if bool(result.get("time_sensitive", claim.get("time_sensitive", False)))
    )
    compound_claim_count = sum(1 for result in results if result.get("subclaim_results"))
    low_confidence_claim_count = sum(1 for confidence in confidences if confidence < LOW_CONFIDENCE_THRESHOLD)
    high_confidence_claim_count = sum(1 for confidence in confidences if confidence >= HIGH_CONFIDENCE_THRESHOLD)
    manual_override_claim_count = sum(
        1 for result in results if bool((result.get("manual_override") or {}).get("active"))
    )
    reflection_adjusted_claim_count = sum(
        1
        for result in results
        if any(
            "reflection auditor corrected" in str(flag or "").lower()
            for flag in (result.get("risk_flags") or [])
        )
    )

    verdict_breakdown = {
        verdict: 0
        for verdict in ("TRUE", "FALSE", "PARTIALLY_TRUE", "UNVERIFIABLE")
    }
    contradiction_counter: Counter[str] = Counter()
    contradiction_labels: dict[str, str] = {}
    recovery_triggered_claim_count = 0
    first_pass_sufficient_claim_count = 0
    failed_query_count = 0
    provider_instability_claim_count = 0
    primary_source_claim_count = 0
    query_attempt_counts: list[float] = []
    source_counts: list[float] = []
    independent_source_counts: list[float] = []

    for result in results:
        verdict = str(result.get("verdict", "UNVERIFIABLE")).strip().upper()
        verdict_breakdown[verdict] = verdict_breakdown.get(verdict, 0) + 1

        retrieval_summary = dict(result.get("retrieval_summary") or {})
        query_attempt_count = _safe_int(
            retrieval_summary.get("query_attempt_count", len(result.get("query_variants") or []))
        )
        query_attempt_counts.append(float(query_attempt_count))
        source_counts.append(float(_safe_int(retrieval_summary.get("source_count", len(result.get("evidence_used") or [])))))
        independent_source_counts.append(float(_safe_int(retrieval_summary.get("independent_source_count", 0))))
        failed_queries_for_claim = _safe_int(retrieval_summary.get("failed_query_count"))
        failed_query_count += failed_queries_for_claim
        if failed_queries_for_claim > 0:
            provider_instability_claim_count += 1
        if retrieval_summary.get("recovery_triggered"):
            recovery_triggered_claim_count += 1
        if str(retrieval_summary.get("recovery_strategy", "")).strip().lower() == "not_needed":
            first_pass_sufficient_claim_count += 1
        if _safe_int(retrieval_summary.get("primary_source_count")) > 0:
            primary_source_claim_count += 1

        for contradiction_type in _normalize_contradiction_types(result):
            type_id = contradiction_type["id"]
            contradiction_counter[type_id] += 1
            contradiction_labels[type_id] = contradiction_type["label"]

    contradiction_type_breakdown = [
        {
            "id": type_id,
            "label": contradiction_labels.get(type_id, _title_from_identifier(type_id)),
            "count": count,
        }
        for type_id, count in contradiction_counter.most_common()
    ]
    top_contradiction = contradiction_type_breakdown[0] if contradiction_type_breakdown else None

    extraction_mode = str(claim_extraction.get("mode", "pending") or "pending").strip().lower()
    extraction_warning_count = len(
        [item for item in claim_extraction.get("warnings", []) if str(item or "").strip()]
    )
    extraction_review_required = extraction_mode == "heuristic"
    extraction_manual_review_completed = extraction_mode == "manual_review"

    quality_flags: list[str] = []
    if extraction_review_required:
        quality_flags.append("Claim extraction required heuristic fallback and human review.")
    elif extraction_manual_review_completed:
        quality_flags.append("Claims were manually reviewed before verification.")
    if extraction_warning_count:
        quality_flags.append(
            f"Claim extraction emitted {extraction_warning_count} warning"
            f"{'' if extraction_warning_count == 1 else 's'}."
        )
    if recovery_triggered_claim_count and _ratio(recovery_triggered_claim_count, max(verified_claims, 1)) >= 0.5:
        quality_flags.append("Retrieval relied heavily on recovery search.")
    if provider_instability_claim_count:
        quality_flags.append("One or more claims encountered provider instability during retrieval.")
    if verified_claims and _ratio(conservative_claim_count, verified_claims) >= 0.5:
        quality_flags.append("More than half of the claims resolved conservatively.")
    if top_contradiction is not None:
        quality_flags.append(
            f"Most common contradiction pattern: {top_contradiction['label']}."
        )

    return {
        "version": 1,
        "generated_at": generated_at or _utc_now(),
        "summary": {
            "total_claims": total_claims,
            "verified_claims": verified_claims,
            "completion_rate": _ratio(verified_claims, total_claims),
            "average_confidence": _mean(confidences),
            "conflict_claim_count": conflict_claim_count,
            "time_sensitive_claim_count": time_sensitive_claim_count,
            "conservative_claim_count": conservative_claim_count,
            "conservative_claim_rate": _ratio(conservative_claim_count, verified_claims),
        },
        "extraction": {
            "mode": extraction_mode,
            "source_mode": claim_extraction.get("source_mode"),
            "provider_label": claim_extraction.get("provider_label"),
            "claim_count": _safe_int(claim_extraction.get("claim_count", total_claims)),
            "warning_count": extraction_warning_count,
            "review_required": extraction_review_required,
            "manual_review_completed": extraction_manual_review_completed,
            "fallback_used": extraction_mode == "heuristic",
            "failed": extraction_mode == "failed",
            "compound_claim_count": compound_claim_count,
            "atomic_claim_rate": _ratio(max(verified_claims - compound_claim_count, 0), verified_claims),
        },
        "retrieval": {
            "recovery_triggered_claim_count": recovery_triggered_claim_count,
            "recovery_rate": _ratio(recovery_triggered_claim_count, verified_claims),
            "first_pass_sufficient_claim_count": first_pass_sufficient_claim_count,
            "avg_query_attempt_count": _mean(query_attempt_counts),
            "failed_query_count": failed_query_count,
            "provider_instability_claim_count": provider_instability_claim_count,
            "avg_sources_per_claim": _mean(source_counts),
            "avg_independent_source_count": _mean(independent_source_counts),
            "primary_source_coverage_rate": _ratio(primary_source_claim_count, verified_claims),
        },
        "verification": {
            "verdict_breakdown": verdict_breakdown,
            "low_confidence_claim_count": low_confidence_claim_count,
            "high_confidence_claim_count": high_confidence_claim_count,
            "manual_override_claim_count": manual_override_claim_count,
            "reflection_adjusted_claim_count": reflection_adjusted_claim_count,
            "contradiction_type_breakdown": contradiction_type_breakdown,
            "top_contradiction_type": top_contradiction,
        },
        "quality_flags": quality_flags,
    }
