from __future__ import annotations

import ast
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from llm_provider import create_chat_model

llm, llm_descriptor = create_chat_model("text_detector", temperature=0.1, max_tokens=2048)

SYSTEM_PROMPT = """You are an expert at distinguishing AI-generated text from human-written text.
Analyze the provided text solely for these stylistic AI-generation signals:
- Overly uniform sentence structure and length
- Absence of personal voice, typos, or colloquialisms
- Excessive use of transitional phrases (Furthermore, Moreover, In conclusion)
- Unnaturally comprehensive coverage without a clear perspective
- Lack of specific anecdotes or first-person observations
- Technical or robotic "tone consistency" without emotional variance or rhythmic shifts

CRITICAL RULE: DO NOT fact-check the text. False information, factual errors, or lies are commonly written by humans and are NOT signals of AI generation. You must judge based ONLY on stylistic and structural markers, regardless of whether the content is true or false.

Return ONLY valid JSON:
{
  "ai_probability": 0.0,
  "label": "LIKELY_AI" | "POSSIBLY_AI" | "LIKELY_HUMAN",
  "signals_found": ["signal1", "signal2"],
  "explanation": "One sentence summary"
}

Scoring guide:
0.0 - 0.35 -> LIKELY_HUMAN
0.35 - 0.65 -> POSSIBLY_AI
0.65 - 1.0 -> LIKELY_AI"""

VALID_LABELS = {"LIKELY_AI", "POSSIBLY_AI", "LIKELY_HUMAN", "UNKNOWN"}
TEXT_LIMITATIONS = [
    "This is a stylistic text-authenticity estimate, not proof of human or AI authorship.",
    "Strong editing, translation, or templated writing can look AI-like even when a human wrote the text.",
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
            raise ValueError("Could not parse AI detector response.") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed


def _normalize_probability(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            try:
                return max(0.0, min(1.0, float(text[:-1].strip()) / 100.0))
            except ValueError:
                return None
        try:
            value = float(text)
        except ValueError:
            return None

    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None

    return max(0.0, min(1.0, probability))


def _label_from_probability(probability: float | None) -> str:
    if probability is None:
        return "UNKNOWN"
    if probability >= 0.65:
        return "LIKELY_AI"
    if probability >= 0.35:
        return "POSSIBLY_AI"
    return "LIKELY_HUMAN"


def _normalize_label(value: object, probability: float | None) -> str:
    label = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if label in VALID_LABELS:
        return label
    return _label_from_probability(probability)


def _normalize_signals(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _default_explanation(label: str) -> str:
    if label == "LIKELY_AI":
        return "The text shows multiple machine-writing cues."
    if label == "POSSIBLY_AI":
        return "The text mixes human-like and machine-like stylistic cues."
    if label == "LIKELY_HUMAN":
        return "The text reads more like human-authored writing than a machine-generated draft."
    return "The text-authenticity model could not produce a trustworthy classification."


def _looks_like_benchmark_fact_list(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return False

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", normalized)
        if sentence.strip()
    ]
    if not 2 <= len(sentences) <= 6:
        return False

    lowered = f" {normalized.lower()} "
    if any(marker in lowered for marker in (" i ", " we ", " my ", " our ", " me ", " us ", " you ")):
        return False
    if any(
        marker in lowered
        for marker in ("furthermore", "moreover", "however", "in conclusion", "for example", "for instance")
    ):
        return False

    word_counts = [len(re.findall(r"\b\w+\b", sentence)) for sentence in sentences]
    if not word_counts or max(word_counts) > 16:
        return False

    average_words = sum(word_counts) / len(word_counts)
    return average_words <= 12


def _build_detection_result(
    *,
    probability: float | None,
    label: str,
    explanation: str,
    signals_found: list[str] | None = None,
    warnings: list[str] | None = None,
    review_recommended: bool | None = None,
) -> dict:
    resolved_review_recommended = (
        bool(review_recommended)
        if review_recommended is not None
        else label in {"LIKELY_AI", "POSSIBLY_AI", "UNKNOWN"}
    )

    return {
        "ai_probability": probability if label != "UNKNOWN" else None,
        "label": label,
        "signals_found": list(dict.fromkeys(signals_found or [])),
        "explanation": explanation,
        "analysis_mode": "text_llm_stylistic_review",
        "provider": llm_descriptor.provider,
        "provider_label": llm_descriptor.provider_label,
        "model": llm_descriptor.model,
        "review_recommended": resolved_review_recommended,
        "warnings": list(dict.fromkeys(warnings or [])),
        "limitations": list(TEXT_LIMITATIONS),
    }


def _calibrate_detection_result(text: str, detection: dict) -> dict:
    probability = detection.get("ai_probability")
    if probability is None:
        return detection

    if _looks_like_benchmark_fact_list(text) and detection.get("label") == "LIKELY_AI":
        explanation = (
            f"{detection.get('explanation', '').rstrip()} "
            "This input also resembles a short benchmark fact list, which often reads as templated even when written by a human."
        ).strip()
        return _build_detection_result(
            probability=min(float(probability), 0.64),
            label="POSSIBLY_AI",
            explanation=explanation,
            signals_found=detection.get("signals_found", []),
            warnings=list(detection.get("warnings", []))
            + ["Short benchmark-style fact lists can look AI-like even when they are human-written."],
            review_recommended=True,
        )

    return detection


def _coerce_detection_payload(parsed: dict) -> dict:
    probability = _normalize_probability(parsed.get("ai_probability"))
    label = _normalize_label(parsed.get("label"), probability)
    explanation = str(parsed.get("explanation", "")).strip() or _default_explanation(label)

    return _build_detection_result(
        probability=probability,
        label=label,
        explanation=explanation,
        signals_found=_normalize_signals(parsed.get("signals_found")),
    )


async def _invoke_detector(user_message: str) -> str:
    if llm is None:
        raise RuntimeError(llm_descriptor.issue or "No text-authenticity model is configured.")

    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]
    )
    return response.content if isinstance(response.content, str) else str(response.content)


async def detect_ai(text: str) -> dict:
    if llm is None:
        return _build_detection_result(
            probability=None,
            label="UNKNOWN",
            explanation=llm_descriptor.issue or "No text-authenticity model is configured.",
            warnings=["Text-authenticity analysis is unavailable because no LLM provider is configured."],
            review_recommended=True,
        )

    user_message = f"Analyze this text:\n\n{text[:3000]}"

    try:
        initial_response = await _invoke_detector(user_message)
        detection = _coerce_detection_payload(_parse_json_object(initial_response))
        return _calibrate_detection_result(text, detection)
    except (json.JSONDecodeError, ValueError):
        try:
            retry_response = await _invoke_detector(
                (
                    f"{user_message}\n\n"
                    "Return strict JSON with double-quoted keys and values only. "
                    "Do not include markdown, commentary, or code fences."
                )
            )
            detection = _coerce_detection_payload(_parse_json_object(retry_response))
            calibrated = _calibrate_detection_result(text, detection)
            return {
                **calibrated,
                "warnings": list(
                    dict.fromkeys(
                        calibrated.get("warnings", [])
                        + ["The first text-authenticity response was malformed, so FactLens retried the analysis."]
                    )
                ),
            }
        except Exception:
            return _build_detection_result(
                probability=None,
                label="UNKNOWN",
                explanation=(
                    "Text-authenticity analysis failed after two malformed model responses. "
                    "Treat this as unavailable and review the writing manually."
                ),
                warnings=[
                    "The text-authenticity model did not return trustworthy structured output."
                ],
                review_recommended=True,
            )
    except Exception as exc:
        return _build_detection_result(
            probability=None,
            label="UNKNOWN",
            explanation=f"Detection failed: {exc}",
            warnings=["The text-authenticity analysis request did not complete successfully."],
            review_recommended=True,
        )
