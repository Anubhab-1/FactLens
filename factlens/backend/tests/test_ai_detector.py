from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pipeline.ai_detector as ai_detector


class _QueuedLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def ainvoke(self, _messages):
        if not self._responses:
            raise AssertionError("No queued detector responses remain.")
        return SimpleNamespace(content=self._responses.pop(0))


class AiDetectorTests(unittest.TestCase):
    def test_detect_ai_downgrades_short_benchmark_fact_lists(self) -> None:
        llm = _QueuedLLM(
            [
                json.dumps(
                    {
                        "ai_probability": 0.9,
                        "label": "LIKELY_AI",
                        "signals_found": [
                            "Overly uniform sentence structure and length",
                            "Absence of personal voice, typos, or colloquialisms",
                        ],
                        "explanation": "The text looks highly uniform and templated.",
                    }
                )
            ]
        )
        descriptor = SimpleNamespace(
            provider="nvidia",
            provider_label="NVIDIA",
            model="meta/llama-3.1-70b-instruct",
            issue=None,
        )
        text = (
            "Paris is the capital of France. "
            "The chemical symbol for gold is Au. "
            "Earth has one natural satellite, the Moon. "
            "The Pacific Ocean is the largest ocean on Earth."
        )

        with patch.object(ai_detector, "llm", new=llm):
            with patch.object(ai_detector, "llm_descriptor", new=descriptor):
                result = asyncio.run(ai_detector.detect_ai(text))

        self.assertEqual(result["label"], "POSSIBLY_AI")
        self.assertLessEqual(result["ai_probability"], 0.64)
        self.assertIn("benchmark-style fact lists", " ".join(result["warnings"]).lower())

    def test_detect_ai_retries_after_malformed_response(self) -> None:
        llm = _QueuedLLM(
            [
                "not valid json",
                json.dumps(
                    {
                        "ai_probability": "72%",
                        "signals_found": "uniform cadence",
                        "explanation": "The writing is unusually even and templated.",
                    }
                ),
            ]
        )
        descriptor = SimpleNamespace(
            provider="google",
            provider_label="Google Gemini",
            model="gemini-1.5-pro",
            issue=None,
        )

        with patch.object(ai_detector, "llm", new=llm):
            with patch.object(ai_detector, "llm_descriptor", new=descriptor):
                result = asyncio.run(ai_detector.detect_ai("Example text"))

        self.assertEqual(result["label"], "LIKELY_AI")
        self.assertAlmostEqual(result["ai_probability"], 0.72)
        self.assertEqual(result["analysis_mode"], "text_llm_stylistic_review")
        self.assertEqual(result["provider_label"], "Google Gemini")
        self.assertIn("retried", " ".join(result["warnings"]).lower())
        self.assertEqual(result["signals_found"], ["uniform cadence"])

    def test_detect_ai_returns_unknown_after_two_malformed_responses(self) -> None:
        llm = _QueuedLLM(["still bad", "still bad again"])
        descriptor = SimpleNamespace(
            provider="nvidia",
            provider_label="NVIDIA",
            model="meta/llama-3.1-70b-instruct",
            issue=None,
        )

        with patch.object(ai_detector, "llm", new=llm):
            with patch.object(ai_detector, "llm_descriptor", new=descriptor):
                result = asyncio.run(ai_detector.detect_ai("Example text"))

        self.assertEqual(result["label"], "UNKNOWN")
        self.assertIsNone(result["ai_probability"])
        self.assertTrue(result["review_recommended"])
        self.assertIn("failed after two malformed model responses", result["explanation"].lower())
        self.assertIn("did not return trustworthy structured output", " ".join(result["warnings"]).lower())
        self.assertEqual(result["provider_label"], "NVIDIA")


if __name__ == "__main__":
    unittest.main()
