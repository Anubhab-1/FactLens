# FactLens

FactLens is a fact and claim verification prototype that turns raw text or article URLs into an evidence-backed accuracy report.

## What It Does

- Extracts atomic, verifiable claims from pasted text or scraped article content
- Generates multiple search strategies for each claim
- Retrieves live web evidence and ranks sources by authority, relevance, freshness, and diversity
- Verifies each claim as `TRUE`, `FALSE`, `PARTIALLY_TRUE`, or `UNVERIFIABLE`
- Streams progress to the UI while building a detailed claim-by-claim report
- Includes an experimental AI-text detection badge

## Stack

- Frontend: React + Vite + Tailwind CSS
- Backend: FastAPI
- Models: NVIDIA hosted LLM endpoints
- Search: Tavily
- Article extraction: Trafilatura with HTML fallback

## Run Locally

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

## Environment Variables

### Backend

- `NVIDIA_API_KEY`
- `TAVILY_API_KEY`

### Frontend

- `VITE_API_URL`

## Suggested Demo Scenarios

- A clearly true factual paragraph
- A partially true or historically disputed claim
- A time-sensitive claim where freshness and dating matter
- A URL from a news article with multiple extractable claims

## Quality Improvements Included

- Cleaner article extraction for URL inputs
- Fallback claim extraction when the LLM is unavailable or malformed
- Stricter handling of time-sensitive and conflicting evidence
- Source diversity controls in retrieval
- Original-context display in the report
- More honest top-line report metrics and stronger temporal warnings

