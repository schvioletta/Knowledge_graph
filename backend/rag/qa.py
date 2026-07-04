"""Grounded RAG-ответ: только по фрагментам загруженных документов/ссылок.

Отказ вместо выдумки — если Neo4jDocumentStore.search() не находит ничего выше
порога релевантности, отвечаем прямым текстом "не нашлось", а не отправляем
пустой контекст в LLM (иначе модель почти наверняка ответит из общих знаний,
что и является тем самым "неподтверждённым ответом", которого просили
избежать). Confidence — эвристика той же природы, что infer_confidence в
nlp_pipeline/graph_writer.py: чем выше сходство и чем больше независимых
документов подтверждают ответ, тем выше уверенность.
"""
from __future__ import annotations

from typing import Any

from backend.llm_client import complete as llm_complete
from backend.llm_client import get_last_error as llm_last_error
from backend.llm_client import is_configured as llm_configured
from backend.rag.chunk_graph import (
    add_external_sources,
    build_graph_from_hits,
    build_internal_graph,
    finalize_graph,
)
from backend.rag.external_search import search_external
from backend.rag.store import Neo4jDocumentStore
from backend.schema import EntityType

_NOT_FOUND_ANSWER = (
    "В загруженных документах и ссылках не нашлось информации по этому вопросу. "
    "Загрузите релевантный файл или добавьте ссылку на статью, чтобы получить ответ по нему."
)

_SYSTEM_PROMPT = """Ты — ассистент, отвечающий СТРОГО по предоставленным фрагментам документов.

Правила (обязательны без исключений):
1. Используй только факты из фрагментов ниже. Не добавляй ничего от себя, не используй общие знания.
2. Каждое утверждение и КАЖДОЕ число (концентрации, проценты, даты, объёмы, показатели и т.д.)
   сопровождай ссылкой на фрагмент в формате [N], где N — номер фрагмента из списка ниже.
   Числа переноси из фрагментов дословно, не округляй и не пересчитывай.
3. Если во фрагментах нет ответа на вопрос (полностью или частично) — прямо скажи, какой
   именно части вопроса не хватает данных, не додумывай и не подменяй общими рассуждениями.
4. Ответ — на русском, по делу, без вступлений и извинений.

ФРАГМЕНТЫ:
{context}

ВОПРОС: {question}

ОТВЕТ (каждый факт и число — со ссылкой [N]):"""

# Вариант промпта, когда автоматический внешний поиск нашёл научные публикации
# и/или патенты. Внутренняя база остаётся основой ответа (правила 1–4), а внешние
# источники — вспомогательный контекст, который LLM обязана явно отделять от неё.
_SYSTEM_PROMPT_WITH_EXTERNAL = """Ты — ассистент, отвечающий по предоставленным материалам двух видов:
(A) фрагменты внутренней базы знаний (загруженные документы/ссылки) — ссылки [N];
(B) внешние источники, найденные автоматически по ключевым словам, — научные
    публикации Google Scholar (ссылки [S1], [S2], …) и патенты Google Patents
    (ссылки [P1], [P2], …).

Правила (обязательны без исключений):
1. Основу ответа строй по внутренним фрагментам [N]. Каждое утверждение и КАЖДОЕ число
   (концентрации, проценты, даты, объёмы, показатели) сопровождай ссылкой на фрагмент [N].
   Числа переноси дословно, не округляй и не пересчитывай.
2. Внешние источники (B) используй только как дополнительный контекст — чтобы подтвердить,
   уточнить или расширить сказанное. Ссылайся на них как [S*] (публикации) и [P*] (патенты).
   Не приписывай внешним источникам фактов, которых нет в их описании.
3. ЯВНО разделяй в ответе информацию по происхождению. В конце ответа добавь короткие
   помеченные блоки (только те, для которых есть данные):
   «Из внутренней базы знаний:» — что подтверждается фрагментами [N];
   «Подтверждено научными публикациями:» — что согласуется с [S*];
   «Подтверждено патентной литературой:» — что согласуется с [P*].
4. Если внешние источники не подтверждают ничего по существу вопроса — не выдумывай связь,
   просто опусти соответствующий блок. Внутренняя база важнее: противоречия трактуй в её пользу.
5. Ответ — на русском, по делу, без вступлений и извинений.

ФРАГМЕНТЫ ВНУТРЕННЕЙ БАЗЫ:
{context}

ВНЕШНИЕ ИСТОЧНИКИ:
{external}

ВОПРОС: {question}

ОТВЕТ (факты внутренней базы — со ссылкой [N]; внешние — с [S*]/[P*]; в конце — разделение по происхождению):"""


def build_external_context(external: dict[str, Any] | None) -> str:
    """Форматирует найденные внешние источники для промпта, нумеруя публикации
    как [S1], [S2]… и патенты как [P1], [P2]…, чтобы LLM могла ссылаться на них
    отдельно от внутренних фрагментов [N]. Пустая строка — если внешних нет."""
    if not external or not external.get("enabled"):
        return ""
    scholar = external.get("scholar") or []
    patents = external.get("patents") or []
    if not scholar and not patents:
        return ""

    lines: list[str] = []
    if scholar:
        lines.append("Научные публикации (Google Scholar):")
        for i, s in enumerate(scholar, start=1):
            authors = ", ".join(s.get("authors") or []) or "авторы не указаны"
            year = s.get("year") or "год не указан"
            venue = s.get("venue") or "источник не указан"
            snippet = (s.get("snippet") or "").strip()
            lines.append(f"[S{i}] «{s.get('title', '')}» — {authors}. {year}. {venue}. {snippet}".strip())
    if patents:
        lines.append("Патенты (Google Patents):")
        for i, p in enumerate(patents, start=1):
            authors = ", ".join(p.get("authors") or []) or "изобретатели не указаны"
            year = p.get("year") or "год не указан"
            number = p.get("venue") or "номер не указан"
            snippet = (p.get("snippet") or "").strip()
            lines.append(f"[P{i}] «{p.get('title', '')}» — {authors}. {year}. {number}. {snippet}".strip())
    return "\n".join(lines)


def build_citations_and_context(hits: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Нумерованные цитаты для UI + контекст для промпта из результатов поиска.
    Общая часть для потокового и непотокового ответа — чтобы номера [N] в
    ответе, список источников и переданный в LLM контекст были согласованы."""
    citations: list[dict[str, Any]] = []
    context_lines: list[str] = []
    for i, hit in enumerate(hits, start=1):
        chunk = hit["chunk"]
        doc = hit["document"]
        title = doc.title if doc else "?"
        context_lines.append(f"[{i}] ({title}, {chunk.location}):\n{chunk.text}")
        citations.append({
            "index": i,
            "doc_id": chunk.doc_id,
            "title": title,
            "source_type": doc.source_type if doc else "?",
            "source_name": doc.source_name if doc else "?",
            "location": chunk.location,
            "score": round(hit["score"], 3),
            "snippet": chunk.text[:280],
        })
    return citations, context_lines


def confidence_from_citations(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return "нет данных"
    distinct_docs = {c["doc_id"] for c in citations}
    top_score = citations[0]["score"]
    if top_score >= 0.60 and len(distinct_docs) >= 2:
        return "высокая"
    if top_score >= 0.45:
        return "средняя"
    return "низкая"


def build_prompt(context_lines: list[str], question: str, external_context: str = "") -> str:
    if external_context:
        return _SYSTEM_PROMPT_WITH_EXTERNAL.format(
            context="\n\n".join(context_lines),
            external=external_context,
            question=question,
        )
    return _SYSTEM_PROMPT.format(context="\n\n".join(context_lines), question=question)


def fallback_answer(hits: list[dict[str, Any]]) -> str:
    """Детерминированный, но честный фолбэк, когда LLM недоступен: сами фрагменты
    с указанием источников, а не тишина и не выдумка. Причина — конкретная:
    «ключ не задан» и «ключ задан, но вызов упал» требуют разных действий."""
    if not llm_configured():
        reason = "LLM не настроен (нет GIGACHAT_API_KEY — см. .env.example)"
    else:
        reason = f"вызов LLM не удался ({llm_last_error() or 'неизвестная ошибка'})"
    return f"{reason}. Показаны наиболее релевантные фрагменты источников:\n\n" + "\n\n".join(
        f"[{i}] {hit['chunk'].text[:600]}" for i, hit in enumerate(hits, start=1)
    )


def highlight_entities_from_graph(
    graph: dict[str, Any], hits: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Ключевые сущности для подсветки в тексте ответа — все узлы графа
    из найденных фрагментов, КРОМЕ самих публикаций (их и так видно в
    источниках). Для каждой считаем `mentions` — в скольких найденных
    фрагментах встречается её название (для tooltip). Сортируем от длинных
    названий к коротким, чтобы на фронте более длинные совпадения матчились
    раньше вложенных (напр. «электроэкстракция никеля» раньше «никель»)."""
    chunk_texts = [h["chunk"].text.lower() for h in hits]
    entities: list[dict[str, Any]] = []
    for node in graph["subgraph"]["nodes"]:
        if node.get("type") == EntityType.PUBLICATION.value:
            continue
        name = (node.get("name") or "").strip()
        if len(name) < 3:  # односимвольные/пустые названия не подсвечиваем — шум
            continue
        low = name.lower()
        mentions = sum(1 for t in chunk_texts if low in t)
        entities.append({
            "id": node["id"],
            "name": name,
            "type": node.get("type"),
            "mentions": mentions,
            "degree": node.get("degree", 0),
        })
    entities.sort(key=lambda e: len(e["name"]), reverse=True)
    return entities


def answer_question(
    store: Neo4jDocumentStore,
    question: str,
    top_k: int = 6,
    search_queries: list[str] | None = None,
) -> dict[str, Any]:
    queries = search_queries or [question]
    hits = store.search(queries, top_k=top_k)

    if not hits:
        # Внешний поиск всё равно пробуем — по ключевым словам из самого вопроса,
        # чтобы дать актуальные публикации/патенты, даже когда внутренняя база пуста.
        # На ответ по внутренней базе это не влияет (он остаётся _NOT_FOUND_ANSWER),
        # но найденные Scholar/Patents всё равно попадают в граф как узлы.
        external = search_external(question, [])
        graph = build_graph_from_hits([], external=external)
        return {
            "answer": _NOT_FOUND_ANSWER,
            "confidence": "нет данных",
            "citations": [],
            "grounded": False,
            "llm_used": False,
            "chunk_graph": graph["subgraph"],
            "chunk_graph_node_ids": graph["node_ids"],
            "chunk_graph_stats": graph["stats"],
            "experiment_chains": graph["experiment_chains"],
            "highlight_entities": [],
            "external": external,
        }

    citations, context_lines = build_citations_and_context(hits)

    # Внутренний граф строим один раз (LLM-NER по чанкам), из него берём highlight-
    # сущности, по ним ищем внешние источники, затем добавляем их в ТОТ ЖЕ граф
    # (дёшево, без повторного NER) — чтобы чанки Scholar/Patents стали узлами графа.
    build = build_internal_graph(hits)
    highlight = highlight_entities_from_graph({"subgraph": build.gs.to_vis_json()}, hits)

    # Внешний поиск по ключевым словам из вопроса и сущностей графа. Никогда не
    # бросает исключений (см. search_external), поэтому не может сорвать ответ.
    external = search_external(question, highlight)
    external_context = build_external_context(external)
    add_external_sources(build, external)
    graph = finalize_graph(build)

    llm_answer = llm_complete(build_prompt(context_lines, question, external_context))
    confidence = confidence_from_citations(citations)

    if llm_answer:
        answer, llm_ok = llm_answer, True
    else:
        answer, llm_ok = fallback_answer(hits), False

    return {
        "answer": answer,
        "confidence": confidence,
        "citations": citations,
        "grounded": True,
        "llm_used": llm_ok,
        "chunk_graph": graph["subgraph"],
        "chunk_graph_node_ids": graph["node_ids"],
        "chunk_graph_stats": graph["stats"],
        "experiment_chains": graph["experiment_chains"],
        "highlight_entities": highlight,
        "external": external,
    }
