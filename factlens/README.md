# FactLens

FactLens is a fact and claim verification web app for text passages and article URLs. It extracts reviewable claims, retrieves live evidence, detects conflicting or stale sources, and produces a claim-by-claim accuracy report with citations, confidence scores, and risk flags.

Public repository: https://github.com/Anubhab-1/FactLens

## Core flow

1. Paste text or a news URL.
2. Either run the full pipeline directly or stop after extraction and review the claims first.
3. FactLens retrieves web evidence, repairs weak searches automatically, and verifies each claim.
4. The report shows verdicts, grounded evidence passages, conflict drivers, freshness warnings, and authenticity signals.

## What is in the app now

- Atomic claim extraction with fallback heuristics
- Editable claim-review step before verification
- Automatic verification now pauses when extraction falls back to heuristics, forcing explicit claim review
- Live web retrieval with automatic recovery queries on weak first-pass search
- Grounded evidence passage extraction from retrieved source content
- Verdict calibration across support, conflict, mixed, and low-signal evidence
- Conflict intelligence explaining why sources disagree
- Claim trace panel mapping claims back to analyzed source text
- AI-text signals and caveated media-authenticity risk review
- Saved reports, share links, JSON export, and PDF export
- Guided demo mode with curated hackathon scenario packs

## Architecture

### Frontend

- React + Vite
- Tailwind CSS
- Multi-page product flow: Home, Workspace, Demo, Report, History, Methodology

### Backend

- FastAPI
- SSE streaming for long-running analysis
- SQLAlchemy report persistence with SQLite by default and Postgres via `FACTLENS_DATABASE_URL`
- In-memory rate limiting and session-based report scoping

### Pipeline

- Extraction: LLM + heuristic fallback
- Search: Tavily with multi-query retrieval, LLM-guided recovery planning, and heuristic fallback
- Search fallback chain: Tavily, optional SerpApi, optional Google Custom Search, then DuckDuckGo/Bing HTML
- Verification: source triage + calibrated verdict scoring
- URL ingestion: Trafilatura with HTML fallback
- Media authenticity: specialized classifier if configured, otherwise a clearly labeled vision-LLM heuristic

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload
```

To use Postgres instead of the default local SQLite file, set:

```bash
FACTLENS_DATABASE_URL=postgresql://user:password@localhost:5432/factlens
```

### Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

## Test and build

### Backend tests

```bash
cd backend
pytest -q
```

### Frontend production build

```bash
cd frontend
npm run build
```

### Frontend tests

```bash
cd frontend
npm run test
```

### Frontend browser smoke tests

```bash
cd frontend
npm run test:e2e
```

## Environment variables

### Backend

- `NVIDIA_API_KEY`
- `GOOGLE_API_KEY`
- `OPENAI_API_KEY`
- `TAVILY_API_KEY`
- `SERPAPI_API_KEY`
- `GOOGLE_CSE_ID`
- `FACTLENS_DATABASE_URL`
- `FACTLENS_LLM_PROVIDER`
- `FACTLENS_MEDIA_DETECTOR_MODE`
- `FACTLENS_MEDIA_CLASSIFIER_URL`
- `FACTLENS_MEDIA_CLASSIFIER_API_KEY`
- `FACTLENS_MEDIA_CLASSIFIER_AUTH_HEADER`
- `FACTLENS_MEDIA_CLASSIFIER_TIMEOUT_SECONDS`
- `FACTLENS_PUBLIC_SHARE_ENABLED`
- `FACTLENS_LEGACY_PUBLIC_REPORTS`
- `FACTLENS_ALLOWED_ORIGINS`
- `FACTLENS_RATE_LIMIT_WINDOW_SECONDS`
- `FACTLENS_RATE_LIMIT_READ_REQUESTS`
- `FACTLENS_RATE_LIMIT_WRITE_REQUESTS`
- `FACTLENS_RATE_LIMIT_ANALYZE_REQUESTS`

### Specialized Media Classifier Setup (Optional for Bonus Points)

To enable the specialized media classifier for improved deepfake detection (earning the AI-Generated Media Detection bonus points):

1. Set `FACTLENS_MEDIA_DETECTOR_MODE=specialized` in your backend `.env` file
2. Configure your specialized classifier endpoint:
   - `FACTLENS_MEDIA_CLASSIFIER_URL` - URL of your deepfake classification service
   - `FACTLENS_MEDIA_CLASSIFIER_API_KEY` - API key for authentication (if required)
   - `FACTLENS_MEDIA_CLASSIFIER_AUTH_HEADER` - Header name for API key (default: "Authorization")
   - `FACTLENS_MEDIA_CLASSIFIER_TIMEOUT_SECONDS` - Request timeout (default: 20)

The classifier should accept POST requests with JSON body:
```json
{
  "image_url": "https://example.com/image.jpg",
  "media_url": "https://example.com/image.jpg"
}
```

And return JSON response:
```json
{
  "result": {
    "ai_probability": 0.85,
    "label": "LIKELY_SYNTHETIC",
    "signals_found": ["inconsistent_lighting", "blurred_artifacts"],
    "explanation": "Image shows signs of digital manipulation"
  }
}
```

Supported labels: `LIKELY_SYNTHETIC`, `POSSIBLY_SYNTHETIC`, `NO_STRONG_SIGNAL`, `UNKNOWN`

### Frontend

- `VITE_API_URL`

## Hackathon demo path

Use the built-in `Demo` page for a clean 10-minute walkthrough:

1. `Clean truth pack`: show a clean, high-confidence verification pass.
2. `Mixed verdict pack`: show `TRUE` and `FALSE` verdicts in the same run.
3. `Time-sensitive pack`: show freshness warnings, dated evidence, and recovery search.
4. `Live article URL`: show scraping, claim review, and real-world ambiguity.

For the strongest live URL demo, configure at least one search API beyond the HTML fallbacks:

- `SERPAPI_API_KEY`
- or `GOOGLE_API_KEY` + `GOOGLE_CSE_ID`

## Strong demo talking points

- FactLens does not force a one-shot LLM answer; it shows the intermediate claim draft and lets the user edit it.
- Weak retrieval does not silently fail; the search layer records when it had to repair the query strategy.
- If one provider returns junk search hits that fail grounding, FactLens now continues to the next provider instead of stopping at `result_count > 0`.
- Conflicting evidence is not flattened into a single badge; the report explains whether disagreement came from time drift, authority imbalance, numeric disagreement, or claim scope mismatch.
- The report stays anchored to source text through the claim trace and grounded evidence passages.

## Current notes

- Backend tests currently pass with `pytest -q`.
- Frontend unit tests currently pass with `npm run test -- --run`.
- Frontend browser smoke tests currently pass with `npm run test:e2e`.
- Frontend production build currently passes with `npm run build`.
- The NVIDIA vision endpoint emits a non-fatal warning during backend tests about model typing.
