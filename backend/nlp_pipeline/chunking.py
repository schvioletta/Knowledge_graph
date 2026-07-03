"""Этап 2: определение языка на уровне абзаца + смысловой чанкинг.

Язык определяется по каждому текстовому блоку отдельно (не по всему документу),
т.к. в русских отчётах по горно-металлургии часто встречаются английские
аббревиатуры/цитаты и наоборот (см. журнал «Цветные металлы» — русские статьи
с англоязычной аннотацией и списком авторов). Если установлен `langdetect` —
используется он (точнее на коротких фрагментах), иначе — быстрый эвристический
детектор по доле кириллических символов (без тяжёлых зависимостей).

Чанкинг — по смысловым блокам (абзац/группа абзацев, таблица целиком), а не по
фиксированному числу токенов: это важно, чтобы факт вида «Материал X при
Процессе Y дал Z» не был разорван границей чанка на две части для LLM-экстрактора.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.nlp_pipeline.ingest import TextBlock

try:
    from langdetect import detect as _langdetect_detect
    from langdetect import LangDetectException
    _HAS_LANGDETECT = True
except ImportError:
    _HAS_LANGDETECT = False


def detect_language(text: str) -> str:
    """Возвращает 'ru', 'en' или 'mixed'/'other'. langdetect используется, если
    доступен и текст достаточно длинный; иначе — эвристика по доле кириллицы."""
    sample = text.strip()
    if not sample:
        return "unknown"
    if _HAS_LANGDETECT and len(sample) >= 20:
        try:
            lang = _langdetect_detect(sample)
            if lang in ("ru", "en"):
                return lang
        except LangDetectException:
            pass

    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", sample)
    if not letters:
        return "other"
    cyrillic = sum(1 for c in letters if re.match(r"[А-Яа-яЁё]", c))
    ratio = cyrillic / len(letters)
    if ratio > 0.7:
        return "ru"
    if ratio < 0.15:
        return "en"
    return "mixed"


@dataclass
class Chunk:
    text: str
    kind: str  # "paragraph" | "table"
    language: str
    locations: list[str]
    meta: dict


def chunk_blocks(blocks: list[TextBlock], max_chars: int = 2200) -> list[Chunk]:
    """Склеивает соседние текстовые блоки в чанки до max_chars, не разрывая таблицы
    и не смешивая блоки разного детектированного языка в один чанк (чтобы факты
    на разных языках не перемешивались перед LLM-экстракцией)."""
    chunks: list[Chunk] = []
    buf_blocks: list[TextBlock] = []
    buf_lang: str | None = None
    buf_len = 0

    def flush():
        nonlocal buf_blocks, buf_lang, buf_len
        if buf_blocks:
            text = "\n\n".join(f"[{b.location}] {b.text}" for b in buf_blocks)
            chunks.append(Chunk(
                text=text, kind="paragraph", language=buf_lang or "unknown",
                locations=[b.location for b in buf_blocks], meta={},
            ))
        buf_blocks, buf_lang, buf_len = [], None, 0

    for b in blocks:
        if b.kind == "table":
            flush()
            chunks.append(Chunk(
                text=f"[{b.location}] {b.text}", kind="table",
                language=detect_language(b.text), locations=[b.location], meta=b.meta,
            ))
            continue

        lang = detect_language(b.text)
        piece_len = len(b.text) + len(b.location) + 4
        lang_changed = buf_lang is not None and lang != "mixed" and buf_lang != "mixed" and lang != buf_lang
        if lang_changed or buf_len + piece_len > max_chars:
            flush()
        buf_blocks.append(b)
        buf_lang = lang if buf_lang in (None, "mixed") else buf_lang
        buf_len += piece_len

    flush()
    return chunks
