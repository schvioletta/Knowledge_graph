"""FastAPI-бэкенд knowledge graph поисково-аналитической системы."""
from __future__ import annotations

import os
import uuid
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.graph_store import GraphStore
from backend.hybrid_retriever import hybrid_search
from backend.nlp_pipeline.ingest import LOADERS, load_document
from backend.rag.ingest_link import fetch_url_blocks
from backend.rag.qa import answer_question
from backend.rag.store import DocumentStore
from backend.sample_data import build_sample_graph
from backend.schema import EntityType
from backend.source_files import RAW_ROOT, resolve_source_file, source_file_meta

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# GRAPH_DATA_PATH переключает бэкенд на граф, построенный из реальных документов
# (backend/nlp_pipeline/pipeline.py -> data/real_graph.json), не трогая синтетический демо-датасет.
# Берётся из .env или окружения; относительные пути — от корня репозитория.
_graph_env = os.getenv("GRAPH_DATA_PATH")
if _graph_env:
    _graph_path = Path(_graph_env)
    DATA_PATH = _graph_path if _graph_path.is_absolute() else PROJECT_ROOT / _graph_path
else:
    DATA_PATH = PROJECT_ROOT / "data" / "sample_graph.json"

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
        print(f"[backend] граф загружен: {DATA_PATH} ({gs.g.number_of_nodes()} узлов, {gs.g.number_of_edges()} рёбер)")
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

    doc = rag_store.add_document(title=file.filename, source_type="file", source_name=file.filename, blocks=blocks)
    return asdict(doc)


@app.post("/api/documents/link")
def add_link(payload: LinkRequest):
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="url обязателен")

    try:
        blocks, title = fetch_url_blocks(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не удалось загрузить ссылку: {e}") from e

    doc = rag_store.add_document(title=title, source_type="link", source_name=url, blocks=blocks)
    return asdict(doc)


@app.get("/api/documents")
def list_documents():
    return [asdict(d) for d in rag_store.list_documents()]


@app.get("/api/rag/ask")
def rag_ask(q: str = Query(..., min_length=1)):
    return answer_question(rag_store, q)


@app.get("/api/sources/file")
def open_source_file(name: str = Query(..., min_length=1)):
    """Отдаёт исходный документ из data/raw (поиск по имени файла, без path traversal)."""
    path = resolve_source_file(name)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Файл {name!r} не найден в {RAW_ROOT}. Положите документ в data/raw/ или задайте RAW_DATA_PATH.",
        )
    return FileResponse(path, filename=path.name, media_type=None)
