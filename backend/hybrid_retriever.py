"""Гибридный ретривер: структурный поиск по графу (материал/процесс/условие/
свойство/оборудование/предприятие) + разбор числовых ограничений и геопризнака
из вопроса на естественном языке, затем (опционально) LLM для причёсывания текста.

Работает полностью офлайн на синтетическом датасете — LLM используется только
для финальной формулировки ответа, если заданы YANDEX_API_KEY/YANDEX_FOLDER_ID. Без ключа
возвращается детерминированный, но содержательный ответ, собранный из графа —
демо остаётся рабочим без внешних зависимостей.
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import Any, Optional

from backend.graph_store import GraphStore
from backend.lexicon import best_match, best_matches, expand_synonyms, find_matches, name_similarity
from backend.llm_client import complete as llm_complete
from backend.schema import EntityType, RelationType
from backend.source_files import publication_source_file, source_file_meta

NEAREST_LIMIT = 5
APPROX_DISCLAIMER = (
    "Точного совпадения с запросом не найдено. Ниже — ближайшие эксперименты из графа "
    "(частичное совпадение по сущностям, числовым параметрам или формулировкам вопроса)."
)

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


def _match_entities(gs: GraphStore, text: str, etype: EntityType) -> list[dict[str, Any]]:
    """Возвращает все сущности заданного типа, достаточно хорошо совпавшие с текстом
    (не только единственную лучшую) — это нужно, чтобы вопросы вида «медным/никелевым
    штейном» матчились на ОБА варианта, а не теряли один из них."""
    return best_matches(gs.entities_by_type(etype), text)


def _match_entity(gs: GraphStore, text: str, etype: EntityType) -> Optional[dict[str, Any]]:
    return best_match(gs.entities_by_type(etype), text)


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


def _collect_publications(
    gs: GraphStore,
    detail: dict[str, Any],
    exp: dict[str, Any],
) -> list[dict[str, Any]]:
    pubs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pub in detail.get("incoming::DESCRIBES_EXPERIMENT", []):
        pub_id = pub.get("id")
        if not pub_id or pub_id in seen:
            continue
        seen.add(pub_id)
        gs_node = gs.node(pub_id)
        source_file = publication_source_file(pub, exp, detail, gs_node)
        item = {
            "id": pub_id,
            "name": str(pub.get("name") or (gs_node or {}).get("name") or pub_id),
            "source_file": source_file,
            "date": str(pub.get("date") or (gs_node or {}).get("date") or ""),
        }
        pubs.append({**item, **source_file_meta(source_file)})

    if pubs:
        return pubs

    source_file = publication_source_file({}, exp, detail, gs.node(exp["id"]))
    if source_file:
        item = {
            "id": None,
            "name": source_file.rsplit(".", 1)[0],
            "source_file": source_file,
            "date": str(exp.get("date") or detail.get("date") or ""),
        }
        return [{**item, **source_file_meta(source_file)}]

    return []


def _merge_publications(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for pub in items:
        key = pub.get("id") or f"file::{pub.get('source_file') or pub.get('name')}"
        if key not in merged:
            merged[key] = pub
    return list(merged.values())


def _normalize_source_contexts(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    return []


def _collect_relation_contexts(detail: dict[str, Any]) -> list[dict[str, Any]]:
    relation_groups = (
        "USES_MATERIAL", "USES_PROCESS", "AT_CONDITION", "MEASURES_PROPERTY",
        "PRODUCES_CONCLUSION", "ON_EQUIPMENT", "AT_FACILITY", "CONDUCTED_BY",
        "incoming::DESCRIBES_EXPERIMENT",
    )
    items: list[dict[str, Any]] = []
    for rel_type in relation_groups:
        for node in detail.get(rel_type, []):
            contexts = _normalize_source_contexts(node.get("relation_contexts"))
            if not contexts:
                continue
            items.append({
                "relation_type": rel_type.replace("incoming::", ""),
                "target_name": str(node.get("name") or node.get("id") or ""),
                "source_contexts": contexts,
            })
    return items


def _matches_neighbor(gs: GraphStore, exp_id: str, rel_type: str, name_query: str | list[str]) -> bool:
    queries = [name_query] if isinstance(name_query, str) else name_query
    for nq in queries:
        nq = nq.lower()
        for _, tgt, data in gs.g.out_edges(exp_id, data=True):
            if data.get("type") == rel_type:
                tname = str(gs.g.nodes[tgt].get("name", "")).lower()
                if nq in tname or tname in nq:
                    return True
    return False


def _matches_numeric(attrs: dict[str, Any], key: str, op: str, value: float) -> bool:
    actual = attrs.get(key)
    if actual is None:
        return False
    actual = float(actual)
    return {
        "<=": actual <= value,
        "<": actual < value,
        ">=": actual >= value,
        ">": actual > value,
        "=": actual == value,
    }.get(op, False)


def _build_search_criteria(
    materials: list[dict[str, Any]],
    processes: list[dict[str, Any]],
    condition: Optional[dict[str, Any]],
    prop: Optional[dict[str, Any]],
    equipment: Optional[dict[str, Any]],
    facility: Optional[dict[str, Any]],
    country: Optional[str],
    numeric_filters: list[tuple[str, str, float]],
    year_cutoff: Optional[str],
) -> dict[str, Any]:
    return {
        "materials": [m["name"] for m in materials],
        "processes": [p["name"] for p in processes],
        "condition": condition["name"] if condition else None,
        "prop": prop["name"] if prop else None,
        "equipment": equipment["name"] if equipment else None,
        "facility": facility["name"] if facility else None,
        "country": country,
        "numeric_filters": numeric_filters,
        "year_cutoff": year_cutoff,
    }


def _experiment_context_text(gs: GraphStore, exp_id: str, detail: dict[str, Any]) -> str:
    parts: list[str] = []
    for group in (
        "USES_MATERIAL", "USES_PROCESS", "AT_CONDITION", "MEASURES_PROPERTY",
        "PRODUCES_CONCLUSION", "ON_EQUIPMENT", "AT_FACILITY", "CONDUCTED_BY",
    ):
        for it in detail.get(group, []):
            parts.append(str(it.get("name", "")))
    for pub in detail.get("incoming::DESCRIBES_EXPERIMENT", []):
        parts.append(str(pub.get("name", "")))
    node = gs.node(exp_id) or {}
    if node.get("effect"):
        parts.append(str(node["effect"]))
    if node.get("name"):
        parts.append(str(node["name"]))
    return " ".join(p for p in parts if p.strip())


def _score_experiment(gs: GraphStore, exp_id: str, criteria: dict[str, Any], text: str) -> float:
    detail = gs.experiment_detail(exp_id)
    node = gs.node(exp_id) or {}
    score = 0.0

    dim_specs: list[tuple[Any, str, float]] = [
        (criteria["materials"], RelationType.USES_MATERIAL.value, 3.0),
        (criteria["processes"], RelationType.USES_PROCESS.value, 3.0),
        (criteria["condition"], RelationType.AT_CONDITION.value, 2.0),
        (criteria["prop"], RelationType.MEASURES_PROPERTY.value, 2.0),
        (criteria["equipment"], RelationType.ON_EQUIPMENT.value, 1.5),
        (criteria["facility"], RelationType.AT_FACILITY.value, 1.5),
    ]
    for names, rel, weight in dim_specs:
        if not names:
            continue
        if _matches_neighbor(gs, exp_id, rel, names):
            score += weight

    if criteria["country"]:
        if str(node.get("country", "")).upper() == str(criteria["country"]).upper():
            score += 1.0

    numeric_filters = criteria["numeric_filters"]
    if numeric_filters:
        if all(_matches_numeric(node, k, op, v) for k, op, v in numeric_filters):
            score += 2.0
        else:
            keys = {k for k, _, _ in numeric_filters}
            if any(node.get(k) is not None for k in keys):
                score += 0.75

    if criteria["year_cutoff"]:
        exp_date = str(node.get("date", ""))
        if exp_date and exp_date >= criteria["year_cutoff"]:
            score += 0.5

    context = _experiment_context_text(gs, exp_id, detail)
    if context.strip():
        score += name_similarity(text, context) * 5.0

    return score


def _experiments_for_entity(gs: GraphStore, entity_id: str) -> list[str]:
    exp_ids: list[str] = []
    for src, _, _ in gs.g.in_edges(entity_id, data=True):
        if gs.g.nodes[src].get("type") == EntityType.EXPERIMENT.value:
            exp_ids.append(src)
    return exp_ids


def _find_nearest_experiments(
    gs: GraphStore,
    criteria: dict[str, Any],
    text: str,
    limit: int = NEAREST_LIMIT,
) -> list[tuple[float, dict[str, Any]]]:
    all_exps = gs.entities_by_type(EntityType.EXPERIMENT)
    if not all_exps:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for exp in all_exps:
        s = _score_experiment(gs, exp["id"], criteria, text)
        if s > 0:
            scored.append((s, exp))
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        return scored[:limit]

    # Запасной путь: сущности, хоть как-то совпавшие с текстом -> связанные эксперименты.
    entity_hits: dict[str, float] = {}
    for etype in (
        EntityType.MATERIAL, EntityType.PROCESS, EntityType.CONDITION,
        EntityType.PROPERTY, EntityType.EQUIPMENT, EntityType.FACILITY,
    ):
        for match_score, entity in find_matches(gs.entities_by_type(etype), text):
            for exp_id in _experiments_for_entity(gs, entity["id"]):
                entity_hits[exp_id] = max(entity_hits.get(exp_id, 0.0), match_score)

    if entity_hits:
        by_id = {exp["id"]: exp for exp in all_exps}
        ranked = sorted(
            ((score, by_id[exp_id]) for exp_id, score in entity_hits.items() if exp_id in by_id),
            key=lambda x: x[0],
            reverse=True,
        )
        return ranked[:limit]

    text_scored: list[tuple[float, dict[str, Any]]] = []
    for exp in all_exps:
        detail = gs.experiment_detail(exp["id"])
        context = _experiment_context_text(gs, exp["id"], detail)
        ts = name_similarity(text, context) * 5.0
        if ts > 0:
            text_scored.append((ts, exp))
    text_scored.sort(key=lambda x: x[0], reverse=True)
    return text_scored[:limit]


def _summarize_experiments(
    gs: GraphStore,
    experiments: list[dict[str, Any]],
    path_nodes: set[str],
    approximate: bool = False,
    relevance_scores: Optional[dict[str, float]] = None,
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    lines: list[str] = []
    experiment_summaries: list[dict[str, Any]] = []
    conclusion_ids: list[str] = []

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
        publications = _collect_publications(gs, detail, exp)
        pub_names = pub_names or [p["name"] for p in publications]

        for group in ("USES_MATERIAL", "USES_PROCESS", "AT_CONDITION", "MEASURES_PROPERTY", "PRODUCES_CONCLUSION"):
            for it in detail.get(group, []):
                path_nodes.add(it["id"])

        source_contexts = _normalize_source_contexts(detail.get("source_contexts"))
        relation_contexts = _collect_relation_contexts(detail)

        experiment_summaries.append({
            "id": exp["id"],
            "approximate": approximate,
            "relevance_score": (relevance_scores or {}).get(exp["id"]),
            "country": str(country_tag),
            "confidence": str(confidence),
            "materials": mat_names,
            "processes": proc_names,
            "conditions": cond_names,
            "equipment": eq_names,
            "facilities": fac_names,
            "effect": str(effect or ""),
            "conclusions": [c["name"] for c in conclusions],
            "publications": publications,
            "team": team_names,
            "source_contexts": source_contexts,
            "relation_contexts": relation_contexts,
        })

        prefix = "~ " if approximate else ""
        lines.append(
            f"{prefix}[{exp['id']}] ({country_tag}, достоверность: {confidence}) "
            f"Материал: {', '.join(mat_names) or '—'}; Процесс: {', '.join(proc_names) or '—'}; "
            f"Условие: {', '.join(cond_names) or '—'}; Оборудование: {', '.join(eq_names) or '—'}; "
            f"Предприятие: {', '.join(fac_names) or '—'}. "
            f"Эффект: {effect or '—'}. "
            f"Вывод: {'; '.join(c['name'] for c in conclusions) or '—'}. "
            f"Источник: {', '.join(pub_names) or '—'}. Команда: {', '.join(team_names) or '—'}."
        )

    return lines, experiment_summaries, conclusion_ids


def hybrid_search(gs: GraphStore, question: str) -> dict[str, Any]:
    text = expand_synonyms(question)

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
    criteria = _build_search_criteria(
        materials, processes, condition, prop, equipment, facility,
        country, numeric_filters, year_cutoff,
    )

    has_anchor = bool(materials or processes or condition or prop or equipment or facility)
    if has_anchor or numeric_filters or country:
        experiments = gs.query_experiments(
            material=criteria["materials"] or None,
            process=criteria["processes"] or None,
            condition=criteria["condition"],
            prop=criteria["prop"],
            equipment=criteria["equipment"],
            facility=criteria["facility"],
            country=country,
            numeric_filters=numeric_filters,
        )
    else:
        experiments = []
    if year_cutoff:
        experiments = [e for e in experiments if str(e.get("date", "")) >= year_cutoff]

    exact_match = bool(experiments)
    approximate = False
    relevance_scores: dict[str, float] = {}

    if not experiments:
        nearest = _find_nearest_experiments(gs, criteria, text)
        if nearest:
            approximate = True
            experiments = [exp for _, exp in nearest]
            relevance_scores = {exp["id"]: score for score, exp in nearest}

    path_nodes: set[str] = set()
    for anchor in (*materials, *processes, condition, prop, equipment, facility):
        if anchor:
            path_nodes.add(anchor["id"])

    lines: list[str] = []
    experiment_summaries: list[dict[str, Any]] = []
    conclusion_ids: list[str] = []
    gaps_mentioned: list[str] = []

    if approximate:
        lines.append(APPROX_DISCLAIMER)
        combo = ", ".join(
            f"{k}={v['name']}" for k, v in
            {"материал": material, "процесс": process, "условие": condition,
             "оборудование": equipment, "предприятие": facility}.items()
            if v
        )
        if combo or numeric_filters:
            extra = f" при ограничениях {numeric_filters}" if numeric_filters else ""
            gaps_mentioned = [f"нет точного совпадения ({combo}{extra})".strip()]
        elif not has_anchor:
            gaps_mentioned = ["сущности в вопросе не распознаны — показаны ближайшие по тексту"]

    if experiments:
        exp_lines, experiment_summaries, conclusion_ids = _summarize_experiments(
            gs, experiments, path_nodes, approximate=approximate, relevance_scores=relevance_scores,
        )
        lines.extend(exp_lines)
    elif not approximate:
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

    contradictions = gs.contradictions_for(conclusion_ids) if conclusion_ids else []
    if contradictions:
        lines.append("")
        lines.append("⚠ ОБНАРУЖЕНО ПРОТИВОРЕЧИЕ В ВЫВОДАХ:")
        for c in contradictions:
            path_nodes.add(c["a"]["id"])
            path_nodes.add(c["b"]["id"])
            lines.append(f"  • «{c['a']['name']}» ПРОТИВОРЕЧИТ «{c['b']['name']}». {c.get('note', '')}")

    draft = "\n".join(lines)
    polished = _maybe_llm_polish(question, draft, approximate=approximate)
    if experiment_summaries and polished == draft:
        if approximate:
            answer = (
                f"Точного совпадения нет. Показаны {len(experiment_summaries)} ближайших "
                f"экспериментов из графа знаний."
            )
        else:
            answer = f"Найдено {len(experiment_summaries)} релевантных экспериментов в графе знаний."
    else:
        answer = polished

    all_publications = _merge_publications(
        [pub for summary in experiment_summaries for pub in summary["publications"]]
    )

    return {
        "answer": answer,
        "exact_match": exact_match,
        "experiments": experiment_summaries,
        "publications": all_publications,
        "matched_experiment_ids": [e["id"] for e in experiments],
        "path_node_ids": list(path_nodes),
        "subgraph": gs.vis_subgraph(path_nodes),
        "gaps_mentioned": gaps_mentioned,
        "contradictions": contradictions,
        "detected_entities": {
            "material": material, "process": process, "condition": condition,
            "property": prop, "equipment": equipment, "facility": facility,
            "country_filter": country, "year_cutoff": year_cutoff,
            "numeric_filters": numeric_filters,
        },
    }


def _maybe_llm_polish(question: str, draft_answer: str, approximate: bool = False) -> str:
    if not draft_answer:
        return draft_answer
    approx_note = (
        " В начале ответа явно укажи, что точного совпадения с запросом нет и показаны только "
        "ближайшие эксперименты из графа."
        if approximate
        else ""
    )
    prompt = (
        "Ты помощник-исследователь в горно-металлургической отрасли. Ниже вопрос и сырые данные "
        "из графа знаний (эксперименты, источники, выводы, возможные противоречия). Перепиши данные "
        "в связный, структурированный ответ на русском, ничего не выдумывая и не теряя фактов: "
        "материалы, процессы, числовые эффекты, источники, уровень достоверности, противоречия."
        f"{approx_note}\n\n"
        f"ВОПРОС: {question}\n\nДАННЫЕ:\n{draft_answer}\n\nОТВЕТ:"
    )
    polished = llm_complete(prompt)
    return polished or draft_answer
