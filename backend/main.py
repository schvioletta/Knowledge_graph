"""FastAPI-бэкенд knowledge graph поисково-аналитической системы."""
from __future__ import annotations

import os
import uuid
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Без этого .env никогда не читался: os.getenv() ниже (и в llm_client.py) видел
# только переменные, реально экспортированные в shell, поэтому YANDEX_API_KEY/
# YANDEX_FOLDER_ID из .env (см. .env.example) молча игнорировались, и LLM всегда
# уходил в фолбэк "недоступен", даже если ключ был прописан в файле.
load_dotenv()

from backend.graph_store import GraphStore
from backend.hybrid_retriever import hybrid_search
from backend.nlp_pipeline.ingest import LOADERS, load_document
from backend.rag.ingest_link import fetch_url_blocks
from backend.rag.qa import answer_question
from backend.rag.store import DocumentStore
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

# RAG-хранилище загруженных файлов/ссылок (независимо от графа знаний — см.
# backend/rag/store.py). Модель эмбеддингов грузится лениво при первой
# загрузке документа/вопросе, поэтому старт бэкенда не замедляется, если
# RAG не используется.
rag_store = DocumentStore()


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
    return {**asdict(doc), "duplicate": is_duplicate}


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
    return {**asdict(doc), "duplicate": is_duplicate}


@app.get("/api/documents")
def list_documents():
    return [asdict(d) for d in rag_store.list_documents()]


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    if not rag_store.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="document not found")
    return {"status": "deleted", "id": doc_id}


@app.get("/api/rag/ask")
def rag_ask(q: str = Query(..., min_length=1)):
    return answer_question(rag_store, q)
