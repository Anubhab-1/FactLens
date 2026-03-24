from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, model_validator

load_dotenv(Path(__file__).resolve().parent / ".env")

from pipeline.ai_detector import detect_ai
from pipeline.extractor import extract_claims_with_metadata
from pipeline.media_detector import detect_media
from pipeline.retriever import retrieve_evidence
from pipeline.scraper import scrape_url
from pipeline.scoring import classify_claim_type, infer_time_sensitivity
from pipeline.verifier import recalculate_claim_result, verify_claim
from pipeline.youtube import get_youtube_transcript, extract_video_id
from security import InMemoryRateLimiter, create_session_id, get_client_identifier, get_rate_limit_for_request
from settings import load_settings
from storage.report_exports import build_report_pdf
from storage.reports import (
    build_report_record,
    delete_report,
    get_report,
    list_reports,
    save_report,
    update_report_metadata,
)

settings = load_settings()
rate_limiter = InMemoryRateLimiter()

app = FastAPI(title="FactLens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials="*" not in settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None

    @model_validator(mode="after")
    def validate_input(self) -> "AnalyzeRequest":
        if not (self.text and self.text.strip()) and not (self.url and self.url.strip()):
            raise ValueError("At least one of 'text' or 'url' must be provided.")
        return self


class ReportUpdateRequest(BaseModel):
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None


class SourceStanceOverrideInput(BaseModel):
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    stance: str

    @model_validator(mode="after")
    def validate_source_reference(self) -> "SourceStanceOverrideInput":
        if not (self.source_id and self.source_id.strip()) and not (
            self.source_url and self.source_url.strip()
        ):
            raise ValueError("Each override must include source_id or source_url.")
        return self


class ClaimOverrideRequest(BaseModel):
    overrides: List[SourceStanceOverrideInput] = []


class ReviewClaimInput(BaseModel):
    id: Optional[str] = None
    claim: str
    context: Optional[str] = None
    time_sensitive: Optional[bool] = None
    claim_type: Optional[str] = None


class AnalyzeReviewedRequest(BaseModel):
    source_text: str
    claims: List[ReviewClaimInput]
    input_mode: str = "text"
    input_value: Optional[str] = None
    source_capture: Optional[dict] = None
    claim_extraction: Optional[dict] = None
    ai_detection: Optional[dict] = None
    media_detection: Optional[dict] = None

    @model_validator(mode="after")
    def validate_payload(self) -> "AnalyzeReviewedRequest":
        if not (self.source_text or "").strip():
            raise ValueError("source_text must be provided.")
        if self.input_mode not in {"text", "url"}:
            raise ValueError("input_mode must be 'text' or 'url'.")
        if not any((claim.claim or "").strip() for claim in self.claims):
            raise ValueError("At least one reviewed claim is required.")
        return self


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prepare_source_text_payload(text: str, max_chars: int = 15000) -> dict:
    normalized = (text or "").strip()
    if len(normalized) <= max_chars:
        return {
            "source_text": normalized,
            "source_text_truncated": False,
        }

    return {
        "source_text": normalized[:max_chars].rstrip(),
        "source_text_truncated": True,
    }


def _claim_sort_key(value: object) -> tuple:
    text = str(value or "").strip()
    return (0, int(text)) if text.isdigit() else (1, text)


def _sort_results(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda item: _claim_sort_key(item.get("claim_id")))


def _normalize_review_claims(claims: list[ReviewClaimInput]) -> list[dict]:
    normalized_claims = []

    for index, claim in enumerate(claims, start=1):
        claim_text = (claim.claim or "").strip()
        if not claim_text:
            continue

        context = (claim.context or claim_text).strip() or claim_text
        normalized_claims.append(
            {
                "id": str(claim.id or index),
                "claim": claim_text,
                "context": context,
                "time_sensitive": bool(
                    claim.time_sensitive
                    if claim.time_sensitive is not None
                    else infer_time_sensitivity(claim_text)
                ),
                "claim_type": str(claim.claim_type or classify_claim_type(claim_text)),
            }
        )

    return normalized_claims


def _attach_url_context_to_claims(
    claims: list[dict],
    *,
    source_url: str,
    source_text: str,
    source_capture: dict | None = None,
) -> list[dict]:
    source_url = (source_url or "").strip()
    source_text = (source_text or "").strip()
    if not source_url or not source_text:
        return claims

    source_title = ""
    if isinstance(source_capture, dict):
        source_title = str(source_capture.get("title", "") or "").strip()

    enriched_claims = []
    for claim in claims:
        enriched_claims.append(
            {
                **claim,
                "source_url": source_url,
                "source_title": source_title,
                "source_text": source_text,
            }
        )
    return enriched_claims


def _serialize_report_for_viewer(report: dict, viewer_session_id: str) -> dict:
    payload = dict(report)
    payload["viewer_can_manage"] = bool(
        payload.get("owner_session_id")
        and payload.get("owner_session_id") == viewer_session_id
    )
    return payload


def _manual_review_claim_extraction(payload: dict | None, claim_count: int) -> dict:
    existing = dict(payload or {})
    warnings = [
        *[
            str(item).strip()
            for item in existing.get("warnings", [])
            if str(item).strip()
        ],
        "Claims were manually reviewed before verification.",
    ]

    return {
        "mode": "manual_review",
        "source_mode": existing.get("mode"),
        "provider": existing.get("provider"),
        "provider_label": existing.get("provider_label"),
        "model": existing.get("model"),
        "warnings": list(dict.fromkeys(warnings)),
        "error": existing.get("error"),
        "claim_count": claim_count,
    }


def _claim_extraction_requires_review(payload: dict | None) -> bool:
    return str((payload or {}).get("mode", "")).strip().lower() == "heuristic"


def _apply_payload_to_report(report: dict, payload: dict) -> dict:
    updated = dict(report)
    payload_type = payload.get("type")

    if payload_type == "scraping_done":
        updated["pipeline_stage"] = "detecting"
        updated["source_capture"] = payload.get("data", {}).get(
            "source_capture",
            updated.get("source_capture"),
        )
    elif payload_type == "source_text_ready":
        updated["source_text"] = payload.get("data", {}).get("source_text", "")
        updated["source_text_truncated"] = bool(
            payload.get("data", {}).get("source_text_truncated", False)
        )
    elif payload_type == "media_detection_start":
        updated["pipeline_stage"] = "media_detecting"
    elif payload_type == "media_detection_result":
        updated["media_detection"] = payload.get("data")
    elif payload_type == "ai_detection_start":
        updated["pipeline_stage"] = "detecting"
    elif payload_type == "ai_detection_result":
        updated["ai_detection"] = payload.get("data")
    elif payload_type == "extracting_start":
        updated["pipeline_stage"] = "extracting"
    elif payload_type == "extracting_done":
        updated["claims"] = payload.get("data", {}).get("claims", [])
        updated["claim_extraction"] = payload.get("data", {}).get(
            "claim_extraction",
            updated.get("claim_extraction"),
        )
    elif payload_type == "retrieving_start":
        updated["pipeline_stage"] = "retrieving"
        updated["progress"] = {"done": 0, "total": payload.get("data", {}).get("total", 0)}
    elif payload_type == "retrieving_progress":
        updated["pipeline_stage"] = "retrieving"
        updated["progress"] = {
            "done": payload.get("data", {}).get("done", 0),
            "total": payload.get("data", {}).get("total", 0),
        }
    elif payload_type == "verifying_start":
        updated["pipeline_stage"] = "verifying"
        updated["progress"] = {"done": 0, "total": payload.get("data", {}).get("total", 0)}
    elif payload_type == "verifying_progress":
        next_results = [
            *[item for item in updated.get("results", []) if item.get("claim_id") != payload.get("data", {}).get("claim_id")],
            payload.get("data", {}),
        ]
        updated["pipeline_stage"] = "verifying"
        updated["results"] = _sort_results(next_results)
        updated["progress"] = {
            "done": len(updated["results"]),
            "total": updated.get("progress", {}).get("total")
            or len(updated.get("claims", []))
            or len(updated["results"]),
        }
    elif payload_type == "verifying_status":
        updated["pipeline_stage"] = "verifying"
        updated["progress"] = {
            "done": payload.get("data", {}).get("done", 0),
            "total": payload.get("data", {}).get("total", 0),
        }
    elif payload_type == "done":
        updated["pipeline_stage"] = "done"
        updated["status"] = "done"
        updated["completed_at"] = payload.get("data", {}).get("completed_at") or _utc_now()
        updated["error"] = None
    elif payload_type == "error":
        updated["status"] = "error"
        updated["error"] = payload.get("message") or "The analysis failed."
        updated["completed_at"] = payload.get("data", {}).get("completed_at") or _utc_now()

    return updated


async def _run_with_limit(items: list[dict], worker, limit: int = 3):
    semaphore = asyncio.Semaphore(limit)

    async def _wrapped(item: dict):
        async with semaphore:
            return item, await worker(item)

    tasks = [asyncio.create_task(_wrapped(item)) for item in items]
    for task in asyncio.as_completed(tasks):
        yield await task


async def _verify_claim_with_context(claim: dict, evidence: dict, claims: list[dict]) -> dict:
    try:
        return await verify_claim(claim, evidence, session_claims=claims)
    except TypeError as exc:
        if "session_claims" not in str(exc):
            raise
        return await verify_claim(claim, evidence)


async def _stream_retrieval_and_verification(claims: list[dict], _emit):
    total_claims = len(claims)
    event_queue = asyncio.Queue()
    
    async def _push(payload: dict):
        await event_queue.put(_emit(payload))

    async def _process_single_claim(claim: dict):
        async def _on_query(data: dict):
            await _push({"type": "retrieving_query", "data": data})
        
        # Step 1: Retrieve evidence with live query updates
        evidence = await retrieve_evidence(claim, progress_callback=_on_query)
        
        # Step 2: Verify claim immediately with full claims list as context
        result = await _verify_claim_with_context(claim, evidence, claims)
        return result

    async def _producer():
        completed_verifications = 0
        try:
            async for _item, result in _run_with_limit(claims, _process_single_claim, limit=10):
                completed_verifications += 1
                await _push({"type": "verifying_progress", "data": result})
                await _push(
                    {
                        "type": "verifying_status",
                        "data": {
                            "done": completed_verifications,
                            "total": total_claims,
                        },
                    }
                )
        except Exception as exc:
            await _push({"type": "error", "message": f"Verification failed: {exc}"})
        finally:
            await event_queue.put(None) # Sentinel

    yield _emit({"type": "verifying_start", "data": {"total": total_claims}})
    
    producer_task = asyncio.create_task(_producer())
    
    while True:
        event = await event_queue.get()
        if event is None:
            break
        yield event
    
    await producer_task
    
    yield _emit({"type": "reflecting_start"})
    await asyncio.sleep(0.5) 


@app.middleware("http")
async def apply_request_security(request: Request, call_next):
    incoming_session_id = request.cookies.get(settings.session_cookie_name)
    session_id = incoming_session_id or create_session_id()
    request.state.session_id = session_id

    limit = get_rate_limit_for_request(request, settings)
    if limit is not None:
        identifier = get_client_identifier(request, session_id)
        decision = rate_limiter.check(
            f"{request.method}:{request.url.path}:{identifier}",
            limit=limit,
            window_seconds=settings.rate_limit_window_seconds,
        )
        if not decision.allowed:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )
            response.headers["Retry-After"] = str(decision.retry_after)
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
            if not incoming_session_id:
                response.set_cookie(
                    settings.session_cookie_name,
                    session_id,
                    httponly=True,
                    secure=settings.session_cookie_secure,
                    samesite="lax",
                    max_age=settings.session_cookie_max_age,
                )
            return response

    response = await call_next(request)

    if limit is not None:
        response.headers.setdefault("X-RateLimit-Limit", str(limit))

    if not incoming_session_id:
        response.set_cookie(
            settings.session_cookie_name,
            session_id,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            max_age=settings.session_cookie_max_age,
        )

    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/reports")
async def reports(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_archived: bool = Query(default=False),
) -> dict:
    payload = list_reports(
        owner_session_id=request.state.session_id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        allow_legacy_public_reports=settings.allow_legacy_public_reports,
    )
    payload["reports"] = [
        _serialize_report_for_viewer(report, request.state.session_id)
        for report in payload.get("reports", [])
    ]
    return payload


@app.get("/reports/{report_id}")
async def report_detail(
    report_id: str,
    request: Request,
    share: Optional[str] = Query(default=None),
) -> dict:
    report = get_report(
        report_id,
        owner_session_id=request.state.session_id,
        share_token=share if settings.public_share_enabled else None,
        allow_legacy_public_reports=settings.allow_legacy_public_reports,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return _serialize_report_for_viewer(report, request.state.session_id)


@app.patch("/reports/{report_id}")
async def update_report(
    report_id: str,
    request: Request,
    payload: ReportUpdateRequest,
) -> dict:
    report = update_report_metadata(
        report_id,
        owner_session_id=request.state.session_id,
        is_pinned=payload.is_pinned,
        is_archived=payload.is_archived,
        allow_legacy_public_reports=False,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return _serialize_report_for_viewer(report, request.state.session_id)


@app.post("/reports/{report_id}/claims/{claim_id}/recalculate")
async def recalculate_report_claim(
    report_id: str,
    claim_id: str,
    request: Request,
    payload: ClaimOverrideRequest,
) -> dict:
    report = get_report(
        report_id,
        owner_session_id=request.state.session_id,
        allow_legacy_public_reports=False,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    claim = next(
        (item for item in report.get("claims", []) if str(item.get("id", "")).strip() == str(claim_id).strip()),
        None,
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found.")

    current_result = next(
        (
            item
            for item in report.get("results", [])
            if str(item.get("claim_id", "")).strip() == str(claim_id).strip()
        ),
        None,
    )
    if current_result is None:
        raise HTTPException(status_code=404, detail="Verified result not found for this claim.")

    overrides: dict[str, str] = {}
    for item in payload.overrides:
        if item.source_id and item.source_id.strip():
            overrides[item.source_id.strip()] = item.stance
        if item.source_url and item.source_url.strip():
            overrides[item.source_url.strip()] = item.stance

    try:
        updated_result = recalculate_claim_result(claim, current_result, overrides=overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    report["results"] = _sort_results(
        [
            *[
                item
                for item in report.get("results", [])
                if str(item.get("claim_id", "")).strip() != str(claim_id).strip()
            ],
            updated_result,
        ]
    )
    report["status"] = "done"
    report["pipeline_stage"] = "done"
    report["error"] = None
    saved_report = save_report(report)
    return _serialize_report_for_viewer(saved_report, request.state.session_id)


@app.delete("/reports/{report_id}")
async def remove_report(report_id: str, request: Request) -> dict:
    deleted = delete_report(
        report_id,
        owner_session_id=request.state.session_id,
        allow_legacy_public_reports=False,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Report not found.")
    return {"deleted": True, "report_id": report_id}


@app.get("/reports/{report_id}/export")
async def export_report(
    report_id: str,
    request: Request,
    share: Optional[str] = Query(default=None),
) -> Response:
    report = get_report(
        report_id,
        owner_session_id=request.state.session_id,
        share_token=share if settings.public_share_enabled else None,
        allow_legacy_public_reports=settings.allow_legacy_public_reports,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    return Response(
        content=json.dumps(report, ensure_ascii=True, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{report_id}.json"',
        },
    )


@app.get("/reports/{report_id}/export/pdf")
async def export_report_pdf(
    report_id: str,
    request: Request,
    share: Optional[str] = Query(default=None),
) -> Response:
    report = get_report(
        report_id,
        owner_session_id=request.state.session_id,
        share_token=share if settings.public_share_enabled else None,
        allow_legacy_public_reports=settings.allow_legacy_public_reports,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    return Response(
        content=build_report_pdf(report),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{report_id}.pdf"',
        },
    )


@app.post("/draft-claims")
async def draft_claims(payload: AnalyzeRequest) -> dict:
    url_stripped = payload.url.strip() if payload.url else ""
    text_stripped = (payload.text or "").strip()
    
    is_youtube = bool(url_stripped and extract_video_id(url_stripped))
    input_mode = "youtube" if is_youtube else ("url" if url_stripped else "text")
    input_value = url_stripped if input_mode in ("url", "youtube") else text_stripped

    scrape_result = {}
    media_result = None

    if input_mode == "youtube":
        try:
            text = get_youtube_transcript(url_stripped)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif input_mode == "url":
        try:
            scrape_result = await scrape_url(url_stripped)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        text = scrape_result.get("text", "")
        media_urls = scrape_result.get("media", [])
        media_result = await detect_media(media_urls) if media_urls else None
    else:
        text = text_stripped

    ai_result = await detect_ai(text) if text else None
    extraction = await extract_claims_with_metadata(text)
    source_text_payload = _prepare_source_text_payload(text)

    return {
        "input_mode": input_mode,
        "input_value": input_value,
        "source_text": source_text_payload["source_text"],
        "source_text_truncated": source_text_payload["source_text_truncated"],
        "source_capture": scrape_result.get("source_capture") if input_mode == "url" else None,
        "claims": extraction["claims"],
        "claim_extraction": extraction["meta"],
        "review_required": _claim_extraction_requires_review(extraction["meta"]),
        "ai_detection": ai_result,
        "media_detection": media_result,
    }


@app.post("/analyze")
async def analyze(request: Request, payload: AnalyzeRequest) -> StreamingResponse:
    async def event_stream():
        url_stripped = payload.url.strip() if payload.url else ""
        text_stripped = (payload.text or "").strip()
        
        is_youtube = bool(url_stripped and extract_video_id(url_stripped))
        input_mode = "youtube" if is_youtube else ("url" if url_stripped else "text")
        input_value = url_stripped if input_mode in ("url", "youtube") else text_stripped
        
        report = None
        buffered_payloads: list[dict] = []
        scrape_result = {}
        media_urls = []
        media_result = None

        def _emit(payload: dict) -> str:
            nonlocal report
            if report is None:
                buffered_payloads.append(payload)
                return _sse(payload)
            report = _apply_payload_to_report(report, payload)
            report = save_report(report)
            return _sse(payload)

        def _start_report() -> dict:
            nonlocal report
            report = build_report_record(
                input_mode=input_mode,
                input_value=input_value,
                owner_session_id=request.state.session_id,
            )
            for buffered_payload in buffered_payloads:
                report = _apply_payload_to_report(report, buffered_payload)
            report = save_report(report)
            buffered_payloads.clear()
            return report

        try:
            if input_mode == "youtube":
                text = get_youtube_transcript(url_stripped)
                yield _emit({"type": "source_text_ready", "data": _prepare_source_text_payload(text)})
                yield _emit(
                    {
                        "type": "scraping_done",
                        "data": {
                            "chars": len(text),
                            "media_count": 0,
                            "source_capture": None,
                        },
                    }
                )
            elif input_mode == "url":
                scrape_result = await scrape_url(url_stripped)
                text = scrape_result["text"]
                media_urls = scrape_result.get("media", [])
                yield _emit({"type": "source_text_ready", "data": _prepare_source_text_payload(text)})
                yield _emit(
                    {
                        "type": "scraping_done",
                        "data": {
                            "chars": len(text),
                            "media_count": len(media_urls),
                            "source_capture": scrape_result.get("source_capture"),
                        },
                    }
                )
                
                if media_urls:
                    yield _emit({"type": "media_detection_start", "data": {"media_count": len(media_urls)}})
                    media_result = await detect_media(media_urls)
                    yield _emit({"type": "media_detection_result", "data": media_result})
            else:
                text = text_stripped
                yield _emit({"type": "source_text_ready", "data": _prepare_source_text_payload(text)})

            # RUN ENTIRE METADATA PIPELINE IN PARALLEL
            async def _run_metadata_and_extraction():
                # We need to extract claims, but also run detectors. 
                # We can run ai_detection and claim_extraction in parallel.
                # If it's a URL, we also run media_detection.
                tasks = [
                    extract_claims_with_metadata(text),
                    detect_ai(text)
                ]
                if input_mode == "url" and media_urls:
                    tasks.append(detect_media(media_urls))
                
                results = await asyncio.gather(*tasks)
                return results

            metadata_results = await _run_metadata_and_extraction()
            extraction = metadata_results[0]
            ai_result = metadata_results[1]
            media_result = metadata_results[2] if len(metadata_results) > 2 else None

            claims = extraction["claims"]
            if input_mode == "url":
                claims = _attach_url_context_to_claims(
                    claims,
                    source_url=url_stripped,
                    source_text=text,
                    source_capture=scrape_result.get("source_capture"),
                )

            # Emit all results at once
            yield _emit({"type": "ai_detection_result", "data": ai_result})
            if media_result:
                yield _emit({"type": "media_detection_result", "data": media_result})
            
            yield _emit(
                {
                    "type": "extracting_done",
                    "data": {
                        "claims": claims,
                        "count": len(claims),
                        "claim_extraction": extraction["meta"],
                    },
                }
            )

            if _claim_extraction_requires_review(extraction["meta"]):
                source_text_payload = _prepare_source_text_payload(text)
                yield _sse(
                    {
                        "type": "review_required",
                        "message": (
                            "Automatic verification paused because FactLens had to use a heuristic claim draft. "
                            "Review and confirm the claims before verification."
                        ),
                        "data": {
                            "input_mode": input_mode,
                            "input_value": input_value,
                            "source_text": source_text_payload["source_text"],
                            "source_text_truncated": source_text_payload["source_text_truncated"],
                            "source_capture": scrape_result.get("source_capture") if payload.url else None,
                            "claims": claims,
                            "claim_extraction": extraction["meta"],
                            "review_required": True,
                            "ai_detection": ai_result,
                            "media_detection": media_result if payload.url and media_urls else None,
                        },
                    }
                )
                return

            report = _start_report()
            yield _sse({"type": "report_created", "data": {"report_id": report["id"]}})

            if not claims and extraction["meta"].get("error"):
                raise ValueError(extraction["meta"]["error"])

            async for chunk in _stream_retrieval_and_verification(claims, _emit):
                yield chunk

            yield _emit(
                {
                    "type": "done",
                    "data": {"report_id": report["id"], "completed_at": _utc_now()},
                }
            )
        except Exception as exc:
            if report is None:
                yield _sse(
                    {
                        "type": "error",
                        "message": str(exc),
                        "data": {"completed_at": _utc_now()},
                    }
                )
                return
            yield _emit(
                {
                    "type": "error",
                    "message": str(exc),
                    "data": {"report_id": report["id"], "completed_at": _utc_now()},
                }
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/analyze-reviewed")
async def analyze_reviewed(
    request: Request,
    payload: AnalyzeReviewedRequest,
) -> StreamingResponse:
    normalized_claims = _normalize_review_claims(payload.claims)
    if payload.input_mode == "url":
        normalized_claims = _attach_url_context_to_claims(
            normalized_claims,
            source_url=(payload.input_value or "").strip(),
            source_text=payload.source_text,
            source_capture=payload.source_capture,
        )
    if not normalized_claims:
        raise HTTPException(status_code=422, detail="At least one reviewed claim is required.")

    async def event_stream():
        input_value = (payload.input_value or "").strip() or payload.source_text.strip()
        report = save_report(
            build_report_record(
                input_mode=payload.input_mode,
                input_value=input_value,
                owner_session_id=request.state.session_id,
            )
        )

        def _emit(payload: dict) -> str:
            nonlocal report
            report = _apply_payload_to_report(report, payload)
            report = save_report(report)
            return _sse(payload)

        try:
            yield _sse({"type": "report_created", "data": {"report_id": report["id"]}})
            yield _emit(
                {
                    "type": "source_text_ready",
                    "data": _prepare_source_text_payload(payload.source_text),
                }
            )
            if payload.input_mode == "url" and payload.source_capture is not None:
                yield _emit(
                    {
                        "type": "scraping_done",
                        "data": {
                            "chars": len(payload.source_text),
                            "media_count": int(payload.source_capture.get("media_count", 0) or 0),
                            "source_capture": payload.source_capture,
                        },
                    }
                )

            if payload.media_detection is not None:
                yield _emit({"type": "media_detection_result", "data": payload.media_detection})
            if payload.ai_detection is not None:
                yield _emit({"type": "ai_detection_result", "data": payload.ai_detection})

            yield _emit({"type": "extracting_start"})
            claim_extraction = _manual_review_claim_extraction(
                payload.claim_extraction,
                len(normalized_claims),
            )
            yield _emit(
                {
                    "type": "extracting_done",
                    "data": {
                        "claims": normalized_claims,
                        "count": len(normalized_claims),
                        "claim_extraction": claim_extraction,
                    },
                }
            )

            async for chunk in _stream_retrieval_and_verification(normalized_claims, _emit):
                yield chunk

            yield _emit(
                {
                    "type": "done",
                    "data": {"report_id": report["id"], "completed_at": _utc_now()},
                }
            )
        except Exception as exc:
            yield _emit(
                {
                    "type": "error",
                    "message": str(exc),
                    "data": {"report_id": report["id"], "completed_at": _utc_now()},
                }
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
