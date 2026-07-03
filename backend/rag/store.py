"""Хранилище загруженных документов и внешних ссылок для RAG-чата — в Neo4j,
той же графовой БД, что и основной граф знаний (backend/graph_store_neo4j.py).

Каждый загруженный документ — обычный узел `:Entity {type: "publication"}`,
поэтому он автоматически появляется в общей визуализации графа (`/api/graph`)
наравне с публикациями из NLP-пайплайна — без этого пользователь не видел бы
загруженные через чат файлы на графе, а просил именно это. Различие только в
одном служебном свойстве: `rag_chunks` — JSON-блоб с текстом чанков и их
эмбеддингами, есть только у документов, добавленных через этот стор (обычные
Publication из nlp_pipeline его не имеют). Это поле сознательно скрыто из
всех «обычных» ответов графа (см. _HIDDEN_FROM_VIS в graph_store_neo4j.py) —
десятки КБ эмбеддингов на документ незачем гонять в каждый /api/graph.

Эмбеддинги — по-прежнему локальная модель sentence-transformers (без внешнего
сервера векторной БД, без токенов LLM); Neo4j здесь — просто персистентное
хранилище для этого JSON-блоба и место, где документ становится частью графа,
а не движок векторного поиска: сравнение сходства всё так же считается в
Python/numpy после того, как эмбеддинги вытянуты из Neo4j.

Дедупликация — по sha256 извлечённого текста (`content_hash` на узле): узел
с таким же хэшем уже есть — эмбеддинги не пересчитываются, файл повторно не
обрабатывается.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from neo4j import GraphDatabase

from backend.nlp_pipeline.chunking import chunk_blocks
from backend.nlp_pipeline.ingest import TextBlock

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_EMBED_DIM = 384


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


@dataclass
class DocumentMeta:
    id: str
    title: str
    source_type: str  # "file" | "link"
    source_name: str  # исходное имя файла или URL
    added_at: str
    num_chunks: int
    status: str  # "ready" | "error"
    error: Optional[str] = None
    content_hash: str = ""


class Neo4jDocumentStore:
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "changeme12345")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self._model = None  # ленивая загрузка — не тормозит старт бэкенда, если RAG не используется
        self._ensure_constraints()

    def close(self) -> None:
        self.driver.close()

    def _ensure_constraints(self) -> None:
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")

    # ---------- модель эмбеддингов ----------
    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(_MODEL_NAME)
        return self._model

    def _embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)

    @staticmethod
    def _meta_from_node(n) -> DocumentMeta:
        return DocumentMeta(
            id=n["id"], title=n["name"], source_type=n.get("source_type", "file"),
            source_name=n.get("source_name", ""), added_at=n.get("added_at", ""),
            num_chunks=n.get("num_chunks", 0), status=n.get("status", "ready"),
            error=n.get("error"), content_hash=n.get("content_hash", ""),
        )

    # ---------- запись ----------
    def add_document(
        self, title: str, source_type: str, source_name: str, blocks: list[TextBlock]
    ) -> tuple[DocumentMeta, bool]:
        """Возвращает (метаданные документа, is_duplicate)."""
        content_hash = hashlib.sha256("\n".join(b.text for b in blocks).encode("utf-8")).hexdigest()

        with self.driver.session() as s:
            existing = s.run(
                "MATCH (n:Entity {type: 'publication'}) "
                "WHERE n.content_hash = $hash AND n.status = 'ready' RETURN n LIMIT 1",
                hash=content_hash,
            ).single()
            if existing:
                return self._meta_from_node(existing["n"]), True

        doc_id = f"rag_{uuid.uuid4().hex[:12]}"
        chunks = chunk_blocks(blocks)

        if not chunks:
            meta = DocumentMeta(
                id=doc_id, title=title, source_type=source_type, source_name=source_name,
                added_at=_now(), num_chunks=0, status="error",
                error="Не удалось извлечь текст (пустой документ или нераспознанный формат)",
                content_hash=content_hash,
            )
            self._write_node(meta, rag_chunks=None)
            return meta, False

        vecs = self._embed([c.text for c in chunks])
        chunk_records = [
            {
                "id": f"{doc_id}_{i}", "text": c.text,
                "location": ", ".join(c.locations), "language": c.language,
                "embedding": vecs[i].tolist(),
            }
            for i, c in enumerate(chunks)
        ]

        meta = DocumentMeta(
            id=doc_id, title=title, source_type=source_type, source_name=source_name,
            added_at=_now(), num_chunks=len(chunk_records), status="ready",
            content_hash=content_hash,
        )
        self._write_node(meta, rag_chunks=chunk_records)
        return meta, False

    def _write_node(self, meta: DocumentMeta, rag_chunks: Optional[list[dict[str, Any]]]) -> None:
        props: dict[str, Any] = {
            "type": "publication", "name": meta.title,
            "source_type": meta.source_type, "source_name": meta.source_name,
            "added_at": meta.added_at, "num_chunks": meta.num_chunks,
            "status": meta.status, "content_hash": meta.content_hash,
            "error": meta.error or "",
        }
        if rag_chunks is not None:
            props["rag_chunks"] = json.dumps(rag_chunks, ensure_ascii=False)
        with self.driver.session() as s:
            s.run(
                "MERGE (n:Entity {id: $id}) SET n += $props",
                id=meta.id, props=props,
            )

    # ---------- поиск ----------
    def search(self, query: str, top_k: int = 6, min_score: float = 0.35) -> list[dict[str, Any]]:
        with self.driver.session() as s:
            rows = list(s.run(
                "MATCH (n:Entity {type: 'publication'}) WHERE n.rag_chunks IS NOT NULL RETURN n"
            ))
        if not rows:
            return []

        all_chunks: list[dict[str, Any]] = []
        all_vecs: list[list[float]] = []
        docs: dict[str, DocumentMeta] = {}
        for row in rows:
            node = row["n"]
            doc_id = node["id"]
            docs[doc_id] = self._meta_from_node(node)
            for rec in json.loads(node["rag_chunks"]):
                all_chunks.append({
                    "id": rec["id"], "doc_id": doc_id, "text": rec["text"],
                    "location": rec["location"], "language": rec["language"],
                })
                all_vecs.append(rec["embedding"])

        if not all_chunks:
            return []

        embeddings = np.asarray(all_vecs, dtype=np.float32)
        qvec = self._embed([query])[0]
        scores = embeddings @ qvec  # эмбеддинги нормированы -> косинусное сходство
        top_idx = np.argsort(-scores)[:top_k]

        results = []
        for idx in top_idx:
            score = float(scores[idx])
            if score < min_score:
                continue
            chunk = all_chunks[int(idx)]
            results.append({"chunk": _ChunkView(chunk), "score": score, "document": docs.get(chunk["doc_id"])})
        return results

    def list_documents(self) -> list[DocumentMeta]:
        with self.driver.session() as s:
            rows = s.run(
                "MATCH (n:Entity {type: 'publication'}) WHERE n.source_type IS NOT NULL RETURN n"
            )
            metas = [self._meta_from_node(r["n"]) for r in rows]
        return sorted(metas, key=lambda d: d.added_at, reverse=True)

    # ---------- удаление ----------
    def delete_document(self, doc_id: str) -> bool:
        # source_type (не rag_chunks) — так удаляются и документы со статусом
        # "error" (пустой/нечитаемый файл), у которых чанков и эмбеддингов нет,
        # но запись в списке источников всё равно есть и должна убираться.
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:Entity {id: $id, type: 'publication'}) WHERE n.source_type IS NOT NULL "
                "DETACH DELETE n RETURN count(n) AS c",
                id=doc_id,
            ).single()
        return bool(result and result["c"] > 0)


class _ChunkView:
    """Обёртка над dict-записью чанка с атрибутным доступом (chunk.text, chunk.doc_id, ...)
    — backend/rag/qa.py написан против такого интерфейса (раньше это был dataclass
    ChunkRecord из локального JSON-хранилища); здесь чанк живёт как элемент JSON-блоба
    на узле Neo4j, но контракт для qa.py остаётся тем же, чтобы не переписывать её."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError as e:
            raise AttributeError(name) from e
