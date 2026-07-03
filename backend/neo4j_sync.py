"""Заливает граф из JSON (data/sample_graph.json или data/real_graph.json,
собранный backend/nlp_pipeline/pipeline.py) в Neo4j одной пакетной операцией.

Использование:
    docker compose up -d neo4j
    export NEO4J_PASSWORD=...   # см. docker-compose.yml
    python -m backend.neo4j_sync data/sample_graph.json
    GRAPH_BACKEND=neo4j uvicorn backend.main:app --reload --port 8000

Идемпотентно: перезаливка того же файла не плодит дублей (MERGE по id),
а полный DETACH DELETE перед заливкой гарантирует, что в Neo4j не остаётся
узлов из предыдущей версии графа, которых больше нет в файле.
"""
from __future__ import annotations

import argparse
import sys
import time

from backend.graph_store import GraphStore
from backend.graph_store_neo4j import Neo4jGraphStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Синхронизация graph.json -> Neo4j")
    parser.add_argument("graph_json", help="Путь к графу в формате GraphStore.save() (напр. data/real_graph.json)")
    args = parser.parse_args()

    gs = GraphStore()
    gs.load(args.graph_json)
    print(f"загружено из {args.graph_json}: {gs.g.number_of_nodes()} узлов, {gs.g.number_of_edges()} рёбер")

    neo = Neo4jGraphStore()
    try:
        t0 = time.time()
        stats = neo.sync_from_graph_store(gs)
        print(f"залито в Neo4j: {stats['nodes']} узлов, {stats['edges']} рёбер за {time.time() - t0:.1f}с")
    except Exception as e:
        print(f"ошибка синхронизации с Neo4j ({neo.uri}): {e}", file=sys.stderr)
        raise
    finally:
        neo.close()


if __name__ == "__main__":
    main()
