"""Извлечение ключевых секций документа (аннотация/методы/результаты/
заключение) — вместо прогона LLM по всему тексту документа отдаём в
экстрактор только эти секции. Для научных статей это покрывает почти все
извлекаемые факты (материалы/процессы/числа в результатах, авторский вывод
в заключении) при заметно меньшем числе токенов, чем весь документ.

Заголовок секции определяется либо явным стилем Heading (docx), либо
эвристикой «короткая строка без завершающей пунктуации» — многие реальные
отчёты не используют встроенные стили Word для заголовков. Если ни одной
из четырёх секций не нашлось (презентации, отчёты без формальной структуры
статьи) — берём начало и конец документа как разумное приближение
аннотации/заключения, чтобы не терять документ целиком.
"""
from __future__ import annotations

import re

from backend.nlp_pipeline.ingest import TextBlock

SECTION_PATTERNS: dict[str, re.Pattern] = {
    "abstract": re.compile(r"^(аннотаци|реферат|abstract|резюме)", re.IGNORECASE),
    "methods": re.compile(r"^(метод[аы]?( и материал)?|материал[аы] и метод|methodology|methods)", re.IGNORECASE),
    "results": re.compile(r"^(результат|results)", re.IGNORECASE),
    "conclusion": re.compile(r"^(заключени|вывод|conclusion|discussion|итог)", re.IGNORECASE),
}

SECTION_ORDER = ("abstract", "methods", "results", "conclusion")
_MAX_HEADING_LEN = 100


def _is_heading_like(b: TextBlock) -> bool:
    if b.kind == "heading":
        return True
    t = b.text.strip()
    return bool(t) and len(t) < _MAX_HEADING_LEN and not t.endswith((".", ":", ";", ","))


def extract_key_sections(blocks: list[TextBlock], max_chars_per_section: int = 6000) -> dict[str, list[TextBlock]]:
    sections: dict[str, list[TextBlock]] = {}
    section_chars: dict[str, int] = {}
    current: str | None = None

    for b in blocks:
        if b.kind == "table":
            if current and section_chars.get(current, 0) < max_chars_per_section:
                sections.setdefault(current, []).append(b)
                section_chars[current] = section_chars.get(current, 0) + len(b.text)
            continue

        if _is_heading_like(b):
            matched = next((key for key, pat in SECTION_PATTERNS.items() if pat.match(b.text.strip())), None)
            if matched:
                current = matched
                sections.setdefault(current, [])
                section_chars.setdefault(current, 0)
                continue
            current = None  # любой другой заголовок закрывает текущую секцию
            continue

        if current and section_chars.get(current, 0) < max_chars_per_section:
            sections.setdefault(current, []).append(b)
            section_chars[current] = section_chars.get(current, 0) + len(b.text)

    if not sections:
        # Нет формальной структуры статьи (презентация, отчёт без разделов) —
        # начало и конец документа как приближение аннотации/заключения.
        head, tail = blocks[:3], blocks[-3:]
        if head:
            sections["abstract"] = head
        if tail:
            sections["conclusion"] = tail

    return sections
