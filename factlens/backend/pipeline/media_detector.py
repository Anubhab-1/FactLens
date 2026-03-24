from __future__ import annotations

import ast
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from langchain_core.messages import HumanMessage, SystemMessage

from llm_provider import create_chat_model

llm, llm_descriptor = create_chat_model(
    "media_detector",
    temperature=0.1,
    max_tokens=1024,
    vision=True,
)

SYSTEM_PROMPT = """You are reviewing whether an image shows heuristic signals that sometimes appear in synthetic or manipulated media.
This is NOT a forensic conclusion. You must speak cautiously and only report visible cues.

Look for signals such as:
- inconsistent reflections, shadows, or lighting
- garbled text or signage
- anatomy or geometry errors
- oversmoothed textures or plastic-looking skin
- edge blending around hair, glasses, or object borders
- suspiciously inconsistent depth of field

Return ONLY valid JSON:
{
  "ai_probability": 0.0,
  "label": "LIKELY_SYNTHETIC" | "POSSIBLY_SYNTHETIC" | "NO_STRONG_SIGNAL" | "UNKNOWN",
  "signals_found": ["signal1", "signal2"],
  "explanation": "One sentence summary"
}

Scoring guide:
0.0 - 0.35 -> NO_STRONG_SIGNAL
0.35 - 0.65 -> POSSIBLY_SYNTHETIC
0.65 - 1.0 -> LIKELY_SYNTHETIC"""

VISION_HEURISTIC_LIMITATIONS = [
    "This result comes from a general vision LLM, not a forensic deepfake classifier.",
    "Modern AI-generated images can evade prompt-based inspection, while real images can trigger false positives.",
    "For production use, consider integrating specialized deepfake detection models like Microsoft Video Authenticator, Intel's FakeCatcher, or Sensity AI."
]
SPECIALIZED_LIMITATIONS = [
    "Classifier outputs should still be treated as risk signals until a human reviewer confirms the result.",
    "Specialized models may have biases based on their training data and may not generalize to all types of deepfakes."
]


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
            raise ValueError("Could not parse media detector response.") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed


def _get_mode() -> str:
    mode = os.getenv("FACTLENS_MEDIA_DETECTOR_MODE", "auto").strip().lower()
    return mode if mode in {"auto", "specialized", "vision_llm", "disabled"} else "auto"


def _get_classifier_url() -> str:
    return os.getenv("FACTLENS_MEDIA_CLASSIFIER_URL", "").strip()


def _get_classifier_api_key() -> str:
    return os.getenv("FACTLENS_MEDIA_CLASSIFIER_API_KEY", "").strip()


def _get_classifier_auth_header() -> str:
    return os.getenv("FACTLENS_MEDIA_CLASSIFIER_AUTH_HEADER", "Authorization").strip() or "Authorization"


def _get_classifier_timeout() -> float:
    raw_value = os.getenv("FACTLENS_MEDIA_CLASSIFIER_TIMEOUT_SECONDS", "20")
    try:
        timeout = float(raw_value)
    except ValueError:
        timeout = 20.0
    return max(timeout, 1.0)


def _normalize_label(value: object) -> str:
    normalized = str(value or "UNKNOWN").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "LIKELY_AI": "LIKELY_SYNTHETIC",
        "POSSIBLY_AI": "POSSIBLY_SYNTHETIC",
        "LIKELY_HUMAN": "NO_STRONG_SIGNAL",
        "LIKELY_REAL": "NO_STRONG_SIGNAL",
        "LIKELY_AUTHENTIC": "NO_STRONG_SIGNAL",
        "HUMAN": "NO_STRONG_SIGNAL",
        "AUTHENTIC": "NO_STRONG_SIGNAL",
    }
    normalized = aliases.get(normalized, normalized)
    return (
        normalized
        if normalized in {"LIKELY_SYNTHETIC", "POSSIBLY_SYNTHETIC", "NO_STRONG_SIGNAL", "UNKNOWN"}
        else "UNKNOWN"
    )


def _coerce_probability(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(numeric, 1.0))


def _base_result(media_url: str | None) -> dict:
    return {
        "ai_probability": None,
        "label": "UNKNOWN",
        "signals_found": [],
        "explanation": "",
        "media_url": media_url,
        "analysis_mode": "unavailable",
        "provider": None,
        "provider_label": None,
        "model": None,
        "review_recommended": True,
        "warnings": [],
        "limitations": [],
    }


def _build_result(
    payload: dict | None,
    *,
    media_url: str | None,
    analysis_mode: str,
    provider: str | None,
    provider_label: str | None,
    model: str | None,
    warnings: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict:
    result = _base_result(media_url)
    payload = payload or {}

    explanation = str(
        payload.get("explanation")
        or payload.get("summary")
        or payload.get("message")
        or ""
    ).strip()
    signals_found = [
        str(item).strip()
        for item in payload.get("signals_found", []) or []
        if str(item).strip()
    ]
    label = _normalize_label(payload.get("label"))
    probability = _coerce_probability(payload.get("ai_probability"))

    result.update(
        {
            "ai_probability": probability,
            "label": label,
            "signals_found": signals_found,
            "explanation": explanation,
            "analysis_mode": analysis_mode,
            "provider": provider,
            "provider_label": provider_label,
            "model": model,
            "warnings": list(dict.fromkeys([*(warnings or [])])),
            "limitations": list(dict.fromkeys([*(limitations or [])])),
        }
    )
    result["review_recommended"] = (
        analysis_mode != "specialized_classifier"
        or label in {"LIKELY_SYNTHETIC", "POSSIBLY_SYNTHETIC", "UNKNOWN"}
        or bool(result["warnings"])
    )
    return result


def _specialized_result(target_url: str) -> dict:
    classifier_url = _get_classifier_url()
    if not classifier_url:
        raise RuntimeError("No specialized media classifier endpoint is configured.")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    api_key = _get_classifier_api_key()
    if api_key:
        headers[_get_classifier_auth_header()] = api_key

    request = Request(
        classifier_url,
        data=json.dumps({"image_url": target_url, "media_url": target_url}).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=_get_classifier_timeout()) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"Specialized classifier returned HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"Specialized classifier request failed: {exc.reason}") from exc

    parsed = _parse_json_object(raw_body)
    nested = parsed.get("result") or parsed.get("data")
    if isinstance(nested, dict):
        parsed = nested

    model = urlparse(classifier_url).netloc or classifier_url
    return _build_result(
        parsed,
        media_url=target_url,
        analysis_mode="specialized_classifier",
        provider="custom_endpoint",
        provider_label="Specialized classifier",
        model=model,
        limitations=SPECIALIZED_LIMITATIONS,
    )


async def _vision_heuristic_result(target_url: str, warnings: list[str] | None = None) -> dict:
     if llm is None:
         raise RuntimeError(llm_descriptor.issue or "No media-authenticity model is configured.")

     # Enhanced prompt with self-consistency approach - run multiple times and aggregate
     enhanced_prompt = """You are reviewing whether an image shows heuristic signals that sometimes appear in synthetic or manipulated media.
 This is NOT a forensic conclusion. You must speak cautiously and only report visible cues.

 Look for signals such as:
 - inconsistent reflections, shadows, or lighting
 - garbled text or signage
 - anatomy or geometry errors
 - oversmoothed textures or plastic-looking skin
 - edge blending around hair, glasses, or object borders
 - suspiciously inconsistent depth of field

 Additionally, consider:
 - Consistency of lighting across the image
 - Plausibility of physics in the scene
 - Whether the image contains elements that are impossible or highly improbable
 - Signs of digital manipulation like repeating patterns or unrealistic smoothness

 Return ONLY valid JSON:
 {
   "ai_probability": 0.0,
   "label": "LIKELY_SYNTHETIC" | "POSSIBLY_SYNTHETIC" | "NO_STRONG_SIGNAL" | "UNKNOWN",
   "signals_found": ["signal1", "signal2"],
   "explanation": "One sentence summary"
 }

 Scoring guide:
 0.0 - 0.35 -> NO_STRONG_SIGNAL
 0.35 - 0.65 -> POSSIBLY_SYNTHETIC
 0.65 - 1.0 -> LIKELY_SYNTHETIC"""

     message_content = [
         {
             "type": "text",
             "text": enhanced_prompt,
         },
         {"type": "image_url", "image_url": {"url": target_url, "detail": "auto"}},
     ]

     # Run multiple times for self-consistency (we'll do 3 runs and average)
     async def _single_run(index: int):
         for attempt in range(2):
             try:
                 # Stagger the starts to avoid hitting rate limits simultaneously
                 await asyncio.sleep(index * 0.5) 
                 response = await llm.ainvoke(
                     [
                         SystemMessage(content=enhanced_prompt),
                         HumanMessage(content=message_content),
                     ]
                 )
                 return _parse_json_object(
                     response.content if isinstance(response.content, str) else str(response.content)
                 )
             except Exception:
                 if attempt == 0:
                     await asyncio.sleep(1) # Wait before retry
                     continue
                 return None

     tasks = [_single_run(i) for i in range(3)]
     raw_results = await asyncio.gather(*tasks)
     results = [r for r in raw_results if r is not None]
     
     # Aggregate results
     if not results:
         raise RuntimeError("All vision LLM runs failed")
     
     # Average the probabilities
     total_prob = 0.0
     all_signals = []
     explanations = []
     label_votes = {"LIKELY_SYNTHETIC": 0, "POSSIBLY_SYNTHETIC": 0, "NO_STRONG_SIGNAL": 0, "UNKNOWN": 0}
     
     for result in results:
         prob = result.get("ai_probability", 0.0)
         if isinstance(prob, (int, float)):
             total_prob += float(prob)
         
         label = result.get("label", "UNKNOWN")
         if label in label_votes:
             label_votes[label] += 1
         
         signals = result.get("signals_found", [])
         if isinstance(signals, list):
             all_signals.extend(signals)
         
         explanation = result.get("explanation", "")
         if explanation:
             explanations.append(explanation)
     
     avg_prob = total_prob / len(results) if results else 0.0
     
     # Determine final label by voting
     final_label = max(label_votes, key=label_votes.get)
     if label_votes[final_label] == 0:  # All voted UNKNOWN or error
         final_label = "UNKNOWN"
     
     # Use the most common explanation or combine them
     final_explanation = explanations[0] if explanations else "Analysis completed"
     if len(explanations) > 1:
         # Check if explanations are similar
         if len(set(explanations)) == 1:
             final_explanation = explanations[0]
         else:
             final_explanation = f"Multiple analyses suggested: {'; '.join(explanations[:2])}"
     
     # Deduplicate signals
     unique_signals = list(dict.fromkeys(all_signals))
     
     provider_label = getattr(llm_descriptor, "provider_label", None) or "LLM"
     provider = getattr(llm_descriptor, "provider", None)
     model = getattr(llm_descriptor, "model", None)
     heuristic_warnings = [
         *(warnings or []),
         "This is a heuristic synthetic-media review with self-consistency checking, not a forensic deepfake determination.",
     ]
     return _build_result(
         {
             "ai_probability": avg_prob,
             "label": final_label,
             "signals_found": unique_signals,
             "explanation": final_explanation,
         },
         media_url=target_url,
         analysis_mode="vision_llm_heuristic",
         provider=provider,
         provider_label=provider_label,
         model=model,
         warnings=heuristic_warnings,
         limitations=VISION_HEURISTIC_LIMITATIONS,
     )


async def detect_media(image_urls: list[str]) -> dict:
    if not image_urls:
        result = _base_result(None)
        result.update(
            {
                "analysis_mode": "none",
                "review_recommended": False,
                "explanation": "No media found to analyze.",
            }
        )
        return result

    target_url = image_urls[0]
    warnings = []
    if len(image_urls) > 1:
        warnings.append("Only the first extracted image was analyzed in this run.")

    mode = _get_mode()
    if mode == "disabled":
        result = _base_result(target_url)
        result.update(
            {
                "analysis_mode": "disabled",
                "explanation": "Media authenticity review is disabled in the current configuration.",
                "warnings": warnings,
            }
        )
        return result

    if mode in {"auto", "specialized"} and _get_classifier_url():
        try:
            specialized_result = _specialized_result(target_url)
            specialized_result["warnings"] = list(
                dict.fromkeys([*specialized_result.get("warnings", []), *warnings])
            )
            return specialized_result
        except Exception as exc:
            if mode == "specialized":
                result = _base_result(target_url)
                result.update(
                    {
                        "analysis_mode": "specialized_classifier",
                        "provider": "custom_endpoint",
                        "provider_label": "Specialized classifier",
                        "model": urlparse(_get_classifier_url()).netloc or _get_classifier_url(),
                        "explanation": f"Specialized media review failed: {exc}",
                        "warnings": warnings,
                        "limitations": SPECIALIZED_LIMITATIONS,
                    }
                )
                return result
            warnings.append(f"Specialized classifier failed, so FactLens fell back to heuristic review: {exc}")

    if mode == "specialized" and not _get_classifier_url():
        result = _base_result(target_url)
        result.update(
            {
                "analysis_mode": "specialized_classifier",
                "provider": "custom_endpoint",
                "provider_label": "Specialized classifier",
                "model": None,
                "explanation": "Specialized media review was requested, but no classifier endpoint is configured.",
                "warnings": warnings,
                "limitations": SPECIALIZED_LIMITATIONS,
            }
        )
        return result

    try:
        return await _vision_heuristic_result(target_url, warnings=warnings)
    except Exception as exc:
        result = _base_result(target_url)
        result.update(
            {
                "analysis_mode": "vision_llm_heuristic",
                "provider": getattr(llm_descriptor, "provider", None),
                "provider_label": getattr(llm_descriptor, "provider_label", None),
                "model": getattr(llm_descriptor, "model", None),
                "explanation": llm_descriptor.issue if llm is None else f"Media detection failed: {exc}",
                "warnings": warnings,
                "limitations": VISION_HEURISTIC_LIMITATIONS if llm is not None else [],
            }
        )
        return result
