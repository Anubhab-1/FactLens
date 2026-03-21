from __future__ import annotations

import asyncio
from functools import partial
import os
import re
from urllib.parse import urljoin

os.environ.setdefault("USER_AGENT", "FactLens/1.0")

import trafilatura
from bs4 import BeautifulSoup
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers import Html2TextTransformer


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
    for img in images:
        if img not in seen and not img.lower().endswith(".svg") and not img.lower().endswith(".gif"):
            seen.add(img)
            unique_images.append(img)
            if len(unique_images) >= 3:
                break
    return unique_images


async def _run_blocking(func, *args):
    to_thread = getattr(asyncio, "to_thread", None)
    if to_thread is not None:
        return await to_thread(func, *args)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args))


async def scrape_url(url: str) -> dict:
    loader = AsyncHtmlLoader([url])
    documents = await loader.aload()
    
    if not documents:
        raise ValueError("Could not fetch URL.")
        
    html = documents[0].page_content
    media_urls = await _run_blocking(_extract_media_urls, html, url)
    
    extracted = await _run_blocking(
        trafilatura.extract,
        html,
        url=url,
        output_format="txt",
        favor_precision=True,
        include_comments=False,
        include_tables=False,
    )
    cleaned_text = _normalize_text(extracted or "")

    if len(cleaned_text) < 200:
        transformer = Html2TextTransformer()
        transformed = await _run_blocking(transformer.transform_documents, documents)
        cleaned_text = _normalize_text(
            "\n\n".join(
                doc.page_content.strip() for doc in transformed if doc.page_content.strip()
            )
        )

    if not cleaned_text:
        raise ValueError("Could not extract text from URL. Please paste the text directly.")

    return {"text": cleaned_text, "media": media_urls}

