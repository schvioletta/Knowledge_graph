"""Расширение поискового запроса: LLM генерирует перефразировки без потери смысла."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from backend.rag.query_expand_llm import complete_query_expand, is_query_expand_available

_SYSTEM_PROMPT = """Ты помогаешь улучшить поиск по техническим документам (горная металлургия, R&D).
Перефразируй вопрос пользователя 2–3 альтернативными формулировками на том же языке,
что и исходный вопрос. Сохрани все числа, единицы измерения, химические формулы и
смысл вопроса — не добавляй новых фактов и не сужай/не расширяй тему.

Верни СТРОГО JSON-массив строк без markdown, например:
["формулировка 1", "формулировка 2"]
"""

_DEFAULT_MAX = 3


def _extract_json_array(raw: str) -> list[Any] | None:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        return None


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _skip_query_expand() -> bool:
    return os.getenv("RAG_SKIP_QUERY_EXPAND", "").strip().lower() in ("1", "true", "yes", "on")


def expand_query(question: str, max_variants: int = _DEFAULT_MAX) -> dict[str, Any]:
    """Возвращает {original, expansions, all_queries, expanded, expand_llm}."""
    original = question.strip()
    if not original:
        return {"original": "", "expansions": [], "all_queries": [], "expanded": False}

    expansions: list[str] = []
    expand_llm = None
    if not _skip_query_expand() and is_query_expand_available():
        prompt = f"Исходный вопрос:\n{original}\n\nДай {max_variants} перефразировки."
        raw, source = complete_query_expand(prompt, system=_SYSTEM_PROMPT, temperature=0.2)
        if raw:
            parsed = _extract_json_array(raw)
            if parsed:
                seen = {_normalize(original)}
                for item in parsed:
                    if not isinstance(item, str):
                        continue
                    text = item.strip()
                    key = _normalize(text)
                    if text and key not in seen and len(expansions) < max_variants:
                        expansions.append(text)
                        seen.add(key)
                if expansions:
                    expand_llm = source

    all_queries = [original] + expansions
    return {
        "original": original,
        "expansions": expansions,
        "all_queries": all_queries,
        "expanded": len(expansions) > 0,
        "expand_llm": expand_llm,
    }
