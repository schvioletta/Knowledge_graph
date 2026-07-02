"""Гибридный ретривер: структурный поиск по графу (материал/процесс/условие/
свойство/оборудование/предприятие) + разбор числовых ограничений и геопризнака
из вопроса на естественном языке, затем (опционально) LLM для причёсывания текста.

Работает полностью офлайн на синтетическом датасете — LLM используется только
для финальной формулировки ответа, если задан GIGACHAT_API_KEY. Без ключа
возвращается детерминированный, но содержательный ответ, собранный из графа —
демо остаётся рабочим без внешних зависимостей.
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import Any, Optional

from backend.graph_store import GraphStore
from backend.schema import EntityType

_STOPWORDS = {
    "что", "уже", "делали", "по", "при", "какой", "был", "какая", "какие", "как", "и",
    "с", "в", "во", "для", "а", "если", "на", "или", "за", "все", "the", "what", "was",
    "did", "for", "are", "is",
}

# Синонимы RU/EN и профессиональный жаргон -> канонический фрагмент имени сущности в графе.
SYNONYMS = {
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
}

# Термины -> ключ числового атрибута на узле Experiment.
ATTR_TERMS: list[tuple[str, str]] = [
    (r"сульфат|sulfate", "sulfate_mg_l"),
    (r"хлорид|chloride", "chloride_mg_l"),
    (r"\bca\b|кальц", "calcium_mg_l"),
    (r"\bmg\b|магни", "magnesium_mg_l"),
    (r"\bna\b|натри", "sodium_mg_l"),
    (r"сухо\w* остат\w*|dry residue", "dry_residue_mg_l"),
    (r"циркуляц\w*|catholyte flow|flow rate", "catholyte_flow_rate_m3_h"),
    (r"плотност\w* ток|current density", "current_density_a_m2"),
    (r"\bau\b|золот", "au_distribution_pct"),
    (r"\bag\b|серебр", "ag_distribution_pct"),
    (r"мпг|pgm|платин", "pgm_distribution_pct"),
    (r"извлечени\w*|extraction", "extraction_rate_pct"),
    (r"капзатрат\w*|capex", "capex_musd"),
    (r"опекс\w*|opex", "opex_musd_year"),
    (r"производительност\w*|capacity", "capacity_m3_day"),
    (r"глубин\w*|depth", "injection_depth_m"),
]

_ION_KEYS = {"sulfate_mg_l", "chloride_mg_l", "calcium_mg_l", "magnesium_mg_l", "sodium_mg_l"}

_NUM = r"\d+(?:[.,]\d+)?"
_RANGE_RE = re.compile(rf"({_NUM})\s*(?:-|–|—)\s*({_NUM})")
_LE_RE = re.compile(rf"(?:≤|<=|не\s+более|не\s+превыша\w*|максимум)\s*({_NUM})")
_GE_RE = re.compile(rf"(?:≥|>=|не\s+менее|минимум|от)\s*({_NUM})")
_PLAIN_NUM_RE = re.compile(rf"({_NUM})")


def _expand_synonyms(text: str) -> str:
    low = text.lower()
    extra = []
    for alias, canonical in SYNONYMS.items():
        if alias in low:
            extra.append(canonical)
    if extra:
        return text + " " + " ".join(extra)
    return text


def _extract_candidates(text: str) -> list[str]:
    words = re.findall(r"[\wА-Яа-яЁё\-]+", text)
    return [w for w in words if w.lower() not in _STOPWORDS and len(w) > 1]


def _word_match(a: str, b: str) -> bool:
    """Грубое сопоставление словоформ рус. языка без полноценного стемминга:
    точное совпадение либо достаточно длинный общий префикс относительно длины
    слова (покрывает падежные/родовые окончания: руда/руды, никелевая/никелевой,
    электроэкстракция/электроэкстракции)."""
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


def _match_entities(gs: GraphStore, text: str, etype: EntityType) -> list[dict[str, Any]]:
    """Возвращает все сущности заданного типа, достаточно хорошо совпавшие с текстом
    (не только единственную лучшую) — это нужно, чтобы вопросы вида «медным/никелевым
    штейном» матчились на ОБА варианта, а не теряли один из них."""
    candidates = gs.entities_by_type(etype)
    low = text.lower()
    tokens = [t.lower() for t in _extract_candidates(text)]
    scored: list[tuple[float, dict[str, Any]]] = []
    for c in candidates:
        name = str(c["name"]).lower()
        if name in low:
            score = 100.0 + len(name)
        else:
            name_words = [w for w in re.findall(r"[\wа-яёa-z\-]+", name) if len(w) > 2]
            if not name_words:
                continue
            overlap = sum(1 for w in name_words if any(_word_match(w, t) for t in tokens))
            ratio = overlap / len(name_words)
            if overlap == 0 or ratio < 0.5:
                continue
            score = overlap * 10 + ratio * 5
        scored.append((score, c))
    if not scored:
        return []
    scored.sort(key=lambda x: x[0], reverse=True)
    top_score = scored[0][0]
    return [c for score, c in scored if score >= 0.7 * top_score][:3]


def _match_entity(gs: GraphStore, text: str, etype: EntityType) -> Optional[dict[str, Any]]:
    matches = _match_entities(gs, text, etype)
    return matches[0] if matches else None


def _detect_country(text: str) -> Optional[str]:
    low = text.lower()
    ru = bool(re.search(r"росси|отечественн|рф\b", low))
    intl = bool(re.search(r"рубеж|зарубежн|мировой|мировая практика|foreign|international", low))
    if ru and intl:
        return None  # сравнение — показываем обе стороны, не фильтруем
    if ru:
        return "RU"
    if intl:
        return "INTL"
    return None


def _detect_year_cutoff(text: str) -> Optional[str]:
    m = re.search(r"последн\w*\s+(\d+)\s+лет", text.lower())
    if not m:
        return None
    years = int(m.group(1))
    cutoff = date.today() - timedelta(days=365 * years)
    return cutoff.isoformat()


def _extract_numeric_filters(text: str) -> list[tuple[str, str, float]]:
    low = text.lower()
    dedicated: dict[str, list[tuple[str, float]]] = {}
    shared_range: Optional[tuple[float, float]] = None
    shared_le: Optional[float] = None

    keyword_spans = []
    for pattern, key in ATTR_TERMS:
        for m in re.finditer(pattern, low):
            keyword_spans.append((m.start(), m.end(), key))
    keyword_spans.sort()

    for i, (start, end, key) in enumerate(keyword_spans):
        window_end = keyword_spans[i + 1][0] if i + 1 < len(keyword_spans) else min(len(low), end + 30)
        window = low[end:window_end]
        le = _LE_RE.search(window)
        ge = _GE_RE.search(window)
        rng = _RANGE_RE.search(window)
        if le:
            dedicated.setdefault(key, []).append(("<=", float(le.group(1).replace(",", "."))))
        elif ge:
            dedicated.setdefault(key, []).append((">=", float(ge.group(1).replace(",", "."))))
        elif rng:
            dedicated.setdefault(key, []).append((">=", float(rng.group(1).replace(",", "."))))
            dedicated.setdefault(key, []).append(("<=", float(rng.group(2).replace(",", "."))))
        else:
            plain = _PLAIN_NUM_RE.search(window)
            if plain:
                dedicated.setdefault(key, []).append(("<=", float(plain.group(1).replace(",", "."))))

    # общий диапазон/порог в хвосте фразы, не привязанный к конкретному ключу —
    # применяем ко всем упомянутым ионам без собственного числа (пример: "по 200-300 мг/л")
    tail_range = None
    for m in _RANGE_RE.finditer(low):
        tail_range = (float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")))
    ion_keys_mentioned = {key for _, _, key in keyword_spans if key in _ION_KEYS}
    if tail_range:
        for key in ion_keys_mentioned:
            if key not in dedicated:
                dedicated[key] = [(">=", tail_range[0]), ("<=", tail_range[1])]

    filters: list[tuple[str, str, float]] = []
    for key, ops in dedicated.items():
        for op, val in ops:
            filters.append((key, op, val))
    return filters


def hybrid_search(gs: GraphStore, question: str) -> dict[str, Any]:
    text = _expand_synonyms(question)

    materials = _match_entities(gs, text, EntityType.MATERIAL)
    processes = _match_entities(gs, text, EntityType.PROCESS)
    condition = _match_entity(gs, text, EntityType.CONDITION)
    prop = _match_entity(gs, text, EntityType.PROPERTY)
    equipment = _match_entity(gs, text, EntityType.EQUIPMENT)
    facility = _match_entity(gs, text, EntityType.FACILITY)
    material = materials[0] if materials else None
    process = processes[0] if processes else None

    country = _detect_country(text)
    year_cutoff = _detect_year_cutoff(text)
    numeric_filters = _extract_numeric_filters(text)

    experiments = gs.query_experiments(
        material=[m["name"] for m in materials] if materials else None,
        process=[p["name"] for p in processes] if processes else None,
        condition=condition["name"] if condition else None,
        prop=prop["name"] if prop else None,
        equipment=equipment["name"] if equipment else None,
        facility=facility["name"] if facility else None,
        country=country,
        numeric_filters=numeric_filters,
    )
    if year_cutoff:
        experiments = [e for e in experiments if str(e.get("date", "")) >= year_cutoff]

    path_nodes: set[str] = set()
    for anchor in (*materials, *processes, condition, prop, equipment, facility):
        if anchor:
            path_nodes.add(anchor["id"])

    lines: list[str] = []
    conclusion_ids: list[str] = []
    gaps_mentioned: list[str] = []

    if not experiments:
        combo = ", ".join(
            f"{k}={v['name']}" for k, v in
            {"материал": material, "процесс": process, "условие": condition,
             "оборудование": equipment, "предприятие": facility}.items()
            if v
        )
        if combo or numeric_filters:
            extra = f" при ограничениях {numeric_filters}" if numeric_filters else ""
            lines.append(
                f"По запрошенной комбинации ({combo}){extra} экспериментов и публикаций в базе не найдено — "
                f"это похоже на пробел в данных, требующий отдельного исследования или запроса внешних источников."
            )
            gaps_mentioned = [combo or "числовые ограничения без совпадений"]
        else:
            lines.append(
                "Не удалось распознать материал/процесс/условие/свойство в вопросе. "
                "Попробуйте конкретнее, например: «Какие методы обессоливания подходят при сульфатах "
                "200-300 мг/л и требуемом сухом остатке ≤1000 мг/дм³?»"
            )
    else:
        for exp in experiments:
            detail = gs.experiment_detail(exp["id"])
            path_nodes.add(exp["id"])
            mat_names = [m["name"] for m in detail.get("USES_MATERIAL", [])]
            proc_names = [p["name"] for p in detail.get("USES_PROCESS", [])]
            cond_names = [c["name"] for c in detail.get("AT_CONDITION", [])]
            eq_names = [e["name"] for e in detail.get("ON_EQUIPMENT", [])]
            fac_names = [f["name"] for f in detail.get("AT_FACILITY", [])]
            team_names = [t["name"] for t in detail.get("CONDUCTED_BY", [])]
            conclusions = detail.get("PRODUCES_CONCLUSION", [])
            conclusion_ids.extend(c["id"] for c in conclusions)
            effect = exp.get("attrs", {}).get("effect", detail.get("effect", ""))
            country_tag = exp.get("attrs", {}).get("country", detail.get("country", "?"))
            confidence = exp.get("attrs", {}).get("confidence", detail.get("confidence", "?"))
            pub_names = [p["name"] for p in detail.get("incoming::DESCRIBES_EXPERIMENT", [])]

            for group in ("USES_MATERIAL", "USES_PROCESS", "AT_CONDITION", "MEASURES_PROPERTY", "PRODUCES_CONCLUSION"):
                for it in detail.get(group, []):
                    path_nodes.add(it["id"])

            lines.append(
                f"[{exp['id']}] ({country_tag}, достоверность: {confidence}) "
                f"Материал: {', '.join(mat_names) or '—'}; Процесс: {', '.join(proc_names) or '—'}; "
                f"Условие: {', '.join(cond_names) or '—'}; Оборудование: {', '.join(eq_names) or '—'}; "
                f"Предприятие: {', '.join(fac_names) or '—'}. "
                f"Эффект: {effect or '—'}. "
                f"Вывод: {'; '.join(c['name'] for c in conclusions) or '—'}. "
                f"Источник: {', '.join(pub_names) or '—'}. Команда: {', '.join(team_names) or '—'}."
            )

    contradictions = gs.contradictions_for(conclusion_ids) if conclusion_ids else []
    if contradictions:
        lines.append("")
        lines.append("⚠ ОБНАРУЖЕНО ПРОТИВОРЕЧИЕ В ВЫВОДАХ:")
        for c in contradictions:
            path_nodes.add(c["a"]["id"])
            path_nodes.add(c["b"]["id"])
            lines.append(f"  • «{c['a']['name']}» ПРОТИВОРЕЧИТ «{c['b']['name']}». {c.get('note', '')}")

    answer = "\n".join(lines)
    answer = _maybe_llm_polish(question, answer)

    subgraph = gs.g.subgraph(path_nodes)
    return {
        "answer": answer,
        "matched_experiment_ids": [e["id"] for e in experiments],
        "path_node_ids": list(path_nodes),
        "subgraph": gs.to_vis_json(subgraph),
        "gaps_mentioned": gaps_mentioned,
        "contradictions": contradictions,
        "detected_entities": {
            "material": material, "process": process, "condition": condition,
            "property": prop, "equipment": equipment, "facility": facility,
            "country_filter": country, "year_cutoff": year_cutoff,
            "numeric_filters": numeric_filters,
        },
    }


def _maybe_llm_polish(question: str, draft_answer: str) -> str:
    api_key = os.getenv("GIGACHAT_API_KEY")
    if not api_key or not draft_answer:
        return draft_answer
    try:
        from langchain_community.chat_models.gigachat import GigaChat

        llm = GigaChat(credentials=api_key, verify_ssl_certs=False, temperature=0)
        prompt = (
            "Ты помощник-исследователь в горно-металлургической отрасли. Ниже вопрос и сырые данные "
            "из графа знаний (эксперименты, источники, выводы, возможные противоречия). Перепиши данные "
            "в связный, структурированный ответ на русском, ничего не выдумывая и не теряя фактов: "
            "материалы, процессы, числовые эффекты, источники, уровень достоверности, противоречия.\n\n"
            f"ВОПРОС: {question}\n\nДАННЫЕ:\n{draft_answer}\n\nОТВЕТ:"
        )
        result = llm.invoke(prompt)
        return getattr(result, "content", None) or draft_answer
    except Exception:
        return draft_answer
