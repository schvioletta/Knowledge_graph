"""Лексический буст поверх векторного поиска (пункт «hybrid-lite»).

Зачем: эмбеддинг-модель (multilingual MiniLM) плохо различает ровно то, чего в
горно-металлургических текстах много и что критично не перепутать — точные числа
с единицами (≤300 мг/л vs ≤200 мг/л), химические формулы (SO₂, Pt, Pd), аббревиатуры
и коды (ПВП, МПГ, КГМК, Rutrol AD 171). Для таких токенов важно не «похоже по
смыслу», а буквальное совпадение. Поэтому после векторного отбора мы не меняем сам
retrieval, а лишь ПЕРЕРАНЖИРУЕМ кандидатов: чанк, где встретился нужный код/число/
формула из запроса, поднимается выше среди уже семантически релевантных.

Две принципиально разные природы токенов — две разные стратегии совпадения:
  • жёсткие токены (числа, формулы, коды, аббревиатуры) НЕ склоняются — им нужна
    точная сверка после нормализации (юникод-подстрочные ₂→2, регистр, пробелы).
    Лемматизация тут не нужна и даже вредна (разобрала бы «Pt» как слово, «испортила»
    бы код);
  • обычные слова (никель/никеля, шлак/шлака) склоняются — им нужно морфологическое
    совпадение. Берём уже существующую в проекте эвристику word_match из lexicon.py
    (совпадение по общему префиксу), а не тащим тяжёлый морфоанализатор — так же, как
    это работает в графовом поиске и entity resolution (согласованность системы).

Отчёт по вектору (`score` у цитаты) сознательно НЕ меняем — он остаётся косинусным
сходством, чтобы калибровка confidence (пороги 0.60/0.45) не поехала. Буст влияет
только на ПОРЯДОК внутри пула кандидатов, уже прошедших семантический порог.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from backend.lexicon import STOPWORDS, word_match

# Вес лексического совпадения при переранжировании: итог = cos + WEIGHT * lex,
# где lex ∈ [0,1]. Умеренный по умолчанию — буст двигает порядок, но не
# перебивает сильную семантику полностью. Настраивается через .env.
BOOST_WEIGHT = float(os.getenv("RAG_LEXICAL_BOOST_WEIGHT", "0.15"))
# Во сколько раз шире top_k берём пул кандидатов на переранжирование: чанк с точным
# кодом/числом, оказавшийся, скажем, на 12-м месте по вектору, должен иметь шанс
# подняться в финальный top_k. Только среди прошедших семантический порог min_score.
POOL_MULT = int(os.getenv("RAG_LEXICAL_POOL_MULT", "4"))

# Единицы измерения, встречающиеся в домене — чтобы «300 мг/л» ловилось как один
# жёсткий токен «число+единица», а не как голое «300» (которое шумит).
_UNIT = (
    r"мг/дм³|мг/дм3|мг/л|г/дм³|г/дм3|г/л|м³/ч|м3/ч|м³/сут|м3/сут|т/сут|т/год|"
    r"а/м²|а/м2|°c|°с|мпа|кпа|ppm|mg/l|%|мкм|нм|мм|см|км|кв|мвт|квт"
)
_NUM = r"\d+(?:[.,]\d+)?"

# Химические символы/формулы, релевантные домену (Pt/Pd/МПГ, никель, медь, газы).
_FORMULA = (
    r"so₂|so2|co₂|co2|h₂so₄|h2so4|no[x₂2]?|caco₃|caco3|"
    r"\bpt\b|\bpd\b|\brh\b|\bir\b|\bos\b|\bru\b|\bau\b|\bag\b|\bni\b|\bcu\b|"
    r"\bca\b|\bmg\b|\bna\b|\bfe\b|\bco\b|\bpb\b|\bzn\b|\bs\b"
)

_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789" "0123456789")

# Порядок важен: сначала число+единица (составной токен), потом формулы, потом
# аббревиатуры/коды, иначе «300 мг/л» разобьётся на «300» отдельно.
_HARD_PATTERNS = [
    re.compile(rf"{_NUM}\s*(?:{_UNIT})", re.IGNORECASE),         # 300 мг/л, 51%
    re.compile(_FORMULA, re.IGNORECASE),                          # SO₂, Pt, Ni
    re.compile(r"\b(?=\w*\d)(?=\w*[a-zа-яё])[\w\-]{2,}\b", re.IGNORECASE),  # коды: AD171, R-171
    re.compile(r"\b[А-ЯA-Z]{2,}\b"),                              # аббревиатуры: ПВП, МПГ, CAPEX
    re.compile(rf"\b\d{{3,}}\b"),                                 # крупные числа: 1000, 2022
]


def _normalize(text: str) -> str:
    return text.translate(_SUBSCRIPTS).lower()


@dataclass
class QuerySignals:
    # Жёсткие токены: (нормализованный текст, скомпилированный regex с гибким пробелом).
    hard: list[tuple[str, re.Pattern]] = field(default_factory=list)
    # Обычные слова для морфологического совпадения.
    terms: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.hard and not self.terms


def extract_query_signals(queries: list[str]) -> QuerySignals:
    """Достаёт из формулировок запроса жёсткие токены и обычные слова (без дублей)."""
    hard_seen: set[str] = set()
    hard: list[tuple[str, re.Pattern]] = []
    hard_spans: list[str] = []

    for q in queries:
        norm = _normalize(q)
        for pat in _HARD_PATTERNS:
            for m in pat.finditer(norm):
                tok = m.group(0).strip()
                key = re.sub(r"\s+", "", tok)
                if len(key) < 2 or key in hard_seen:
                    continue
                hard_seen.add(key)
                # Гибкий пробел: «300 мг/л» ловит и «300мг/л» в тексте чанка.
                flexible = re.sub(r"\s+", r"\\s*", re.escape(tok))
                hard.append((tok, re.compile(flexible, re.IGNORECASE)))
                hard_spans.append(tok)

    # Обычные слова: то, что не является частью жёстких токенов, не стоп-слово,
    # длиннее 3 символов (короткие морфологически матчить бессмысленно).
    joined_hard = " ".join(hard_spans)
    term_seen: set[str] = set()
    terms: list[str] = []
    for q in queries:
        for w in re.findall(r"[А-Яа-яЁёA-Za-z\-]+", q.lower()):
            if len(w) <= 3 or w in STOPWORDS or w in term_seen:
                continue
            if any(ch.isdigit() for ch in w) or w in joined_hard.lower():
                continue
            term_seen.add(w)
            terms.append(w)

    return QuerySignals(hard=hard, terms=terms)


def lexical_score(signals: QuerySignals, chunk_text: str) -> float:
    """Доля сигналов запроса, встреченных в чанке, ∈ [0,1]. Жёсткие токены весят
    больше обычных слов (0.7/0.3) — это и есть смысл буста: точное число/код важнее
    совпадения по обычному слову, которое и так неплохо ловит вектор."""
    if signals.empty:
        return 0.0

    norm = _normalize(chunk_text)
    hard_frac = 0.0
    if signals.hard:
        matched = sum(1 for _, pat in signals.hard if pat.search(norm))
        hard_frac = matched / len(signals.hard)

    term_frac = 0.0
    if signals.terms:
        chunk_words = re.findall(r"[а-яёa-z\-]+", norm)
        matched = sum(1 for t in signals.terms if any(word_match(t, cw) for cw in chunk_words))
        term_frac = matched / len(signals.terms)

    if signals.hard and signals.terms:
        return 0.7 * hard_frac + 0.3 * term_frac
    return hard_frac or term_frac
