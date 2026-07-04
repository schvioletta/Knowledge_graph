# Backend

Полная документация по архитектуре, запуску, NLP-пайплайну, Neo4j, RAG и API —
в [корневом README.md](../README.md).

Кратко:

- `make backend` — FastAPI на `:8000` (требует Neo4j: `docker compose up -d neo4j`)
- `GRAPH_BACKEND=networkx` (по умолчанию, JSON из `GRAPH_DATA_PATH`) или `neo4j` (после `python -m backend.neo4j_sync data/sample_graph.json`)
- RAG-хранилище всегда в Neo4j (`backend/rag/store.py`), независимо от `GRAPH_BACKEND`
