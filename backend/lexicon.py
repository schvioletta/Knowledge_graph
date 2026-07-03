"""Общий словарь терминов и грубая обработка русской морфологии.

Используется в обе стороны, как и должно быть в согласованной системе:
- backend/hybrid_retriever.py — сопоставление сущностей при поиске по графу;
- backend/nlp_pipeline/resolve.py — entity resolution при извлечении из документов,
  чтобы «Электроэкстракция никеля» из нового документа не разъехалась с уже
  существующим узлом «электроэкстракции никеля» на два разных узла графа.
"""
from __future__ import annotations

import re
from typing import Any, Optional

STOPWORDS = {
    "что", "уже", "делали", "по", "при", "какой", "был", "какая", "какие", "как", "и",
    "с", "в", "во", "для", "а", "если", "на", "или", "за", "все", "the", "what", "was",
    "did", "for", "are", "is",
}

# Синонимы RU/EN и профессиональный жаргон -> канонический фрагмент имени сущности в графе.
SYNONYMS: dict[str, str] = {
    "electrowinning": "электроэкстракция",
    "electrowinning of nickel": "электроэкстракция никеля",
    "catholyte": "католит",
    "catholyte circulation": "циркуляции католита",
    "flash smelting": "взвешенной плавки",
    "fluidized bed furnace": "печь взвешенной плавки",
    "пвп": "печь взвешенной плавки",
    "heap leaching": "кучное выщелачивание",
    "deep well injection": "закачка в глубокие горизонты",
    "deep injection": "закачка в глубокие горизонты",
    "matte": "штейн",
    "slag": "шлак",
    "pgm": "мпг",
    "reverse osmosis": "обратный осмос",
    "ion exchange": "ионный обмен",
    "electrodialysis": "электродиализ",
    "dry residue": "сухой остаток",
    "desalination": "обессоливани",
    "overcoring": "полной разгрузки керна",
    "sodium antimonate": "антимонат натрия",
}


def expand_synonyms(text: str) -> str:
    low = text.lower()
    extra = [canonical for alias, canonical in SYNONYMS.items() if alias in low]
    return f"{text} {' '.join(extra)}" if extra else text


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[\wА-Яа-яЁё\-]+", text)
    return [w for w in words if w.lower() not in STOPWORDS and len(w) > 1]


def word_match(a: str, b: str) -> bool:
    """Точное совпадение либо достаточно длинный общий префикс относительно длины
    слова — покрывает падежные/родовые окончания рус. языка (руда/руды,
    никелевая/никелевой, электроэкстракция/электроэкстракции) без полноценного
    стемминга/морфоанализатора."""
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    lcp = 0
    for x, y in zip(a, b):
        if x != y:
            break
        lcp += 1
    threshold = max(3, int(0.6 * min(len(a), len(b))))
    return lcp >= threshold


def name_similarity(name_a: str, name_b: str) -> float:
    """Доля слов из name_a, для которых нашлось совпадение (word_match) в name_b.
    Симметризуется вызывающим кодом при необходимости."""
    words_a = [w for w in re.findall(r"[\wа-яёa-z\-]+", name_a.lower()) if len(w) > 2]
    words_b = [w for w in re.findall(r"[\wа-яёa-z\-]+", name_b.lower()) if len(w) > 2]
    if not words_a or not words_b:
        return 1.0 if name_a.strip().lower() == name_b.strip().lower() else 0.0
    overlap = sum(1 for w in words_a if any(word_match(w, t) for t in words_b))
    return overlap / len(words_a)


def find_matches(candidates: list[dict[str, Any]], text: str) -> list[tuple[float, dict[str, Any]]]:
    """Ищет среди candidates (список узлов графа с полем "name") те, что достаточно
    хорошо совпадают с text. Возвращает (score, candidate) отсортированные по score."""
    low = text.lower()
    tokens = [t.lower() for t in tokenize(text)]
    scored: list[tuple[float, dict[str, Any]]] = []
    for c in candidates:
        name = str(c["name"]).lower()
        if name in low:
            score = 100.0 + len(name)
        else:
            name_words = [w for w in re.findall(r"[\wа-яёa-z\-]+", name) if len(w) > 2]
            if not name_words:
                continue
            overlap = sum(1 for w in name_words if any(word_match(w, t) for t in tokens))
            ratio = overlap / len(name_words)
            if overlap == 0 or ratio < 0.5:
                continue
            score = overlap * 10 + ratio * 5
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def best_matches(candidates: list[dict[str, Any]], text: str, top_ratio: float = 0.7, limit: int = 3) -> list[dict[str, Any]]:
    scored = find_matches(candidates, text)
    if not scored:
        return []
    top_score = scored[0][0]
    return [c for score, c in scored if score >= top_ratio * top_score][:limit]


def best_match(candidates: list[dict[str, Any]], text: str) -> Optional[dict[str, Any]]:
    matches = best_matches(candidates, text)
    return matches[0] if matches else None
