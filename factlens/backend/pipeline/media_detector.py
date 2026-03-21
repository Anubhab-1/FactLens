from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


llm = (
    ChatNVIDIA(
        model="meta/llama-3.2-90b-vision-instruct",
        api_key=os.getenv("NVIDIA_API_KEY"),
        temperature=0.1,
        max_tokens=1024,
    )
    if os.getenv("NVIDIA_API_KEY")
    else None
)

SYSTEM_PROMPT = """You are an expert at distinguishing AI-generated or synthetically manipulated images (deepfakes) from authentic photographs.
Analyze the provided image(s) for these AI-generation and manipulation signals:
- Unnatural lighting, physically impossible reflections, or inconsistent shadows
- Distorted text or garbled lettering in the background
- Anatomical anomalies (e.g., asymmetrical faces, hands with too many/few fingers, blending teeth)
- Oversmoothed textures, hyper-realistic glossy finishes, or plastic-like skin
- Edge blending artifacts, especially around hair, glasses, or borders between objects
- Unnatural bokeh (background blur) or impossible depth of field

Return ONLY valid JSON:
{
  "ai_probability": 0.0,
  "label": "LIKELY_AI" | "POSSIBLY_AI" | "LIKELY_HUMAN" | "UNKNOWN",
  "signals_found": ["signal1", "signal2"],
  "explanation": "One sentence summary"
}

Scoring guide:
0.0 - 0.35 -> LIKELY_HUMAN
0.35 - 0.65 -> POSSIBLY_AI
0.65 - 1.0 -> LIKELY_AI"""


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


async def detect_media(image_urls: list[str]) -> dict:
    if not image_urls:
        return {
            "ai_probability": None,
            "label": "UNKNOWN",
            "signals_found": [],
            "explanation": "No media found to analyze.",
            "media_url": None
        }

    # Analyze the first available image
    target_url = image_urls[0]

    try:
        if llm is None:
            raise RuntimeError("NVIDIA_API_KEY is not configured.")

        message_content = [
            {"type": "text", "text": "Analyze this image for signs of AI generation or deepfake manipulation."},
            {"type": "image_url", "image_url": {"url": target_url}}
        ]

        response = await llm.ainvoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=message_content),
        ])
        
        parsed = _parse_json_object(
            response.content if isinstance(response.content, str) else str(response.content)
        )
        parsed["media_url"] = target_url
        return parsed
    except Exception as exc:
        return {
            "ai_probability": None,
            "label": "UNKNOWN",
            "signals_found": [],
            "explanation": f"Media detection failed.",
            "media_url": target_url
        }
