"""FastAPI-бэкенд knowledge graph поисково-аналитической системы."""
from __future__ import annotations

import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Без этого .env никогда не читался: os.getenv() ниже (и в llm_client.py) видел
# только переменные, реально экспортированные в shell, поэтому YANDEX_API_KEY/
# YANDEX_FOLDER_ID из .env (см. .env.example) молча игнорировались, и LLM всегда
# уходил в фолбэк "недоступен", даже если ключ был прописан в файле.
load_dotenv()

from backend.graph_store import GraphStore
from backend.hybrid_retriever import hybrid_search
from backend.nlp_pipeline.ingest import LOADERS, load_document
from backend.rag.export_pdf import build_answer_pdf
from backend.rag.ingest_link import fetch_url_blocks
from backend.rag.qa import answer_question
from backend.rag.query_expand import expand_query
from backend.rag.store import Neo4jDocumentStore
from backend.rag.stream import stream_answer_events
from backend.sample_data import build_sample_graph
from backend.schema import EntityType

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# GRAPH_DATA_PATH переключает бэкенд на граф, построенный из реальных документов
# (backend/nlp_pipeline/pipeline.py -> data/real_graph.json), не трогая синтетический демо-датасет.
DATA_PATH = Path(os.getenv("GRAPH_DATA_PATH") or (Path(__file__).resolve().parent.parent / "data" / "sample_graph.json"))

# GRAPH_BACKEND=neo4j переключает хранилище на Neo4j (Cypher-обход связей вместо
# самописных Python-запросов поверх NetworkX) — граф должен быть предварительно
# залит в Neo4j через `python -m backend.neo4j_sync <путь-к-graph.json>` (см. README).
# По умолчанию — networkx: не требует поднятого Neo4j, подходит для демо офлайн.
GRAPH_BACKEND = os.getenv("GRAPH_BACKEND", "networkx").lower()

app = FastAPI(title="Materials Knowledge Graph API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if GRAPH_BACKEND == "neo4j":
    from backend.graph_store_neo4j import Neo4jGraphStore

    gs = Neo4jGraphStore()
else:
    gs = GraphStore()

# RAG-хранилище загруженных файлов/ссылок (backend/rag/store.py) — теперь
# всегда в Neo4j, независимо от GRAPH_BACKEND для основного графа: так
# загруженные через чат документы становятся обычными узлами графа и видны
# в общей визуализации (/api/graph), а не только в панели источников чата.
# Модель эмбеддингов грузится лениво при первой загрузке документа/вопросе,
# поэтому старт бэкенда не замедляется, если RAG не используется.
rag_store = Neo4jDocumentStore()


@app.on_event("startup")
def check_rag_store() -> None:
    # RAG-хранилище всегда в Neo4j (см. rag_store = Neo4jDocumentStore() выше),
    # независимо от GRAPH_BACKEND для основного графа — падаем сразу и понятно,
    # а не на первой попытке загрузить файл через чат.
    try:
        rag_store.driver.verify_connectivity()
    except Exception as e:
        raise RuntimeError(
            f"RAG-чат требует Neo4j, а подключиться не удалось ({e}). "
            "Поднимите его: docker compose up -d neo4j (см. README)."
        ) from e


@app.on_event("startup")
def load_graph() -> None:
    if GRAPH_BACKEND == "neo4j":
        counts = gs.counts()
        if counts["nodes"] == 0:
            raise RuntimeError(
                "GRAPH_BACKEND=neo4j, но в Neo4j нет узлов. Сначала залейте граф: "
                "python -m backend.neo4j_sync data/sample_graph.json (или data/real_graph.json)"
            )
        return

    if DATA_PATH.exists():
        gs.load(DATA_PATH)
    elif not os.getenv("GRAPH_DATA_PATH"):
        gs2 = build_sample_graph()
        gs2.save(DATA_PATH)
        gs.load(DATA_PATH)
    else:
        raise FileNotFoundError(
            f"GRAPH_DATA_PATH={DATA_PATH} не найден. Сначала постройте граф: "
            f"python -m backend.nlp_pipeline.pipeline data/raw/*.docx data/raw/*.pdf --out {DATA_PATH}"
        )


@app.on_event("shutdown")
def close_graph() -> None:
    if GRAPH_BACKEND == "neo4j":
        gs.close()
    rag_store.close()


@app.get("/api/graph")
def get_full_graph():
    return gs.to_vis_json()


@app.get("/api/graph/{node_id}")
def get_node(node_id: str):
    node = gs.node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    if node.get("type") == EntityType.EXPERIMENT.value:
        return gs.experiment_detail(node_id)
    return node


@app.get("/api/graph/{node_id}/neighbors")
def get_neighbors(node_id: str, depth: int = Query(1, ge=1, le=3)):
    if gs.node(node_id) is None:
        raise HTTPException(status_code=404, detail="node not found")
    return gs.neighbors_vis_json(node_id, depth=depth)


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    return hybrid_search(gs, q)


@app.get("/api/gaps")
def gaps(x: EntityType = EntityType.MATERIAL, y: EntityType = EntityType.CONDITION):
    return gs.gap_matrix(x_type=x, y_type=y)


@app.get("/api/timeline")
def timeline():
    return gs.dated_nodes()


@app.get("/api/health")
def health():
    return {"status": "ok", "backend": GRAPH_BACKEND, **gs.counts()}


# ---------- RAG: загрузка документов/ссылок и чат по ним ----------

class LinkRequest(BaseModel):
    url: str


class DiscoverAttachRequest(BaseModel):
    query: str
    top_docs: int = 5


def _doc_to_dict(doc) -> dict[str, Any]:
    return asdict(doc)


def _expand_and_search_queries(q: str) -> dict[str, Any]:
    return expand_query(q)


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in LOADERS:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат {ext!r}. Поддерживаются: {', '.join(sorted(LOADERS))}",
        )

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{file.filename}"
    dest.write_bytes(await file.read())

    try:
        blocks, _meta = load_document(dest)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать файл: {e}") from e

    doc, is_duplicate = rag_store.add_document(
        title=file.filename, source_type="file", source_name=file.filename, blocks=blocks
    )
    if is_duplicate:
        # Уже есть документ с тем же текстом (см. add_document) — не тратим место
        # на дублирующую копию файла на диске, эмбеддинги тоже не пересчитывались.
        dest.unlink(missing_ok=True)
    return {**_doc_to_dict(doc), "duplicate": is_duplicate}


@app.post("/api/documents/link")
def add_link(payload: LinkRequest):
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="url обязателен")

    try:
        blocks, title = fetch_url_blocks(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не удалось загрузить ссылку: {e}") from e

    doc, is_duplicate = rag_store.add_document(title=title, source_type="link", source_name=url, blocks=blocks)
    return {**_doc_to_dict(doc), "duplicate": is_duplicate}


@app.get("/api/documents")
def list_documents():
    return [_doc_to_dict(d) for d in rag_store.list_documents()]


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    if not rag_store.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="document not found")
    return {"status": "deleted", "id": doc_id}


@app.post("/api/rag/discover-and-attach")
def discover_and_attach(payload: DiscoverAttachRequest):
    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query обязателен")
    expanded = _expand_and_search_queries(q)
    result = rag_store.activate_for_query(expanded["all_queries"], top_docs=payload.top_docs)
    return {
        "attached": [_doc_to_dict(d) for d in result["attached"]],
        "detached": [_doc_to_dict(d) for d in result["detached"]],
        "query_original": expanded["original"],
        "query_expansions": expanded["expansions"],
        "expand_llm": expanded.get("expand_llm"),
    }


@app.get("/api/rag/ask")
def rag_ask(q: str = Query(..., min_length=1), auto_attach: bool = Query(True)):
    expanded = _expand_and_search_queries(q)
    queries = expanded["all_queries"]
    attach_info = None
    if auto_attach:
        attach_info = rag_store.activate_for_query(queries)
    result = answer_question(rag_store, q, search_queries=queries)
    result["query_original"] = expanded["original"]
    result["query_expansions"] = expanded["expansions"]
    result["expand_llm"] = expanded.get("expand_llm")
    if attach_info:
        result["attached"] = [_doc_to_dict(d) for d in attach_info["attached"]]
        result["detached"] = [_doc_to_dict(d) for d in attach_info["detached"]]
    return result


@app.get("/api/rag/ask/stream")
def rag_ask_stream(q: str = Query(..., min_length=1), auto_attach: bool = Query(True)):
    """SSE-версия /api/rag/ask: те же этапы, но каждый шаг конвейера и куски
    финального ответа отдаются в реальном времени (см. backend/rag/stream.py).
    Финальное событие done несёт тот же объект, что вернул бы /api/rag/ask."""
    import json

    expanded = _expand_and_search_queries(q)

    def event_source():
        try:
            for event in stream_answer_events(
                rag_store, q,
                queries=expanded["all_queries"],
                expansions=expanded["expansions"],
                original=expanded["original"],
                auto_attach=auto_attach,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:  # не роняем поток молча — сообщаем клиенту
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class RagExportRequest(BaseModel):
    question: str
    answer: str
    confidence: str = "нет данных"
    citations: list[dict[str, Any]] = []
    grounded: bool = False
    llm_used: bool = False


@app.post("/api/rag/export/pdf")
def rag_export_pdf(payload: RagExportRequest):
    # PDF — единственный из трёх форматов экспорта, который генерируется на
    # бэкенде (JSON/Markdown фронтенд собирает сам из уже полученного ответа):
    # для кириллицы нужен встроенный TTF-шрифт (fpdf2/rag/export_pdf.py),
    # тащить шрифт и верстку на клиент ради одного экспорта не оправдано.
    pdf_bytes = build_answer_pdf(
        question=payload.question, answer=payload.answer, confidence=payload.confidence,
        citations=payload.citations, grounded=payload.grounded, llm_used=payload.llm_used,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="rag-answer.pdf"'},
    )
