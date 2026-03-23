from __future__ import annotations

import asyncio
from functools import partial
import os
import re
import time
from urllib.parse import urljoin

os.environ.setdefault("USER_AGENT", "FactLens/1.0")

import trafilatura
from bs4 import BeautifulSoup
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers import Html2TextTransformer


MIN_STRONG_TEXT_CHARS = 200
MIN_USABLE_TEXT_CHARS = 120
MAX_MEDIA_URLS = 3
BROWSER_RENDER_WAIT_SECONDS = float(os.getenv("FACTLENS_BROWSER_RENDER_WAIT_SECONDS", "2.5"))
BROWSER_TIMEOUT_SECONDS = int(os.getenv("FACTLENS_BROWSER_TIMEOUT_SECONDS", "25"))


def _normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", (text or "").strip()))


def _extract_media_urls(html: str, base_url: str) -> list[str]:
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            full_url = urljoin(base_url, src)
            if full_url.startswith("http"):
                images.append(full_url)

    seen = set()
    unique_images = []
    for image_url in images:
        if image_url in seen:
            continue
        if image_url.lower().endswith(".svg") or image_url.lower().endswith(".gif"):
            continue
        seen.add(image_url)
        unique_images.append(image_url)
        if len(unique_images) >= MAX_MEDIA_URLS:
            break
    return unique_images


def _soup_visible_text(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _normalize_text(soup.get_text("\n"))


def _best_text(*candidates: str) -> str:
    normalized = [_normalize_text(candidate) for candidate in candidates if (candidate or "").strip()]
    if not normalized:
        return ""
    return max(normalized, key=len)


def _extract_text_from_html(html: str, *, url: str) -> str:
    extracted = trafilatura.extract(
        html,
        url=url,
        output_format="txt",
        favor_precision=True,
        include_comments=False,
        include_tables=False,
    )
    return _normalize_text(extracted or "")


async def _run_blocking(func, *args, **kwargs):
    to_thread = getattr(asyncio, "to_thread", None)
    if to_thread is not None:
        return await to_thread(func, *args, **kwargs)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


async def _scrape_with_http(url: str) -> dict:
    loader = AsyncHtmlLoader([url])
    documents = await loader.aload()
    if not documents:
        raise ValueError("Could not fetch URL.")

    html = documents[0].page_content
    media_urls = await _run_blocking(_extract_media_urls, html, url)
    extracted = await _run_blocking(_extract_text_from_html, html, url=url)

    transformer_text = ""
    if len(extracted) < MIN_STRONG_TEXT_CHARS:
        transformer = Html2TextTransformer()
        transformed = await _run_blocking(transformer.transform_documents, documents)
        transformer_text = _normalize_text(
            "\n\n".join(
                doc.page_content.strip()
                for doc in transformed
                if doc.page_content.strip()
            )
        )

    cleaned_text = _best_text(extracted, transformer_text)
    return {
        "html": html,
        "text": cleaned_text,
        "media": media_urls,
    }


def _make_chrome_driver():
    from selenium import webdriver
    from selenium.webdriver import ChromeOptions

    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,2200")
    options.add_argument(f"--user-agent={os.environ['USER_AGENT']}")
    return webdriver.Chrome(options=options)


def _make_edge_driver():
    from selenium import webdriver
    from selenium.webdriver import EdgeOptions

    options = EdgeOptions()
    options.use_chromium = True
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,2200")
    options.add_argument(f"--user-agent={os.environ['USER_AGENT']}")
    return webdriver.Edge(options=options)


def _scrape_with_browser_sync(url: str) -> dict:
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as exc:
        raise RuntimeError("selenium is not installed.") from exc

    browser_builders = (
        ("chrome", _make_chrome_driver),
        ("edge", _make_edge_driver),
    )
    issues = []

    for browser_name, builder in browser_builders:
        driver = None
        try:
            driver = builder()
            driver.set_page_load_timeout(BROWSER_TIMEOUT_SECONDS)
            driver.get(url)
            WebDriverWait(driver, BROWSER_TIMEOUT_SECONDS).until(
                lambda current: current.execute_script("return document.readyState") == "complete"
            )
            WebDriverWait(driver, BROWSER_TIMEOUT_SECONDS).until(
                lambda current: current.find_element(By.TAG_NAME, "body")
            )
            time.sleep(BROWSER_RENDER_WAIT_SECONDS)

            html = driver.page_source or ""
            body_text = driver.execute_script(
                "return document.body ? document.body.innerText : '';"
            ) or ""
            return {
                "html": html,
                "text": _best_text(_extract_text_from_html(html, url=url), body_text, _soup_visible_text(html)),
                "browser": browser_name,
            }
        except Exception as exc:
            issues.append(f"{browser_name}: {exc}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    raise RuntimeError("Headless browser rendering failed. " + " ".join(issues))


async def _scrape_with_browser(url: str) -> dict:
    browser_payload = await _run_blocking(_scrape_with_browser_sync, url)
    media_urls = await _run_blocking(_extract_media_urls, browser_payload.get("html", ""), url)
    return {
        **browser_payload,
        "media": media_urls,
    }


def _build_source_capture(
    *,
    mode: str,
    renderer: str,
    text: str,
    media_urls: list[str],
    fallback_used: bool,
    browser: str | None = None,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "mode": mode,
        "renderer": renderer,
        "browser": browser,
        "fallback_used": fallback_used,
        "warnings": list(dict.fromkeys(warnings or [])),
        "text_chars": len(text),
        "media_count": len(media_urls),
    }


async def scrape_url(url: str) -> dict:
    http_issue = None
    try:
        fast_capture = await _scrape_with_http(url)
    except Exception as exc:
        fast_capture = {"html": "", "text": "", "media": []}
        http_issue = str(exc)

    fast_text = fast_capture.get("text", "")
    fast_media = fast_capture.get("media", [])

    if len(fast_text) >= MIN_STRONG_TEXT_CHARS:
        return {
            "text": fast_text,
            "media": fast_media,
            "source_capture": _build_source_capture(
                mode="http",
                renderer="AsyncHtmlLoader + Trafilatura",
                text=fast_text,
                media_urls=fast_media,
                fallback_used=False,
            ),
        }

    warnings = []
    if http_issue:
        warnings.append(f"Fast extraction failed: {http_issue}")
    elif fast_text:
        warnings.append(
            "Fast HTML extraction looked incomplete, so FactLens retried the page in a headless browser."
        )
    else:
        warnings.append(
            "Fast HTML extraction returned no usable article text, so FactLens retried the page in a headless browser."
        )

    browser_issue = None
    try:
        browser_capture = await _scrape_with_browser(url)
        browser_text = browser_capture.get("text", "")
        browser_media = browser_capture.get("media", []) or fast_media
        if len(browser_text) >= MIN_USABLE_TEXT_CHARS:
            return {
                "text": browser_text,
                "media": browser_media,
                "source_capture": _build_source_capture(
                    mode="browser",
                    renderer="Headless browser rendering",
                    text=browser_text,
                    media_urls=browser_media,
                    fallback_used=True,
                    browser=browser_capture.get("browser"),
                    warnings=warnings,
                ),
            }
        browser_issue = "Browser rendering completed but still produced too little readable text."
    except Exception as exc:
        browser_issue = str(exc)

    if len(fast_text) >= MIN_USABLE_TEXT_CHARS:
        return {
            "text": fast_text,
            "media": fast_media,
            "source_capture": _build_source_capture(
                mode="http",
                renderer="AsyncHtmlLoader + Trafilatura",
                text=fast_text,
                media_urls=fast_media,
                fallback_used=True,
                warnings=[*warnings, f"Browser fallback failed: {browser_issue}"],
            ),
        }

    raise ValueError(
        "Could not extract text from URL. "
        f"Fast extraction issue: {http_issue or 'insufficient article text'}. "
        f"Browser fallback issue: {browser_issue or 'unknown browser failure'}. "
        "Please paste the article text directly."
    )
