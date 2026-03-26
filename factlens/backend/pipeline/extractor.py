from __future__ import annotations

import ast
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from llm_provider import create_chat_model
from pipeline.scoring import classify_claim_type, infer_time_sensitivity, tokenize

llm, llm_descriptor = create_chat_model("extractor", temperature=0.1, max_tokens=2048)

EXTRACTION_CHUNK_TRIGGER_CHARS = 5000
EXTRACTION_CHUNK_MAX_CHARS = 5000
EXTRACTION_CHUNK_MAX_SENTENCES = 30
EXTRACTION_MAX_CLAIMS = 60
EXTRACTION_MAX_CHUNKS = 20
EXTRACTION_DIRECT_MAX_CHARS = 6000

SYSTEM_PROMPT = """You are a highly granular, high-recall fact-checking assistant. Your job is to extract EVERY
verifiable, atomic factual claim from the provided text, with a special focus on:
- Historical figures, dates, and world-shaping events.
- Scientific discoveries, laws of nature, and technological breakthroughs.
- Celestial bodies (planets, stars, galaxies) and space mission details.
- Famous landmarks, artworks, and cultural achievements.

Rules you must follow:
1. Be COMPREHENSIVE: Do not skip details. Extract granular facts even if they seem minor.
2. Each claim must be a single, independently verifiable statement of fact.
3. Do NOT include opinions, predictions, or subjective statements.
4. Do NOT rephrase -- preserve the original specific names and data points exactly.
5. If a claim is time-sensitive (mentions current leaders, prices, rankings,
   recent events), add 'time_sensitive: true' in the object.
6. Return ONLY a valid JSON array. No explanation, no markdown, no preamble.

Output format:
[
  {
    'id': '1',
    'claim': 'The atomic verifiable statement',
    'context': 'The original sentence for reference',
    'time_sensitive': false
  }
]"""

REFINEMENT_PROMPT = """You are a meticulous fact-checking editor. Your task is to refine and
improve a list of extracted factual claims.

Rules:
1. Split any claim that contains multiple distinct facts into separate atomic claims.
2. Remove any claims that are subjective, opinions, or not verifiable facts.
3. Ensure each claim is clear, unambiguous, and can be verified independently of the original text.
4. Preserve all original context and time-sensitivity flags.
5. NEVER correct, replace, or "fix" a claim. If the original text states something false, keep the false claim exactly as stated.
6. Only keep wording that is directly grounded in the original extracted claims and their contexts.
7. Remove any redundant or near-duplicate claims.
8. Return ONLY a valid JSON array. No explanation.

Output format:
[
  {
    'id': '1',
    'claim': 'Refined atomic claim',
    'context': 'Original context',
    'time_sensitive': boolean,
    'claim_type': 'string'
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
CLAIM_GROUNDING_MIN_OVERLAP = 0.6


def _non_empty_lines(text: str) -> list[str]:
    return [line.strip(" -•\t") for line in (text or "").splitlines() if line.strip()]


def _normalize_text(text: str) -> str:
    # Strip Wikipedia-style citations and notes:
    # 1. Numeric citations: [1], [12][34]
    # 2. Alphabetic footnotes: [a], [b]
    # 3. Special tags: [update], [citation needed]
    # We replace with a space to ensure we don't accidentally merge two sentences
    # if a citation was between them without a space (e.g., "End.[1]Next").
    text = re.sub(r"\[(?:\d+|[a-z]|update|citation\s+needed)\]", " ", text or "", flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text.strip())


def _looks_like_outline(text: str) -> bool:
    lines = _non_empty_lines(text)
    if len(lines) < 8:  # Increase minimum lines to avoid false positives for short lists
        return False

    short_line_ratio = sum(1 for line in lines if len(line) <= 60) / len(lines)
    no_punctuation_ratio = sum(1 for line in lines if not re.search(r"[.!?]$", line)) / len(lines)
    
    # Relaxed thresholds to allow structured scientific/historical lists
    # Only reject if almost everything is a short fragment without punctuation AND no verbs
    if short_line_ratio > 0.9 and no_punctuation_ratio > 0.9:
        return True
    return False


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


def _claim_fingerprint(value: str) -> str:
    normalized = _normalize_text(value)
    normalized = re.sub(r"[^\w\s%.-]", "", normalized.lower())
    return normalized.strip()


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


def _dedupe_claims(claims: list[dict], *, max_claims: int = EXTRACTION_MAX_CLAIMS) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()

    for claim in claims:
        claim_text = str(claim.get("claim", "")).strip()
        fingerprint = _claim_fingerprint(claim_text)
        if not claim_text or not fingerprint or fingerprint in seen:
            continue

        seen.add(fingerprint)
        deduped.append(
            {
                **claim,
                "id": str(len(deduped) + 1),
            }
        )
        if len(deduped) >= max_claims:
            break

    return deduped


def _split_candidate_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return []

    parts = [
        sentence.strip(" -•\t")
        for sentence in re.split(r"(?<=[.!?])\s+|(?<=[.!?])(?=\[)|(?<=\])\s+|\n+", normalized)
        if sentence.strip()
    ]

    candidates = []
    seen = set()
    for part in parts:
        if len(part) < 10 or len(part) > 500:
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

    if not fallback_claims:
        normalized = _normalize_text(text)
        if 8 <= len(normalized) <= 240 and _looks_verifiable(normalized):
            fallback_claims.append(
                {
                    "id": "1",
                    "claim": normalized,
                    "context": normalized,
                    "time_sensitive": infer_time_sensitivity(normalized),
                    "claim_type": classify_claim_type(normalized),
                }
            )

    return fallback_claims


def _claim_overlap_ratio(claim_text: str, source_text: str) -> float:
    claim_tokens = set(tokenize(claim_text))
    source_tokens = set(tokenize(source_text))
    if not claim_tokens or not source_tokens:
        return 0.0
    return len(claim_tokens & source_tokens) / len(claim_tokens)


def _claim_is_grounded(claim: dict, source_text: str) -> bool:
    claim_text = str(claim.get("claim", "")).strip()
    context = str(claim.get("context", claim_text)).strip()
    if not claim_text:
        return False

    claim_fp = _claim_fingerprint(claim_text)
    combined_source = f"{source_text} {context}".strip()
    combined_fp = _claim_fingerprint(combined_source)
    if claim_fp and combined_fp and claim_fp in combined_fp:
        return True

    overlap = _claim_overlap_ratio(claim_text, combined_source)
    if overlap < CLAIM_GROUNDING_MIN_OVERLAP:
        return False

    claim_numbers = set(re.findall(r"\d+(?:\.\d+)?", claim_text))
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?", combined_source))
    if claim_numbers and not claim_numbers.issubset(source_numbers):
        return False

    return True


def _filter_grounded_claims(claims: list[dict], source_text: str) -> tuple[list[dict], int]:
    grounded = []
    dropped_count = 0

    for claim in claims:
        if _claim_is_grounded(claim, source_text):
            grounded.append(claim)
        else:
            dropped_count += 1

    return grounded, dropped_count


def _chunk_text_for_extraction(
    text: str,
    *,
    max_chars: int = EXTRACTION_CHUNK_MAX_CHARS,
    max_sentences: int = EXTRACTION_CHUNK_MAX_SENTENCES,
) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip()
    ]
    if not sentences:
        return [normalized[:max_chars].strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for sentence in sentences:
        candidate_length = current_length + len(sentence) + (1 if current else 0)
        if current and (candidate_length > max_chars or len(current) >= max_sentences):
            chunks.append(" ".join(current).strip())
            current = current[-1:]
            current_length = len(current[0]) if current else 0

        if len(sentence) > max_chars:
            for index in range(0, len(sentence), max_chars):
                fragment = sentence[index : index + max_chars].strip()
                if not fragment:
                    continue
                if current:
                    chunks.append(" ".join(current).strip())
                    current = []
                    current_length = 0
                chunks.append(fragment)
            continue

        current.append(sentence)
        current_length = sum(len(item) for item in current) + max(len(current) - 1, 0)

    if current:
        chunks.append(" ".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def _direct_extraction_text(text: str, *, max_chars: int = EXTRACTION_DIRECT_MAX_CHARS) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rsplit(" ", 1)[0].strip()


async def _invoke_extractor(user_message: str) -> str:
    if llm is None:
        raise RuntimeError(llm_descriptor.issue or "No claim-extraction model is configured.")

    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]
    )
    return response.content if isinstance(response.content, str) else str(response.content)


async def _extract_llm_claims(user_message: str) -> list[dict]:
    try:
        initial_response = await _invoke_extractor(user_message)
        return _normalize_claims(_parse_json_array(initial_response))
    except (json.JSONDecodeError, ValueError):
        retry_response = await _invoke_extractor(
            f"{user_message}\n\nReturn only valid JSON, no markdown code blocks."
        )
        return _normalize_claims(_parse_json_array(retry_response))

async def _refine_extracted_claims(claims: list[dict]) -> list[dict]:
    if not claims:
        return []

    claims_json = json.dumps(claims, indent=2)
    user_message = f"Refine these extracted claims for atomicity and verifiability:\n\n{claims_json}"

    try:
        if llm is None:
            return claims

        response = await llm.ainvoke(
            [
                SystemMessage(content=REFINEMENT_PROMPT),
                HumanMessage(content=user_message),
            ]
        )
        raw_content = response.content if isinstance(response.content, str) else str(response.content)
        refined = _parse_json_array(raw_content)
        return _normalize_claims(refined)
    except Exception:
        # Fallback to original claims if refinement fails
        return claims


async def _extract_chunked_claims(text: str) -> tuple[list[dict], list[str]]:
    all_chunks = _chunk_text_for_extraction(text)
    chunks = all_chunks[:EXTRACTION_MAX_CHUNKS]
    if len(chunks) <= 1:
        return [], []

    collected: list[dict] = []
    warnings: list[str] = []

    async def _extract_single_chunk(index: int, chunk: str) -> list[dict]:
        try:
            return await _extract_llm_claims(
                (
                    "Extract all verifiable claims from this text chunk. "
                    "Only include claims fully stated in this chunk.\n\n"
                    f"Chunk {index} of {len(chunks)}:\n{chunk}"
                )
            )
        except Exception as exc:
            warnings.append(f"Chunk {index} extraction failed: {exc}")
            return []

    # Parallelize extraction across all chunks
    results = await asyncio.gather(*[_extract_single_chunk(i+1, c) for i, c in enumerate(chunks)])
    for chunk_claims in results:
        collected.extend(chunk_claims)

    deduped = _dedupe_claims(collected)
    if deduped:
        warnings.insert(
            0,
            f"Long input was extracted in {len(chunks)} chunks for better claim coverage.",
        )
    if len(all_chunks) > len(chunks):
        warnings.append(
            f"Only the first {len(chunks)} extraction chunks were processed to keep long-article drafting responsive."
        )

    return deduped, list(dict.fromkeys(warnings))


def _build_extraction_meta(
    *,
    mode: str,
    claims: list[dict],
    warnings: list[str] | None = None,
    error: str | None = None,
    source_mode: str | None = None,
) -> dict:
    return {
        "mode": mode,
        "source_mode": source_mode,
        "provider": llm_descriptor.provider,
        "provider_label": llm_descriptor.provider_label,
        "model": llm_descriptor.model,
        "warnings": list(dict.fromkeys(warnings or [])),
        "error": error,
        "claim_count": len(claims),
    }


async def extract_claims_with_metadata(text: str) -> dict:
    raw_text = text or ""
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return {
            "claims": [],
            "meta": _build_extraction_meta(
                mode="failed",
                claims=[],
                error="No input text was provided for claim extraction.",
            ),
        }

    if _looks_like_outline(raw_text):
        return {
            "claims": [],
            "meta": _build_extraction_meta(
                mode="outline_blocked",
                claims=[],
                warnings=[
                    "The input looked like an outline or table of contents, so no automatic claims were drafted."
                ],
            ),
        }

    if llm is None:
        if llm_descriptor.status == "unconfigured":
            claims = _heuristic_extract_claims(normalized_text)
            return {
                "claims": claims,
                "meta": _build_extraction_meta(
                    mode="heuristic",
                    claims=claims,
                    warnings=[
                        "No LLM provider is configured, so FactLens used a heuristic claim draft. Review these claims carefully before verification."
                    ],
                ),
            }

        return {
            "claims": [],
            "meta": _build_extraction_meta(
                mode="failed",
                claims=[],
                error=llm_descriptor.issue or "Claim extraction is not configured correctly.",
            ),
        }

    try:
        warnings: list[str] = []
        normalized: list[dict] = []

        if len(normalized_text) > EXTRACTION_CHUNK_TRIGGER_CHARS:
            normalized, warnings = await _extract_chunked_claims(normalized_text)

        if not normalized:
            direct_text = _direct_extraction_text(normalized_text)
            if direct_text != normalized_text:
                warnings.append(
                    "FactLens retried claim extraction on a shortened lead section to keep long-input drafting fast."
                )
            normalized = await _extract_llm_claims(
                f"Extract all verifiable claims from this text:\n\n{direct_text}"
            )

        # NEW: Iterative Refinement for high accuracy
        if normalized:
            refined = await _refine_extracted_claims(normalized)
            if refined:
                normalized = refined
                warnings.append("Claims were refined for atomicity and verifiability.")

        if normalized:
            normalized, dropped_ungrounded = _filter_grounded_claims(normalized, normalized_text)
            if dropped_ungrounded:
                warnings.append(
                    f"Dropped {dropped_ungrounded} extracted claim"
                    f"{'' if dropped_ungrounded == 1 else 's'} that were not grounded in the source text."
                )

        normalized = _dedupe_claims(normalized)
        if not normalized:
            heuristic_claims = _heuristic_extract_claims(normalized_text)
            warnings.append("The claim-extraction model returned no verifiable claims.")
            if heuristic_claims:
                warnings.append(
                    "FactLens fell back to a heuristic claim draft. Review these claims carefully before verification."
                )
                return {
                    "claims": heuristic_claims,
                    "meta": _build_extraction_meta(
                        mode="heuristic",
                        source_mode="llm",
                        claims=heuristic_claims,
                        warnings=warnings,
                    ),
                }

        return {
            "claims": normalized,
            "meta": _build_extraction_meta(
                mode="llm",
                claims=normalized,
                warnings=list(dict.fromkeys(warnings)),
            ),
        }
    except Exception as exc:
        heuristic_claims = _heuristic_extract_claims(normalized_text)
        if heuristic_claims:
            return {
                "claims": heuristic_claims,
                "meta": _build_extraction_meta(
                    mode="heuristic",
                    source_mode="llm",
                    claims=heuristic_claims,
                    warnings=[
                        (
                            "The claim-extraction model returned unusable output, so FactLens fell back to a "
                            "heuristic claim draft. Review these claims carefully before verification."
                        )
                    ],
                    error=str(exc),
                ),
            }

        return {
            "claims": [],
            "meta": _build_extraction_meta(
                mode="failed",
                claims=[],
                error=(
                    "Claim extraction failed before a trustworthy draft could be produced. "
                    f"{exc}"
                ),
            ),
        }


async def extract_claims(text: str) -> list[dict]:
    return (await extract_claims_with_metadata(text))["claims"]
