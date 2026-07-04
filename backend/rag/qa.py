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
from backend.rag.chunk_graph import build_graph_from_hits
from backend.rag.store import Neo4jDocumentStore

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


def answer_question(
    store: Neo4jDocumentStore,
    question: str,
    top_k: int = 6,
    search_queries: list[str] | None = None,
) -> dict[str, Any]:
    queries = search_queries or [question]
    hits = store.search(queries, top_k=top_k)

    if not hits:
        empty = build_graph_from_hits([])
        return {
            "answer": _NOT_FOUND_ANSWER,
            "confidence": "нет данных",
            "citations": [],
            "grounded": False,
            "llm_used": False,
            "chunk_graph": empty["subgraph"],
            "chunk_graph_node_ids": empty["node_ids"],
            "chunk_graph_stats": empty["stats"],
        }

    citations = []
    context_lines = []
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

    prompt = _SYSTEM_PROMPT.format(context="\n\n".join(context_lines), question=question)
    llm_answer = llm_complete(prompt)

    distinct_docs = {c["doc_id"] for c in citations}
    top_score = citations[0]["score"]
    if top_score >= 0.60 and len(distinct_docs) >= 2:
        confidence = "высокая"
    elif top_score >= 0.45:
        confidence = "средняя"
    else:
        confidence = "низкая"

    if llm_answer:
        answer = llm_answer
        llm_ok = True
    else:
        # Без LLM — детерминированный, но честный фолбэк: сами фрагменты (полнее, чем короткий
        # snippet в citations — там это просто превью для UI) с указанием источников, а не
        # тишина и не выдумка. Причина фолбэка — не общая, а конкретная: «ключ не задан» и
        # «ключ задан, но вызов упал» требуют разных действий от того, кто это читает.
        if not llm_configured():
            reason = "LLM не настроен (нет GIGACHAT_API_KEY — см. .env.example)"
        else:
            reason = f"вызов LLM не удался ({llm_last_error() or 'неизвестная ошибка'})"
        answer = f"{reason}. Показаны наиболее релевантные фрагменты источников:\n\n" + "\n\n".join(
            f"[{i}] {hit['chunk'].text[:600]}" for i, hit in enumerate(hits, start=1)
        )
        llm_ok = False

    graph = build_graph_from_hits(hits)
    return {
        "answer": answer,
        "confidence": confidence,
        "citations": citations,
        "grounded": True,
        "llm_used": llm_ok,
        "chunk_graph": graph["subgraph"],
        "chunk_graph_node_ids": graph["node_ids"],
        "chunk_graph_stats": graph["stats"],
    }
