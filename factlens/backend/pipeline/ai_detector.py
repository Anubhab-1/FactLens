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
        model="meta/llama-3.1-70b-instruct",
        api_key=os.getenv("NVIDIA_API_KEY"),
        temperature=0.1,
        max_tokens=2048,
    )
    if os.getenv("NVIDIA_API_KEY")
    else None
)

SYSTEM_PROMPT = """You are an expert at distinguishing AI-generated text from human-written text.
Analyze the provided text solely for these stylistic AI-generation signals:
- Overly uniform sentence structure and length
- Absence of personal voice, typos, or colloquialisms
- Excessive use of transitional phrases (Furthermore, Moreover, In conclusion)
- Unnaturally comprehensive coverage without a clear perspective
- Lack of specific anecdotes or first-person observations

CRITICAL RULE: DO NOT fact-check the text. False information, factual errors, or lies are commonly written by humans and are NOT signals of AI generation. You must judge based ONLY on stylistic and structural markers, regardless of whether the content is true or false.

Return ONLY valid JSON:
{
  'ai_probability': 0.0,
  'label': 'LIKELY_AI' | 'POSSIBLY_AI' | 'LIKELY_HUMAN',
  'signals_found': ['signal1', 'signal2'],
  'explanation': 'One sentence summary'
}

Scoring guide:
0.0 - 0.35 → LIKELY_HUMAN
0.35 - 0.65 → POSSIBLY_AI
0.65 - 1.0 → LIKELY_AI"""


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


async def detect_ai(text: str) -> dict:
    try:
        if llm is None:
            raise RuntimeError("NVIDIA_API_KEY is not configured.")

        response = await llm.ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=f"Analyze this text:\n\n{text[:3000]}"),
            ]
        )
        return _parse_json_object(
            response.content if isinstance(response.content, str) else str(response.content)
        )
    except Exception:
        return {
            "ai_probability": None,
            "label": "UNKNOWN",
            "signals_found": [],
            "explanation": "Detection failed.",
        }
