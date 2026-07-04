"""Персистентный кэш NER по тексту чанка (хранится в rag_chunks[].ner в Neo4j).

При повторном RAG-запросе с теми же чанками LLM не вызывается — берётся
сохранённый ExtractionResult. При первом попадании чанка результат пишется
обратно в Neo4j (lazy). Опционально NER_PRECOMPUTE_ON_INDEX=1 считает NER
сразу при загрузке/активации документа.

Инвалидация: поле ner.v должно совпадать с NER_CACHE_VERSION; ner.text_hash —
с sha256 текста чанка.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Optional

from pydantic import ValidationError

from backend.nlp_pipeline.ner_extract import (
    ExtractionResult,
    RawEntity,
    RawRelation,
    extract_chunk_entities,
)
from backend.ner_llm import is_ner_configured


def cache_version() -> int:
    return int(os.getenv("NER_CACHE_VERSION", "1"))


def precompute_on_index() -> bool:
    return os.getenv("NER_PRECOMPUTE_ON_INDEX", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pack_ner(result: ExtractionResult, text: str) -> dict[str, Any]:
    return {
        "v": cache_version(),
        "text_hash": text_hash(text),
        "entities": [e.model_dump(mode="json") for e in result.entities],
        "relations": [r.model_dump(mode="json") for r in result.relations],
    }


def load_cached_ner(text: str, cached: dict[str, Any] | None) -> Optional[ExtractionResult]:
    if not cached or not isinstance(cached, dict):
        return None
    if cached.get("v") != cache_version():
        return None
    if cached.get("text_hash") != text_hash(text):
        return None

    entities: list[RawEntity] = []
    for e in cached.get("entities") or []:
        try:
            entities.append(RawEntity(**e))
        except ValidationError:
            return None

    relations: list[RawRelation] = []
    for r in cached.get("relations") or []:
        try:
            relations.append(RawRelation(**r))
        except ValidationError:
            return None

    return ExtractionResult(entities=entities, relations=relations)


def resolve_chunk_ner(
    text: str,
    cached: dict[str, Any] | None,
) -> tuple[ExtractionResult, dict[str, Any] | None, bool]:
    """(result, ner_blob для записи в Neo4j или None, from_cache)."""
    loaded = load_cached_ner(text, cached)
    if loaded is not None:
        return loaded, None, True

    result = extract_chunk_entities(text)
    if not text.strip():
        return result, None, False
    return result, pack_ner(result, text), False


def precompute_ner_for_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Дополняет chunk_records полем ner там, где его ещё нет."""
    if not precompute_on_index() or not is_ner_configured():
        return records

    for rec in records:
        text = rec.get("text") or ""
        if not text.strip():
            continue
        if load_cached_ner(text, rec.get("ner")) is not None:
            continue
        result = extract_chunk_entities(text)
        rec["ner"] = pack_ner(result, text)
        print(f"[ner_cache] precompute {rec.get('id', '?')}: "
              f"{len(result.entities)} сущн., {len(result.relations)} связей")
    return records
