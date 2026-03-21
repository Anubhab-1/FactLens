from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, model_validator

load_dotenv(Path(__file__).resolve().parent / ".env")

from pipeline.ai_detector import detect_ai
from pipeline.extractor import extract_claims
from pipeline.media_detector import detect_media
from pipeline.retriever import retrieve_evidence
from pipeline.scraper import scrape_url
from pipeline.verifier import verify_claim
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
            raise ValueError("At least one of text or url is provided.")
        return self


class ReportUpdateRequest(BaseModel):
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sort_results(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda item: int(item.get("claim_id", 0)))


def _serialize_report_for_viewer(report: dict, viewer_session_id: str) -> dict:
    payload = dict(report)
    payload["viewer_can_manage"] = bool(
        payload.get("owner_session_id")
        and payload.get("owner_session_id") == viewer_session_id
    )
    return payload


def _apply_payload_to_report(report: dict, payload: dict) -> dict:
    updated = dict(report)
    payload_type = payload.get("type")

    if payload_type == "scraping_done":
        updated["pipeline_stage"] = "detecting"
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


@app.post("/analyze")
async def analyze(request: Request, payload: AnalyzeRequest) -> StreamingResponse:
    async def event_stream():
        input_mode = "url" if payload.url and payload.url.strip() else "text"
        input_value = payload.url.strip() if input_mode == "url" else (payload.text or "").strip()
        report = save_report(
            build_report_record(
                input_mode=input_mode,
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

            if payload.url:
                scrape_result = await scrape_url(payload.url.strip())
                text = scrape_result["text"]
                media_urls = scrape_result.get("media", [])
                yield _emit({"type": "scraping_done", "data": {"chars": len(text), "media_count": len(media_urls)}})
                
                if media_urls:
                    yield _emit({"type": "media_detection_start", "data": {"media_count": len(media_urls)}})
                    media_result = await detect_media(media_urls)
                    yield _emit({"type": "media_detection_result", "data": media_result})
            else:
                text = (payload.text or "").strip()

            yield _emit({"type": "ai_detection_start"})
            ai_result = await detect_ai(text)
            yield _emit({"type": "ai_detection_result", "data": ai_result})

            yield _emit({"type": "extracting_start"})
            claims = await extract_claims(text)
            yield _emit(
                {
                    "type": "extracting_done",
                    "data": {"claims": claims, "count": len(claims)},
                }
            )

            yield _emit({"type": "retrieving_start", "data": {"total": len(claims)}})
            evidence_map: dict[str, dict] = {}
            completed_retrievals = 0
            async for claim, evidence in _run_with_limit(claims, retrieve_evidence):
                evidence_map[claim["id"]] = evidence
                completed_retrievals += 1
                yield _emit(
                    {
                        "type": "retrieving_progress",
                        "data": {
                            "claim_id": claim["id"],
                            "done": completed_retrievals,
                            "total": len(claims),
                        },
                    }
                )

            yield _emit({"type": "verifying_start", "data": {"total": len(claims)}})
            completed_verifications = 0

            async def _verify_with_evidence(claim: dict) -> dict:
                return await verify_claim(claim, evidence_map[claim["id"]])

            async for _claim, result in _run_with_limit(claims, _verify_with_evidence):
                completed_verifications += 1
                yield _emit({"type": "verifying_progress", "data": result})
                yield _emit(
                    {
                        "type": "verifying_status",
                        "data": {
                            "done": completed_verifications,
                            "total": len(claims),
                        },
                    }
                )

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
