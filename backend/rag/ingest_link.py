"""Загрузка внешней ссылки (статья/отчёт по URL) в те же TextBlock, что и
локальные файлы (backend/nlp_pipeline/ingest.py) — дальше общий путь
chunk_blocks -> эмбеддинги в DocumentStore. Поддерживает прямые PDF-ссылки
и обычные HTML-страницы (текст, извлечённый из p/h1-h3/li/td, без скриптов
и навигационной обвязки).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from backend.nlp_pipeline.ingest import TextBlock

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KG-RAG-bot/1.0)"}


def fetch_url_blocks(url: str, timeout: int = 20) -> tuple[list[TextBlock], str]:
    """Возвращает (блоки, заголовок источника)."""
    resp = requests.get(url, timeout=timeout, headers=_HEADERS)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "").lower()

    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return _extract_pdf_blocks(resp.content), _title_from_url(url)

    return _extract_html_blocks(resp.text, url)


def _extract_pdf_blocks(data: bytes) -> list[TextBlock]:
    import fitz  # PyMuPDF

    blocks: list[TextBlock] = []
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        for i, page in enumerate(doc):
            text = (page.get_text("text") or "").strip()
            if text:
                blocks.append(TextBlock(text=text, kind="paragraph", location=f"page {i + 1}"))
    finally:
        doc.close()
    return blocks


def _extract_html_blocks(html: str, url: str) -> tuple[list[TextBlock], str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "aside"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title and soup.title.string else _title_from_url(url)

    blocks: list[TextBlock] = []
    for i, el in enumerate(soup.find_all(["p", "h1", "h2", "h3", "li", "td"])):
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if len(text) < 20:
            continue
        kind = "heading" if el.name in ("h1", "h2", "h3") else "paragraph"
        blocks.append(TextBlock(text=text, kind=kind, location=f"para {i}"))
    return blocks, title


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc + parsed.path).strip("/") or url
