from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


API_ORIGIN = os.getenv("FACTLENS_API_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
RESULTS_PATH = (
    Path(__file__).resolve().parents[1] / "results" / "live-api-validation.json"
)

TEXT_SAMPLE = (
    "The Pacific Ocean is the largest ocean on Earth. "
    "Mount Everest is the highest mountain above sea level. "
    "The Eiffel Tower is in Paris."
)
URL_CANDIDATES = [
    "https://en.wikipedia.org/wiki/Paris",
    "https://simple.wikipedia.org/wiki/Paris",
    "https://en.wikipedia.org/wiki/Eiffel_Tower",
]
CONFLICT_CANDIDATES = [
    "The Eiffel Tower is 330 meters tall.",
    "Mount Everest is 8848 meters tall.",
    "The Amazon River is the longest river in the world.",
    "Pluto is the ninth planet in the solar system.",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_json(
    session: requests.Session,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 300,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    response = session.request(
        method,
        f"{API_ORIGIN}{path}",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json() if response.content else {}
    return response.status_code, body, dict(response.headers)


def request_raw(
    session: requests.Session,
    method: str,
    path: str,
    *,
    timeout: int = 300,
) -> tuple[int, bytes, dict[str, str]]:
    response = session.request(method, f"{API_ORIGIN}{path}", timeout=timeout)
    response.raise_for_status()
    return response.status_code, response.content, dict(response.headers)


def stream_events(
    session: requests.Session,
    path: str,
    payload: dict[str, Any],
    *,
    timeout: int = 600,
) -> list[dict[str, Any]]:
    with session.post(
        f"{API_ORIGIN}{path}",
        json=payload,
        headers={"Accept": "text/event-stream"},
        stream=True,
        timeout=timeout,
    ) as response:
        response.raise_for_status()
        events: list[dict[str, Any]] = []
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            raw_payload = line[5:].strip()
            if not raw_payload:
                continue
            events.append(json.loads(raw_payload))
        return events


def build_review_payload(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_text": draft.get("source_text", ""),
        "claims": draft.get("claims", []),
        "input_mode": draft.get("input_mode", "text"),
        "input_value": draft.get("input_value"),
        "source_capture": draft.get("source_capture"),
        "claim_extraction": draft.get("claim_extraction"),
        "ai_detection": draft.get("ai_detection"),
        "media_detection": draft.get("media_detection"),
    }


def analyze_reviewed(
    session: requests.Session,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    events = stream_events(session, "/analyze-reviewed", payload)
    error_event = next((event for event in events if event.get("type") == "error"), None)
    if error_event is not None:
        raise RuntimeError(error_event.get("message") or "Live analyze-reviewed run failed.")

    report_event = next(
        (event for event in events if event.get("type") == "report_created"),
        None,
    )
    if report_event is None:
        raise RuntimeError("Live analyze-reviewed run did not return a report id.")

    report_id = str(report_event.get("data", {}).get("report_id", "")).strip()
    if not report_id:
        raise RuntimeError("Live analyze-reviewed run returned an empty report id.")

    _, report, _ = request_json(session, "GET", f"/reports/{report_id}")
    return report_id, report, events


def verify_single_claim(
    session: requests.Session,
    claim_text: str,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    return analyze_reviewed(
        session,
        {
            "source_text": claim_text,
            "claims": [
                {
                    "id": "1",
                    "claim": claim_text,
                    "context": claim_text,
                }
            ],
            "input_mode": "text",
            "input_value": claim_text,
        },
    )


def result_snapshot(report: dict[str, Any], index: int = 0) -> dict[str, Any]:
    result = (report.get("results") or [])[index]
    return {
        "claim_id": result.get("claim_id"),
        "claim": result.get("claim"),
        "verdict": result.get("verdict"),
        "confidence": result.get("confidence"),
        "conflict_detected": bool(result.get("conflict_detected")),
        "supporting_count": len(result.get("supporting_evidence") or []),
        "conflicting_count": len(result.get("conflicting_evidence") or []),
        "mixed_count": len(result.get("mixed_evidence") or []),
        "neutral_count": len(result.get("neutral_evidence") or []),
        "risk_flags": result.get("risk_flags") or [],
        "manual_override": result.get("manual_override"),
    }


def first_conflict_report(
    session: requests.Session,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []

    for claim_text in CONFLICT_CANDIDATES:
        report_id, report, _events = verify_single_claim(session, claim_text)
        snapshot = result_snapshot(report)
        attempts.append(
            {
                "claim_text": claim_text,
                "report_id": report_id,
                **snapshot,
            }
        )
        if snapshot["conflict_detected"] or (
            snapshot["supporting_count"] > 0 and snapshot["conflicting_count"] > 0
        ):
            return {
                "claim_text": claim_text,
                "report_id": report_id,
                "report": report,
                "snapshot": snapshot,
            }, attempts

    return None, attempts


def build_override_payload(report: dict[str, Any], claim_index: int = 0) -> tuple[str, list[dict[str, str]]]:
    result = (report.get("results") or [])[claim_index]
    claim_id = str(result.get("claim_id", "")).strip()
    if not claim_id:
        raise RuntimeError("Report result is missing a claim id.")

    assessments = result.get("base_source_assessments") or []
    overrides: list[dict[str, str]] = []
    for assessment in assessments:
        source_id = str(assessment.get("source_id", "")).strip()
        source_url = str(assessment.get("url", "")).strip()
        current_stance = str(assessment.get("stance", "")).strip().upper()
        if current_stance == "CONFLICT":
            next_stance = "SUPPORT"
        else:
            next_stance = "CONFLICT"

        override: dict[str, str] = {"stance": next_stance}
        if source_id:
            override["source_id"] = source_id
        elif source_url:
            override["source_url"] = source_url
        else:
            continue
        overrides.append(override)

    if not overrides:
        raise RuntimeError("Report result does not contain any overrideable sources.")

    return claim_id, overrides


def main() -> int:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    owner_session = requests.Session()
    owner_session.headers.update({"Accept": "application/json"})

    summary: dict[str, Any] = {
        "generated_at": utc_now(),
        "api_origin": API_ORIGIN,
        "status": "passed",
        "scenarios": {},
    }

    try:
        health_status, health_body, _ = request_json(owner_session, "GET", "/health", timeout=20)
        summary["health"] = {"status_code": health_status, "body": health_body}

        draft_status, draft_body, _ = request_json(
            owner_session,
            "POST",
            "/draft-claims",
            {"text": TEXT_SAMPLE},
        )
        text_report_id, text_report, text_events = analyze_reviewed(
            owner_session,
            build_review_payload(draft_body),
        )
        summary["scenarios"]["text_input"] = {
            "draft_status_code": draft_status,
            "draft_claim_count": len(draft_body.get("claims") or []),
            "review_required": bool(draft_body.get("review_required")),
            "report_id": text_report_id,
            "event_types": [event.get("type") for event in text_events],
            "result_count": len(text_report.get("results") or []),
            "viewer_can_manage": bool(text_report.get("viewer_can_manage")),
            "first_result": result_snapshot(text_report),
        }

        url_attempts: list[dict[str, Any]] = []
        selected_url: dict[str, Any] | None = None
        for candidate_url in URL_CANDIDATES:
            url_status, url_body, _ = request_json(
                owner_session,
                "POST",
                "/draft-claims",
                {"url": candidate_url},
            )
            attempt = {
                "url": candidate_url,
                "status_code": url_status,
                "claim_count": len(url_body.get("claims") or []),
                "review_required": bool(url_body.get("review_required")),
                "source_capture_mode": (url_body.get("source_capture") or {}).get("mode"),
                "source_capture_title": (url_body.get("source_capture") or {}).get("title"),
                "source_text_truncated": bool(url_body.get("source_text_truncated")),
            }
            url_attempts.append(attempt)
            if attempt["claim_count"] > 0:
                selected_url = attempt
                break

        summary["scenarios"]["url_input"] = {
            "selected": selected_url,
            "attempts": url_attempts,
        }

        conflict_report, conflict_attempts = first_conflict_report(owner_session)
        summary["scenarios"]["conflicting_evidence"] = {
            "selected": (
                {
                    "claim_text": conflict_report["claim_text"],
                    "report_id": conflict_report["report_id"],
                    **conflict_report["snapshot"],
                }
                if conflict_report
                else None
            ),
            "attempts": conflict_attempts,
        }

        export_report_id = text_report_id
        _, owner_report_detail, _ = request_json(owner_session, "GET", f"/reports/{export_report_id}")
        share_token = str(owner_report_detail.get("share_token", "")).strip()
        json_status, json_bytes, json_headers = request_raw(
            owner_session,
            "GET",
            f"/reports/{export_report_id}/export",
        )
        pdf_status, pdf_bytes, pdf_headers = request_raw(
            owner_session,
            "GET",
            f"/reports/{export_report_id}/export/pdf",
        )

        shared_session = requests.Session()
        shared_access_without_token = None
        detail_without_token_status = None
        response_without_token = shared_session.get(
            f"{API_ORIGIN}/reports/{export_report_id}",
            timeout=60,
        )
        detail_without_token_status = response_without_token.status_code
        if response_without_token.ok:
            shared_access_without_token = response_without_token.json()

        shared_detail = shared_session.get(
            f"{API_ORIGIN}/reports/{export_report_id}",
            params={"share": share_token},
            timeout=60,
        )
        shared_detail.raise_for_status()
        shared_export = shared_session.get(
            f"{API_ORIGIN}/reports/{export_report_id}/export",
            params={"share": share_token},
            timeout=60,
        )
        shared_export.raise_for_status()

        summary["scenarios"]["export_share"] = {
            "report_id": export_report_id,
            "share_token_present": bool(share_token),
            "owner_json_export": {
                "status_code": json_status,
                "content_type": json_headers.get("Content-Type"),
                "content_length": len(json_bytes),
            },
            "owner_pdf_export": {
                "status_code": pdf_status,
                "content_type": pdf_headers.get("Content-Type"),
                "content_length": len(pdf_bytes),
            },
            "shared_detail_status_code": shared_detail.status_code,
            "shared_viewer_can_manage": bool(shared_detail.json().get("viewer_can_manage")),
            "shared_export_status_code": shared_export.status_code,
            "unauthorized_detail_status_code": detail_without_token_status,
            "unauthorized_detail_visible": bool(shared_access_without_token),
        }

        override_report = conflict_report["report"] if conflict_report is not None else text_report
        override_report_id = conflict_report["report_id"] if conflict_report is not None else text_report_id
        before_override = result_snapshot(override_report)
        claim_id, overrides = build_override_payload(override_report)
        _, recalculated_report, _ = request_json(
            owner_session,
            "POST",
            f"/reports/{override_report_id}/claims/{claim_id}/recalculate",
            {"overrides": overrides},
        )
        after_override = result_snapshot(recalculated_report)
        summary["scenarios"]["manual_override"] = {
            "report_id": override_report_id,
            "claim_id": claim_id,
            "override_count": len(overrides),
            "before": before_override,
            "after": after_override,
            "verdict_changed": before_override["verdict"] != after_override["verdict"],
            "confidence_changed": before_override["confidence"] != after_override["confidence"],
        }

        if not summary["scenarios"]["manual_override"]["after"]["manual_override"]:
            raise RuntimeError("Manual override did not persist on the recalculated live report.")

        if conflict_report is None:
            summary["status"] = "partial"
            summary["notes"] = [
                "No live claim candidate produced explicit conflicting evidence in this run.",
            ]

    except Exception as exc:  # noqa: BLE001
        summary["status"] = "failed"
        summary["error"] = str(exc)

    RESULTS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] in {"passed", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
