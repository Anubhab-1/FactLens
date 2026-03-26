from __future__ import annotations

import ast
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SPECIALIZED_LIMITATIONS = [
    "Classifier outputs should still be treated as risk signals until a human reviewer confirms the result.",
    "Specialized models may have biases based on their training data and may not generalize to all types of deepfakes.",
]
NO_FALLBACK_WARNING = (
    "Visual media review is unavailable because FactLens no longer uses the vision-LLM fallback."
)


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
    raw_mode = os.getenv("FACTLENS_MEDIA_DETECTOR_MODE", "auto").strip().lower()
    aliases = {
        "vision_llm": "auto",
    }
    mode = aliases.get(raw_mode, raw_mode)
    return mode if mode in {"auto", "specialized", "disabled"} else "auto"


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


def _unavailable_result(
    target_url: str,
    explanation: str,
    *,
    warnings: list[str] | None = None,
) -> dict:
    result = _base_result(target_url)
    result.update(
        {
            "analysis_mode": "unavailable",
            "explanation": explanation,
            "warnings": list(dict.fromkeys([*(warnings or [])])),
        }
    )
    return result


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

    classifier_url = _get_classifier_url()
    if mode in {"auto", "specialized"} and classifier_url:
        try:
            specialized_result = _specialized_result(target_url)
            specialized_result["warnings"] = list(
                dict.fromkeys([*specialized_result.get("warnings", []), *warnings])
            )
            return specialized_result
        except Exception as exc:
            return _unavailable_result(
                target_url,
                f"Specialized media review failed: {exc}",
                warnings=[*warnings, NO_FALLBACK_WARNING],
            )

    if mode == "specialized":
        return _unavailable_result(
            target_url,
            "Specialized media review was requested, but no classifier endpoint is configured.",
            warnings=[*warnings, NO_FALLBACK_WARNING],
        )

    return _unavailable_result(
        target_url,
        "Visual media authenticity review is unavailable because no specialized classifier endpoint is configured.",
        warnings=[*warnings, NO_FALLBACK_WARNING],
    )
