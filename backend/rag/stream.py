"""Потоковый (SSE) RAG-ответ: те же этапы, что и answer_question, но каждый
шаг поиска/анализа отдаётся клиенту в реальном времени как отдельное событие
«thinking», а финальный ответ LLM стримится по мере генерации.

Событийная модель (каждое — dict, сериализуется в `data: {...}\n\n`):
  {"type": "thinking", "stage": "...", "text": "...", ...доп. поля}
  {"type": "answer_delta", "text": "<кусок ответа>"}
  {"type": "done", "result": {<полный ответ, как у /api/rag/ask>}}
  {"type": "error", "text": "..."}

Порядок этапов совпадает с непотоковым /api/rag/ask (расширение запроса →
подключение документов → отбор фрагментов → извлечение сущностей → синтез),
чтобы «ход рассуждений» отражал реальный конвейер, а не бутафорию. Финальное
событие done несёт ровно тот же объект, что вернул бы answer_question (+ поля
расширения/подключения), поэтому фронт переиспользует всю существующую логику
(цитаты, граф из фрагментов, история) без разветвления.
"""
from __future__ import annotations

from typing import Any, Iterator

from backend.llm_client import complete_stream, is_configured as llm_configured
from backend.rag.chunk_graph import (
    add_external_sources,
    build_graph_from_hits,
    build_internal_graph,
    finalize_graph,
)
from backend.rag.external_search import search_external
from backend.rag.qa import (
    _NOT_FOUND_ANSWER,
    build_citations_and_context,
    build_external_context,
    build_prompt,
    confidence_from_citations,
    fallback_answer,
    highlight_entities_from_graph,
)
from backend.rag.store import Neo4jDocumentStore

_TYPE_LABELS = {
    "material": "материалы", "process": "процессы", "equipment": "оборудование",
    "condition": "условия", "facility": "предприятия", "property": "свойства",
    "experiment": "эксперименты", "expert": "эксперты", "conclusion": "выводы",
}


def _external_summary(external: dict[str, Any]) -> str:
    """Человекочитаемый итог внешнего поиска для «хода рассуждений»."""
    if not external.get("enabled"):
        return "Внешний поиск отключён."
    keywords = external.get("keywords") or []
    scholar = external.get("scholar") or []
    patents = external.get("patents") or []
    if not scholar and not patents:
        msg = external.get("message") or "Внешние источники не найдены."
        kw = f" Ключевые слова: {', '.join(keywords)}." if keywords else ""
        return f"{msg}.{kw}" if not msg.endswith(".") else f"{msg}{kw}"
    kw = ", ".join(keywords) if keywords else "—"
    return (f"По ключевым словам ({kw}) найдено: публикаций — {len(scholar)}, "
            f"патентов — {len(patents)}.")


def _entities_summary(entities: list[dict[str, Any]]) -> str:
    by_type: dict[str, list[str]] = {}
    for e in entities:
        by_type.setdefault(e["type"], []).append(e["name"])
    parts = []
    for etype, names in by_type.items():
        label = _TYPE_LABELS.get(etype, etype)
        shown = ", ".join(names[:6]) + ("…" if len(names) > 6 else "")
        parts.append(f"{label}: {shown}")
    return "; ".join(parts)


def stream_answer_events(
    store: Neo4jDocumentStore,
    question: str,
    queries: list[str],
    expansions: list[str],
    original: str,
    top_k: int = 6,
    auto_attach: bool = True,
) -> Iterator[dict[str, Any]]:
    # 1. Расширение запроса
    if expansions:
        yield {
            "type": "thinking", "stage": "expand",
            "text": "Расширяю запрос синонимами и переформулировками: "
                    + "; ".join(expansions),
            "expansions": expansions,
        }

    # 2. Подбор и подключение релевантных документов корпуса по аннотациям
    attached: list[Any] = []
    detached: list[Any] = []
    if auto_attach:
        yield {"type": "thinking", "stage": "discover",
               "text": "Просматриваю аннотации корпуса и подключаю релевантные документы…"}
        info = store.activate_for_query(queries)
        attached, detached = info["attached"], info["detached"]
        if attached:
            titles = ", ".join(f"«{d.title}»" for d in attached)
            yield {"type": "thinking", "stage": "discover",
                   "text": f"Подключил документов: {len(attached)} — {titles}"}
        else:
            yield {"type": "thinking", "stage": "discover",
                   "text": "Дополнительных документов по аннотациям не подключено — "
                           "ищу по уже загруженным."}

    # 3. Векторный отбор фрагментов
    yield {"type": "thinking", "stage": "retrieve",
           "text": "Ищу семантически близкие фрагменты в векторной базе…"}
    hits = store.search(queries, top_k=top_k)

    if not hits:
        yield {"type": "thinking", "stage": "retrieve",
               "text": "Релевантных фрагментов выше порога не найдено."}
        # Внешний поиск пробуем даже без внутренних фрагментов — по ключевым словам
        # из самого вопроса; на ответ по внутренней базе это не влияет, но найденные
        # Scholar/Patents всё равно попадают в граф как узлы.
        yield {"type": "thinking", "stage": "external",
               "text": "Ищу внешние источники (Google Scholar и Google Patents) по ключевым словам вопроса…"}
        external = search_external(question, [])
        yield {"type": "thinking", "stage": "external", "text": _external_summary(external),
               "external": external}
        graph = build_graph_from_hits([], external=external)
        result = {
            "answer": _NOT_FOUND_ANSWER, "confidence": "нет данных", "citations": [],
            "grounded": False, "llm_used": False,
            "chunk_graph": graph["subgraph"], "chunk_graph_node_ids": graph["node_ids"],
            "chunk_graph_stats": graph["stats"], "experiment_chains": graph["experiment_chains"],
            "highlight_entities": [], "external": external,
            "query_original": original, "query_expansions": expansions,
        }
        yield {"type": "answer_delta", "text": _NOT_FOUND_ANSWER}
        yield {"type": "done", "result": result}
        return

    citations, context_lines = build_citations_and_context(hits)
    n_docs = len({c["doc_id"] for c in citations})
    yield {"type": "thinking", "stage": "retrieve",
           "text": f"Отобрано {len(citations)} фрагментов из {n_docs} документ(ов). "
                   f"Лучшая близость: {citations[0]['score']}.",
           "citations": citations}

    # 4. Извлечение сущностей и связей графа из найденных фрагментов (LLM-NER — один раз)
    yield {"type": "thinking", "stage": "entities",
           "text": "Извлекаю сущности и связи графа знаний из найденных фрагментов…"}
    build = build_internal_graph(hits, store=store)
    highlight = highlight_entities_from_graph({"subgraph": build.gs.to_vis_json()}, hits)
    if highlight:
        yield {"type": "thinking", "stage": "entities",
               "text": "Ключевые сущности — " + _entities_summary(highlight),
               "entities": highlight}
    internal_stats = finalize_graph(build)["stats"]
    yield {"type": "thinking", "stage": "entities",
           "text": f"Граф из фрагментов: {internal_stats['entities']} сущностей, "
                   f"{internal_stats['relations']} связей."}

    # 4b. Внешний поиск по ключевым словам из вопроса и сущностей графа; найденные
    # Scholar/Patents добавляем в тот же граф как узлы-публикации (без повторного NER).
    yield {"type": "thinking", "stage": "external",
           "text": "Формирую поисковые запросы из ключевых слов и ищу внешние источники "
                   "(Google Scholar и Google Patents)…"}
    external = search_external(question, highlight)
    yield {"type": "thinking", "stage": "external", "text": _external_summary(external),
           "external": external}
    external_context = build_external_context(external)
    add_external_sources(build, external)
    graph = finalize_graph(build)
    stats = graph["stats"]
    if graph["stats"].get("external_pubs"):
        yield {"type": "thinking", "stage": "external",
               "text": f"Добавил в граф внешних публикаций: {stats['external_pubs']} "
                       f"(узлы Scholar/Patents связаны с сущностями по ключевым словам)."}

    # 5. Синтез финального ответа (потоково)
    confidence = confidence_from_citations(citations)
    synth_note = (
        "Формирую ответ по фрагментам [N], дополняя внешними источниками [S*]/[P*] "
        "и разделяя происхождение фактов…" if external_context
        else "Формирую ответ строго по найденным фрагментам, со ссылками [N]…"
    )
    yield {"type": "thinking", "stage": "synthesize", "text": synth_note}

    parts: list[str] = []
    for delta in complete_stream(build_prompt(context_lines, question, external_context)):
        parts.append(delta)
        yield {"type": "answer_delta", "text": delta}

    if parts:
        answer, llm_ok = "".join(parts), True
    else:
        # LLM недоступен — отдаём честный фолбэк целиком одним delta, чтобы UI
        # всё равно показал найденные фрагменты, а не пустой ответ.
        answer, llm_ok = fallback_answer(hits), False
        yield {"type": "answer_delta", "text": answer}

    result = {
        "answer": answer, "confidence": confidence, "citations": citations,
        "grounded": True, "llm_used": llm_ok,
        "chunk_graph": graph["subgraph"], "chunk_graph_node_ids": graph["node_ids"],
        "chunk_graph_stats": stats, "experiment_chains": graph["experiment_chains"],
        "highlight_entities": highlight, "external": external,
        "query_original": original, "query_expansions": expansions,
    }
    if auto_attach:
        # asdict через _doc_to_dict делается в main.py — тут отдаём как есть,
        # main обернёт. Но чтобы модуль не зависел от main, сериализуем сами.
        from dataclasses import asdict
        result["attached"] = [asdict(d) for d in attached]
        result["detached"] = [asdict(d) for d in detached]
    yield {"type": "done", "result": result}
