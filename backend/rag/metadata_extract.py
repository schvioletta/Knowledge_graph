"""Извлечение метаданных документа для корпусного индекса RAG.

LLM-путь — один вызов YandexGPT по аннотации и началу текста.
Fallback без ключа — эвристики по имени файла, дате и языку блоков.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.llm_client import complete_for_index, is_index_llm_configured
from backend.nlp_pipeline.chunking import chunk_blocks
from backend.nlp_pipeline.ingest import FileMeta, TextBlock
from backend.nlp_pipeline.sections import SECTION_ORDER, extract_key_sections

_ARTICLES_FOLDER = "статьи"

_SYSTEM_PROMPT = """Ты — экстрактор метаданных научных и технических документов (RU/EN).
По фрагменту текста извлеки метаданные СТРОГО из текста, не придумывай факты.
Если поле неизвестно — используй null для year, пустую строку для текстовых полей,
authors как пустой список, reliability_score как 0.5.

Верни СТРОГО JSON без markdown:
{
  "title": "название документа",
  "authors": ["Автор 1", "Автор 2"],
  "source": "журнал/конференция/организация/тип источника",
  "year": 2022,
  "geography": "RU или INTL или регион",
  "language": "ru или en или mixed",
  "domain": "тематическая область",
  "reliability_score": 0.0-1.0,
  "document_summary": "2-4 предложения о содержании"
}
"""


class DocumentMetadata(BaseModel):
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    source: str = ""
    year: Optional[int] = None
    geography: str = ""
    language: str = ""
    domain: str = ""
    reliability_score: float = 0.5
    document_summary: str = ""
    abstract: str = ""


def is_articles_source(source_path: str | Path) -> bool:
    """Файл из папки «статьи» (любой уровень вложенности, без учёта регистра)."""
    return _ARTICLES_FOLDER in (p.lower() for p in Path(source_path).parts)


def abstract_blocks_from_document(blocks: list[TextBlock]) -> list[TextBlock]:
    sections = extract_key_sections(blocks)
    return sections.get("abstract") or blocks[:3]


def rag_index_blocks(source_path: str | Path, blocks: list[TextBlock]) -> list[TextBlock]:
    """Блоки для офлайн-индекса RAG: статьи — аннотация, остальные — весь текст."""
    if is_articles_source(source_path):
        return abstract_blocks_from_document(blocks)
    return blocks


def rag_activate_blocks(source_path: str | Path, blocks: list[TextBlock]) -> list[TextBlock]:
    """Блоки при активации документа по запросу: статьи — ключевые секции, остальные — весь текст."""
    if not is_articles_source(source_path):
        return blocks
    sections = extract_key_sections(blocks)
    selected: list[TextBlock] = []
    for name in SECTION_ORDER:
        selected.extend(sections.get(name, []))
    return selected or blocks


def abstract_text(blocks: list[TextBlock]) -> str:
    abs_blocks = abstract_blocks_from_document(blocks)
    return "\n\n".join(b.text for b in abs_blocks if b.text.strip())


def _detect_language(blocks: list[TextBlock]) -> str:
    chunks = chunk_blocks(blocks[:20], max_chars=5000)
    if not chunks:
        return "unknown"
    langs = Counter(c.language for c in chunks)
    top = langs.most_common(1)[0][0]
    if top == "mixed" and len(langs) > 1:
        return "mixed"
    return top


def _extract_json(raw: str) -> Optional[dict[str, Any]]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _heuristic_metadata(blocks: list[TextBlock], file_meta: FileMeta) -> DocumentMetadata:
    abs_text = abstract_text(blocks)
    title = Path(file_meta.source_file).stem.replace("_", " ")
    year: Optional[int] = None
    if file_meta.modified:
        try:
            year = int(file_meta.modified[:4])
        except ValueError:
            year = None
    summary = abs_text[:500].strip()
    if len(abs_text) > 500:
        summary += "…"
    return DocumentMetadata(
        title=title,
        authors=[],
        source=file_meta.source_file,
        year=year,
        geography="unknown",
        language=_detect_language(blocks),
        domain="unknown",
        reliability_score=0.3,
        document_summary=summary or title,
        abstract=abs_text,
    )


def _sanitize_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    out = dict(parsed)
    for key in ("title", "source", "geography", "language", "domain", "document_summary", "abstract"):
        if out.get(key) is None:
            out[key] = ""
    if out.get("authors") is None:
        out["authors"] = []
    if out.get("year") is None:
        out["year"] = None
    if out.get("reliability_score") is None:
        out["reliability_score"] = 0.5
    return out


def _llm_metadata(blocks: list[TextBlock], file_meta: FileMeta) -> Optional[DocumentMetadata]:
    abs_text = abstract_text(blocks)
    preview = "\n\n".join(b.text for b in blocks[:15])[:3000]
    prompt = (
        f"Имя файла: {file_meta.source_file}\n\n"
        f"АННОТАЦИЯ:\n{abs_text[:4000]}\n\n"
        f"НАЧАЛО ДОКУМЕНТА:\n{preview}"
    )
    raw = complete_for_index(prompt, system=_SYSTEM_PROMPT)
    if not raw:
        return None
    parsed = _extract_json(raw)
    if not parsed:
        print(f"[metadata_extract] Не удалось распарсить JSON: {raw[:200]!r}")
        return None
    try:
        meta = DocumentMetadata(**_sanitize_parsed(parsed))
        if not meta.title or str(meta.title).lower() == "null":
            meta.title = Path(file_meta.source_file).stem.replace("_", " ")
        if not meta.abstract:
            meta.abstract = abs_text
        meta.authors = [a for a in meta.authors if a and str(a).lower() != "null"]
        return meta
    except Exception as e:
        print(f"[metadata_extract] Невалидные метаданные: {e}")
        return None


def extract_metadata(blocks: list[TextBlock], file_meta: FileMeta) -> DocumentMetadata:
    if is_index_llm_configured():
        llm_meta = _llm_metadata(blocks, file_meta)
        if llm_meta:
            return llm_meta
    return _heuristic_metadata(blocks, file_meta)
