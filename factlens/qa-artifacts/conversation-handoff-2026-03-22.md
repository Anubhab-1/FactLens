# FactLens Conversation Handoff

Date: 2026-03-22

## Current status

The project has been upgraded beyond the original hackathon prototype in several important areas. The local app is running at:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`

Latest backend health check:

- `GET /health` -> `{"status":"ok"}`

## Continuation update

Work continued after this handoff and split into two threads:

1. Local session/origin regression fix
- The frontend default API origin no longer hardwires `http://localhost:8000`.
- It now derives the backend host from the current browser hostname, which fixes the real-browser `127.0.0.1` -> `localhost` session/cookie mismatch.
- Result: the Selenium browser QA pass now completes without the earlier report-export 404 and mixed-origin issues.

2. Live validation findings
- Added a reusable live API validator at `qa-artifacts/scripts/live_api_validation.py`.
- Added backend coverage so string-based Tavily failures are surfaced instead of being silently treated as empty search results.
- Added fallback risk-flag coverage so no-evidence reports now expose the upstream retrieval warning.
- Confirmed directly against Tavily that the new key is being accepted but the account is over its current plan usage limit.
- Exact provider response observed during this session: plan-limit rejection with Tavily `Error 432`, not an invalid credential.
- Added no-key retrieval fallback search paths in `backend/pipeline/retriever.py`:
  - DuckDuckGo HTML search
  - Bing HTML search
- Added date-parse hardening in `backend/pipeline/scoring.py` so malformed fallback page metadata cannot crash recency handling.
- On fresh backend runs against `http://127.0.0.1:8011`, the new fallback path restored live evidence retrieval enough to exercise export/share and manual override again.
- Full live validation remains non-deterministic because the fallback chain depends on public search HTML and public page fetches, which are slow and can be rate-limited or blocked between runs.
- The main backend on `http://127.0.0.1:8000` was restarted at the end of the session so it is now serving the updated code.

## Major upgrades completed

1. LLM provider abstraction
- Added provider switching support instead of hardwiring NVIDIA everywhere.
- Gemini/OpenAI/NVIDIA selection is now driven by environment configuration.

2. Claim extraction trust improvements
- Claim extraction now exposes provenance metadata.
- Heuristic extraction is explicitly labeled.
- Automatic verification pauses when extraction falls back to heuristics and forces review first.

3. URL ingestion improvements
- Added browser-rendered fallback support for harder pages.
- Source-capture metadata is surfaced to the frontend.

4. Human-in-the-loop verdict correction
- Added source stance override and verdict recalculation.
- Manual review state is visible and reversible on the report page.

5. Media-authenticity hardening
- The media path no longer overclaims forensic deepfake detection.
- It now distinguishes specialized classifier mode from heuristic vision-LLM review.

6. Text-authenticity stability improvements
- Added retry handling for malformed model output.
- Added normalized output metadata and better fallback behavior.

7. Frontend session-state fix
- Fixed the bug that turned persisted running sessions into fake interruption errors.
- Stale interrupted local sessions are now cleaned up on reload.

8. Storage hardening
- Replaced hardwired SQLite persistence with SQLAlchemy-backed storage.
- SQLite remains the default local backend.
- Postgres is supported through `FACTLENS_DATABASE_URL`.

9. Browser QA automation
- Added Playwright smoke coverage for:
  - workspace claim drafting
  - report manual override recalculation
  - history actions and mobile layout sanity

10. Retrieval orchestration upgrade
- Added an LLM-guided recovery planner for weak retrieval cases.
- Preserved heuristic fallback for sparse or failed recovery scenarios.
- Recovery strategy is surfaced in the evidence rail UI.

## Verification snapshot

Latest successful checks:

- Backend: `pytest -q` -> `51 passed, 1 warning`
- Frontend unit tests: `npm run test` -> `11 passed`
- Frontend browser smoke tests: `npm run test:e2e` -> `3 passed`
- Frontend build: `npm run build` -> passed

Continuation checks:

- Frontend unit tests after origin fix: `npm run test` -> `14 passed`
- Frontend build after origin fix: `npm run build` -> passed
- Frontend Playwright smoke after origin fix: `npm run test:e2e` -> `3 passed`
- Backend targeted regression tests: `pytest -q backend/tests/test_retriever.py backend/tests/test_scoring.py backend/tests/test_scraper.py` -> `30 passed`
- Selenium live browser QA: `python qa-artifacts/run_qa.py` -> passed
- Fresh-backend live validation: `python qa-artifacts/scripts/live_api_validation.py` against `http://127.0.0.1:8011` -> reached source-backed flows again after fallback retrieval was added, but results remained variable across runs
- Main backend restart: `http://127.0.0.1:8000` was restarted after the fallback retrieval changes
- Full validator rerun on `http://127.0.0.1:8000` was intentionally not carried to completion because it was taking too long and the public-search fallback path is not stable enough to justify repeated long runs

## Current important files touched

Backend:

- `backend/llm_provider.py`
- `backend/main.py`
- `backend/pipeline/ai_detector.py`
- `backend/pipeline/extractor.py`
- `backend/pipeline/media_detector.py`
- `backend/pipeline/retriever.py`
- `backend/pipeline/scoring.py`
- `backend/pipeline/scraper.py`
- `backend/pipeline/verifier.py`
- `backend/storage/reports.py`
- `backend/.env.example`
- `backend/requirements.txt`

Frontend:

- `frontend/src/App.jsx`
- `frontend/src/lib/api.js`
- `frontend/src/lib/api.test.js`
- `frontend/src/lib/sessions.js`
- `frontend/src/components/AuthenticitySignalsPanel.jsx`
- `frontend/src/components/ClaimReviewPanel.jsx`
- `frontend/src/components/SourceReviewPanel.jsx`
- `frontend/src/components/SourceTimeline.jsx`
- `frontend/src/pages/WorkspacePage.jsx`
- `frontend/src/pages/ReportPage.jsx`
- `frontend/playwright.config.js`
- `frontend/e2e/app-smoke.spec.js`

Tests:

- `backend/tests/test_ai_detector.py`
- `backend/tests/test_media_detector.py`
- `backend/tests/test_retriever.py`
- `backend/tests/test_scraper.py`
- `backend/tests/test_scoring.py`
- `backend/tests/test_reports_storage.py`
- `frontend/src/components/AuthenticitySignalsPanel.test.jsx`
- `frontend/src/components/ClaimReviewPanel.test.jsx`
- `frontend/src/components/SourceTimeline.test.jsx`
- `frontend/src/lib/sessions.test.js`
- `qa-artifacts/scripts/live_api_validation.py`
- `qa-artifacts/results/live-api-validation.json`

## Remaining high-value next step

The next meaningful step, if work resumes, is to stabilize live retrieval rather than add more product features:

- keep Tavily as an optional provider, but do not rely on it for local QA because the current account is over plan limit
- make the public-search fallback less brittle, or replace it with a more stable retrieval source
- improve the live validator so it uses faster, narrower scenarios instead of one long, variable end-to-end pass
- revisit live URL claim drafting separately, because URL scraping still succeeds more often than URL claim extraction does

## Important caveats

- Postgres support is implemented and verified through the database-URL path plus automated tests, but no live Postgres server was configured during this session.
- The UI/browser QA can currently pass even when retrieval quality is weak, because it validates flow completion and exports more than source-backed verdict quality.
- The new no-key retrieval fallback is pragmatic, not robust: it depends on public search HTML and can be throttled, blocked, or change structure without notice.
