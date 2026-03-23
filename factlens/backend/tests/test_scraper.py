from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from pipeline.scraper import scrape_url


class ScraperTests(unittest.TestCase):
    def test_scrape_url_uses_fast_html_capture_when_text_is_strong(self) -> None:
        http_payload = {
            "html": "<html></html>",
            "text": "A" * 240,
            "media": ["https://example.com/image.jpg"],
        }

        with patch("pipeline.scraper._scrape_with_http", new=AsyncMock(return_value=http_payload)):
            with patch("pipeline.scraper._scrape_with_browser", new=AsyncMock()) as browser_scrape:
                result = asyncio.run(scrape_url("https://example.com/article"))

        browser_scrape.assert_not_awaited()
        self.assertEqual(result["text"], http_payload["text"])
        self.assertEqual(result["source_capture"]["mode"], "http")
        self.assertFalse(result["source_capture"]["fallback_used"])

    def test_scrape_url_uses_browser_fallback_when_fast_capture_is_thin(self) -> None:
        http_payload = {
            "html": "<html></html>",
            "text": "Too short to trust." * 4,
            "media": [],
        }
        browser_payload = {
            "html": "<html><body>Rendered text</body></html>",
            "text": "Rendered article body. " * 12,
            "media": ["https://example.com/rendered.jpg"],
            "browser": "chrome",
        }

        with patch("pipeline.scraper._scrape_with_http", new=AsyncMock(return_value=http_payload)):
            with patch("pipeline.scraper._scrape_with_browser", new=AsyncMock(return_value=browser_payload)):
                result = asyncio.run(scrape_url("https://example.com/article"))

        self.assertEqual(result["text"], browser_payload["text"])
        self.assertEqual(result["source_capture"]["mode"], "browser")
        self.assertTrue(result["source_capture"]["fallback_used"])
        self.assertEqual(result["source_capture"]["browser"], "chrome")

    def test_scrape_url_returns_usable_fast_capture_if_browser_fallback_fails(self) -> None:
        http_payload = {
            "html": "<html></html>",
            "text": "Usable fallback text. " * 8,
            "media": [],
        }

        with patch("pipeline.scraper._scrape_with_http", new=AsyncMock(return_value=http_payload)):
            with patch(
                "pipeline.scraper._scrape_with_browser",
                new=AsyncMock(side_effect=RuntimeError("browser failed")),
            ):
                result = asyncio.run(scrape_url("https://example.com/article"))

        self.assertEqual(result["source_capture"]["mode"], "http")
        self.assertTrue(result["source_capture"]["fallback_used"])
        self.assertIn("Browser fallback failed: browser failed", result["source_capture"]["warnings"])

    def test_scrape_url_raises_when_both_fast_and_browser_capture_fail(self) -> None:
        http_payload = {
            "html": "<html></html>",
            "text": "tiny",
            "media": [],
        }

        with patch("pipeline.scraper._scrape_with_http", new=AsyncMock(return_value=http_payload)):
            with patch(
                "pipeline.scraper._scrape_with_browser",
                new=AsyncMock(side_effect=RuntimeError("browser failed")),
            ):
                with self.assertRaises(ValueError):
                    asyncio.run(scrape_url("https://example.com/article"))


if __name__ == "__main__":
    unittest.main()
