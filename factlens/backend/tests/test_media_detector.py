from __future__ import annotations

import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.media_detector import detect_media


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload

    async def ainvoke(self, _messages):
        return SimpleNamespace(content=json.dumps(self.payload))


class MediaDetectorTests(unittest.TestCase):
    def test_detect_media_uses_specialized_classifier_when_configured(self) -> None:
        payload = {
            "ai_probability": 0.18,
            "label": "NO_STRONG_SIGNAL",
            "signals_found": ["no obvious artifact clusters"],
            "explanation": "The classifier did not find strong synthetic-media patterns.",
        }

        with patch.dict(
            os.environ,
            {
                "FACTLENS_MEDIA_DETECTOR_MODE": "specialized",
                "FACTLENS_MEDIA_CLASSIFIER_URL": "https://classifier.example/analyze",
            },
            clear=False,
        ):
            with patch("pipeline.media_detector.urlopen", return_value=_FakeResponse(payload)):
                result = asyncio.run(detect_media(["https://images.example/photo.png"]))

        self.assertEqual(result["label"], "NO_STRONG_SIGNAL")
        self.assertEqual(result["analysis_mode"], "specialized_classifier")
        self.assertEqual(result["provider"], "custom_endpoint")
        self.assertFalse(result["review_recommended"])
        self.assertIn("Classifier outputs should still be treated as risk signals", result["limitations"][0])

    def test_detect_media_auto_falls_back_to_vision_heuristic_with_warning(self) -> None:
        llm_payload = {
            "ai_probability": 0.58,
            "label": "POSSIBLY_SYNTHETIC",
            "signals_found": ["garbled text"],
            "explanation": "Some visual cues look synthetic, but this is not definitive.",
        }

        with patch.dict(
            os.environ,
            {
                "FACTLENS_MEDIA_DETECTOR_MODE": "auto",
                "FACTLENS_MEDIA_CLASSIFIER_URL": "https://classifier.example/analyze",
            },
            clear=False,
        ):
            with patch("pipeline.media_detector.urlopen", side_effect=RuntimeError("endpoint offline")):
                with patch("pipeline.media_detector.llm", new=_FakeLLM(llm_payload)):
                    with patch(
                        "pipeline.media_detector.llm_descriptor",
                        new=SimpleNamespace(
                            provider="nvidia",
                            provider_label="NVIDIA",
                            model="meta/llama-3.2-90b-vision-instruct",
                            issue=None,
                        ),
                    ):
                        result = asyncio.run(
                            detect_media(
                                [
                                    "https://images.example/photo.png",
                                    "https://images.example/other.png",
                                ]
                            )
                        )

        self.assertEqual(result["label"], "POSSIBLY_SYNTHETIC")
        self.assertEqual(result["analysis_mode"], "vision_llm_heuristic")
        self.assertEqual(result["provider_label"], "NVIDIA")
        self.assertTrue(result["review_recommended"])
        self.assertTrue(any("fell back to heuristic review" in warning for warning in result["warnings"]))
        self.assertTrue(any("Only the first extracted image was analyzed" in warning for warning in result["warnings"]))

    def test_detect_media_disabled_returns_caveated_unknown_result(self) -> None:
        with patch.dict(
            os.environ,
            {
                "FACTLENS_MEDIA_DETECTOR_MODE": "disabled",
                "FACTLENS_MEDIA_CLASSIFIER_URL": "",
            },
            clear=False,
        ):
            result = asyncio.run(detect_media(["https://images.example/photo.png"]))

        self.assertEqual(result["label"], "UNKNOWN")
        self.assertEqual(result["analysis_mode"], "disabled")
        self.assertTrue(result["review_recommended"])
        self.assertIn("disabled", result["explanation"].lower())


if __name__ == "__main__":
    unittest.main()
