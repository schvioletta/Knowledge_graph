"""FastAPI-бэкенд knowledge graph поисково-аналитической системы."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.graph_store import GraphStore
from backend.hybrid_retriever import hybrid_search
from backend.sample_data import build_sample_graph
from backend.schema import EntityType

# GRAPH_DATA_PATH переключает бэкенд на граф, построенный из реальных документов
# (backend/nlp_pipeline/pipeline.py -> data/real_graph.json), не трогая синтетический демо-датасет.
DATA_PATH = Path(os.getenv("GRAPH_DATA_PATH") or (Path(__file__).resolve().parent.parent / "data" / "sample_graph.json"))

app = FastAPI(title="Materials Knowledge Graph API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

gs = GraphStore()


@app.on_event("startup")
def load_graph() -> None:
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
    if node_id not in gs.g:
        raise HTTPException(status_code=404, detail="node not found")
    sub = gs.neighbors_subgraph(node_id, depth=depth)
    return gs.to_vis_json(sub)


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    return hybrid_search(gs, q)


@app.get("/api/gaps")
def gaps(x: EntityType = EntityType.MATERIAL, y: EntityType = EntityType.CONDITION):
    return gs.gap_matrix(x_type=x, y_type=y)


@app.get("/api/timeline")
def timeline():
    dated = []
    for n, d in gs.g.nodes(data=True):
        date = d.get("date")
        if date:
            dated.append({"id": n, "type": d.get("type"), "name": d.get("name"), "date": date})
    dated.sort(key=lambda x: x["date"])
    return dated


@app.get("/api/health")
def health():
    return {"status": "ok", "nodes": gs.g.number_of_nodes(), "edges": gs.g.number_of_edges()}
