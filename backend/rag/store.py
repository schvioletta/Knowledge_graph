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

Корпусный индекс (index_corpus.py): метаданные + abstract-чанки в
`abstract_rag_chunks`; при запросе top-N документов активируются полностью
(`index_mode=full`), auto-источники предыдущего запроса сбрасываются в abstract.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from neo4j import GraphDatabase

from backend.nlp_pipeline.chunking import chunk_blocks
from backend.nlp_pipeline.ingest import TextBlock, load_document
from backend.rag.lexical_boost import (
    BOOST_WEIGHT,
    POOL_MULT,
    extract_query_signals,
    lexical_score,
)
from backend.rag.metadata_extract import DocumentMetadata

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_EMBED_DIM = 384
_DEFAULT_TOP_DOCS = 5


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


@dataclass
class DocumentMeta:
    id: str
    title: str
    source_type: str  # "file" | "link" | "corpus"
    source_name: str
    added_at: str
    num_chunks: int
    status: str  # "ready" | "error"
    error: Optional[str] = None
    content_hash: str = ""
    authors: str = ""
    source: str = ""
    year: Optional[int] = None
    geography: str = ""
    language: str = ""
    domain: str = ""
    reliability_score: float = 0.0
    document_summary: str = ""
    abstract: str = ""
    source_path: str = ""
    index_mode: str = "full"
    attached: bool = True
    attach_source: str = "manual"
    extra: dict[str, Any] = field(default_factory=dict)


class Neo4jDocumentStore:
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "changeme12345")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self._model = None
        self._ensure_constraints()

    def close(self) -> None:
        self.driver.close()

    def _ensure_constraints(self) -> None:
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")

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
        authors_raw = n.get("authors", "")
        year_val = n.get("year")
        year: Optional[int] = None
        if year_val not in (None, ""):
            try:
                year = int(year_val)
            except (TypeError, ValueError):
                year = None
        attached_val = n.get("attached", True)
        if attached_val is None:
            attached = True
        elif isinstance(attached_val, bool):
            attached = attached_val
        else:
            attached = str(attached_val).lower() in ("true", "1")
        return DocumentMeta(
            id=n["id"],
            title=n.get("name", ""),
            source_type=n.get("source_type", "file"),
            source_name=n.get("source_name", ""),
            added_at=n.get("added_at", ""),
            num_chunks=int(n.get("num_chunks", 0) or 0),
            status=n.get("status", "ready"),
            error=n.get("error") or None,
            content_hash=n.get("content_hash", ""),
            authors=authors_raw,
            source=n.get("source", ""),
            year=year,
            geography=n.get("geography", ""),
            language=n.get("language", ""),
            domain=n.get("domain", ""),
            reliability_score=float(n.get("reliability_score", 0) or 0),
            document_summary=n.get("document_summary", ""),
            abstract=n.get("abstract", ""),
            source_path=n.get("source_path", ""),
            index_mode=n.get("index_mode", "full"),
            attached=attached,
            attach_source=n.get("attach_source", "manual"),
        )

    @staticmethod
    def _chunk_records_from_blocks(doc_id: str, blocks: list[TextBlock], vecs: np.ndarray) -> list[dict[str, Any]]:
        chunks = chunk_blocks(blocks)
        return [
            {
                "id": f"{doc_id}_{i}",
                "text": c.text,
                "location": ", ".join(c.locations),
                "language": c.language,
                "embedding": vecs[i].tolist(),
            }
            for i, c in enumerate(chunks)
        ]

    def _build_props(
        self,
        meta: DocumentMeta,
        rag_chunks: Optional[list[dict[str, Any]]] = None,
        abstract_rag_chunks: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        props: dict[str, Any] = {
            "type": "publication",
            "name": meta.title,
            "source_type": meta.source_type,
            "source_name": meta.source_name,
            "added_at": meta.added_at,
            "num_chunks": meta.num_chunks,
            "status": meta.status,
            "content_hash": meta.content_hash,
            "error": meta.error or "",
            "authors": meta.authors,
            "source": meta.source,
            "year": meta.year if meta.year is not None else "",
            "geography": meta.geography,
            "language": meta.language,
            "domain": meta.domain,
            "reliability_score": meta.reliability_score,
            "document_summary": meta.document_summary,
            "abstract": meta.abstract,
            "source_path": meta.source_path,
            "index_mode": meta.index_mode,
            "attached": meta.attached,
            "attach_source": meta.attach_source,
        }
        if rag_chunks is not None:
            props["rag_chunks"] = json.dumps(rag_chunks, ensure_ascii=False)
        if abstract_rag_chunks is not None:
            props["abstract_rag_chunks"] = json.dumps(abstract_rag_chunks, ensure_ascii=False)
        return props

    def _write_node(
        self,
        meta: DocumentMeta,
        rag_chunks: Optional[list[dict[str, Any]]] = None,
        abstract_rag_chunks: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        props = self._build_props(meta, rag_chunks, abstract_rag_chunks)
        with self.driver.session() as s:
            s.run("MERGE (n:Entity {id: $id}) SET n += $props", id=meta.id, props=props)

    def _update_node(self, doc_id: str, props: dict[str, Any]) -> None:
        with self.driver.session() as s:
            s.run("MATCH (n:Entity {id: $id}) SET n += $props", id=doc_id, props=props)

    def _get_node(self, doc_id: str):
        with self.driver.session() as s:
            row = s.run("MATCH (n:Entity {id: $id}) RETURN n", id=doc_id).single()
        return row["n"] if row else None

    # ---------- ручная загрузка ----------
    def add_document(
        self, title: str, source_type: str, source_name: str, blocks: list[TextBlock]
    ) -> tuple[DocumentMeta, bool]:
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
                id=doc_id,
                title=title,
                source_type=source_type,
                source_name=source_name,
                added_at=_now(),
                num_chunks=0,
                status="error",
                error="Не удалось извлечь текст (пустой документ или нераспознанный формат)",
                content_hash=content_hash,
                attached=True,
                attach_source="manual",
                index_mode="full",
            )
            self._write_node(meta, rag_chunks=None)
            return meta, False

        vecs = self._embed([c.text for c in chunks])
        chunk_records = self._chunk_records_from_blocks(doc_id, blocks, vecs)

        meta = DocumentMeta(
            id=doc_id,
            title=title,
            source_type=source_type,
            source_name=source_name,
            added_at=_now(),
            num_chunks=len(chunk_records),
            status="ready",
            content_hash=content_hash,
            attached=True,
            attach_source="manual",
            index_mode="full",
        )
        self._write_node(meta, rag_chunks=chunk_records)
        return meta, False

    # ---------- корпусный индекс ----------
    def find_indexed_by_path(self, source_path: str) -> Optional[DocumentMeta]:
        with self.driver.session() as s:
            row = s.run(
                "MATCH (n:Entity {type: 'publication'}) "
                "WHERE n.source_path = $path AND n.source_type = 'corpus' RETURN n LIMIT 1",
                path=source_path,
            ).single()
        return self._meta_from_node(row["n"]) if row else None

    def index_document(
        self,
        source_path: str | Path,
        metadata: DocumentMetadata,
        abstract_blocks: list[TextBlock],
        file_hash: str,
        force: bool = False,
    ) -> tuple[DocumentMeta, bool]:
        path = str(Path(source_path).resolve())
        existing = self.find_indexed_by_path(path)
        if existing and existing.content_hash == file_hash and existing.status == "ready" and not force:
            return existing, True

        doc_id = existing.id if existing else f"corpus_{uuid.uuid4().hex[:12]}"
        abs_text = metadata.abstract or "\n\n".join(b.text for b in abstract_blocks)

        if not abstract_blocks:
            meta = DocumentMeta(
                id=doc_id,
                title=metadata.title or Path(path).name,
                source_type="corpus",
                source_name=Path(path).name,
                added_at=existing.added_at if existing else _now(),
                num_chunks=0,
                status="error",
                error="Пустая аннотация — документ не проиндексирован",
                content_hash=file_hash,
                authors=", ".join(metadata.authors),
                source=metadata.source,
                year=metadata.year,
                geography=metadata.geography,
                language=metadata.language,
                domain=metadata.domain,
                reliability_score=metadata.reliability_score,
                document_summary=metadata.document_summary,
                abstract=abs_text,
                source_path=path,
                index_mode="abstract",
                attached=False,
                attach_source="",
            )
            self._write_node(meta)
            return meta, False

        text_chunks = chunk_blocks(abstract_blocks)
        vecs = self._embed([c.text for c in text_chunks])
        chunk_records = [
            {
                "id": f"{doc_id}_{i}",
                "text": c.text,
                "location": ", ".join(c.locations),
                "language": c.language,
                "embedding": vecs[i].tolist(),
            }
            for i, c in enumerate(text_chunks)
        ]

        meta = DocumentMeta(
            id=doc_id,
            title=metadata.title or Path(path).name,
            source_type="corpus",
            source_name=Path(path).name,
            added_at=existing.added_at if existing else _now(),
            num_chunks=len(chunk_records),
            status="ready",
            content_hash=file_hash,
            authors=", ".join(metadata.authors),
            source=metadata.source,
            year=metadata.year,
            geography=metadata.geography,
            language=metadata.language,
            domain=metadata.domain,
            reliability_score=metadata.reliability_score,
            document_summary=metadata.document_summary,
            abstract=abs_text,
            source_path=path,
            index_mode="abstract",
            attached=False,
            attach_source="",
        )
        self._write_node(meta, rag_chunks=chunk_records, abstract_rag_chunks=chunk_records)
        return meta, False

    def search_index(
        self,
        query: str | list[str],
        top_k: int = 20,
        min_score: float = 0.25,
    ) -> list[dict[str, Any]]:
        with self.driver.session() as s:
            rows = list(s.run(
                "MATCH (n:Entity {type: 'publication', source_type: 'corpus'}) "
                "WHERE n.abstract_rag_chunks IS NOT NULL AND n.status = 'ready' RETURN n"
            ))
        return self._search_chunks(rows, query, "abstract_rag_chunks", top_k, min_score)

    def detach_auto_documents(self) -> list[DocumentMeta]:
        with self.driver.session() as s:
            rows = list(s.run(
                "MATCH (n:Entity {type: 'publication'}) "
                "WHERE n.attach_source = 'auto' RETURN n"
            ))
        detached: list[DocumentMeta] = []
        for row in rows:
            node = row["n"]
            doc_id = node["id"]
            abstract_chunks_raw = node.get("abstract_rag_chunks") or node.get("rag_chunks")
            if not abstract_chunks_raw:
                continue
            props = {
                "attached": False,
                "attach_source": "",
                "index_mode": "abstract",
                "rag_chunks": abstract_chunks_raw,
                "num_chunks": len(json.loads(abstract_chunks_raw)),
            }
            self._update_node(doc_id, props)
            detached.append(self._meta_from_node({**dict(node), **props}))
        return detached

    def activate_document(self, doc_id: str) -> Optional[DocumentMeta]:
        node = self._get_node(doc_id)
        if not node or node.get("source_type") != "corpus":
            return None
        source_path = node.get("source_path")
        if not source_path or not Path(source_path).exists():
            return None

        blocks, _ = load_document(source_path)
        text_chunks = chunk_blocks(blocks)
        if not text_chunks:
            return None

        vecs = self._embed([c.text for c in text_chunks])
        chunk_records = [
            {
                "id": f"{doc_id}_{i}",
                "text": c.text,
                "location": ", ".join(c.locations),
                "language": c.language,
                "embedding": vecs[i].tolist(),
            }
            for i, c in enumerate(text_chunks)
        ]
        abstract_chunks = node.get("abstract_rag_chunks") or node.get("rag_chunks", "[]")

        props = {
            "attached": True,
            "attach_source": "auto",
            "index_mode": "full",
            "rag_chunks": json.dumps(chunk_records, ensure_ascii=False),
            "abstract_rag_chunks": abstract_chunks,
            "num_chunks": len(chunk_records),
        }
        self._update_node(doc_id, props)
        return self._meta_from_node({**dict(node), **props})

    def activate_for_query(
        self,
        query: str | list[str],
        top_docs: int = _DEFAULT_TOP_DOCS,
    ) -> dict[str, Any]:
        detached = self.detach_auto_documents()
        hits = self.search_index(query, top_k=top_docs * 4)

        doc_scores: dict[str, float] = {}
        for hit in hits:
            doc_id = hit["chunk"].doc_id
            score = hit["score"]
            doc_scores[doc_id] = max(doc_scores.get(doc_id, 0.0), score)

        top_ids = sorted(doc_scores, key=lambda d: doc_scores[d], reverse=True)[:top_docs]
        attached: list[DocumentMeta] = []
        for doc_id in top_ids:
            meta = self.activate_document(doc_id)
            if meta:
                attached.append(meta)
        return {"attached": attached, "detached": detached}

    # ---------- поиск RAG ----------
    def search(
        self,
        query: str | list[str],
        top_k: int = 6,
        min_score: float = 0.35,
    ) -> list[dict[str, Any]]:
        with self.driver.session() as s:
            rows = list(s.run(
                "MATCH (n:Entity {type: 'publication'}) "
                "WHERE n.rag_chunks IS NOT NULL AND n.status = 'ready' "
                "AND (n.attached = true OR n.attached IS NULL) "
                "AND (n.index_mode = 'full' OR n.index_mode IS NULL OR n.source_type IN ['file', 'link']) "
                "RETURN n"
            ))
        return self._search_chunks(rows, query, "rag_chunks", top_k, min_score)

    @staticmethod
    def _as_query_list(query: str | list[str]) -> list[str]:
        if isinstance(query, str):
            return [query.strip()] if query.strip() else []
        return [q.strip() for q in query if q and q.strip()]

    def _search_chunks(
        self,
        rows: list,
        query: str | list[str],
        chunks_field: str,
        top_k: int,
        min_score: float,
    ) -> list[dict[str, Any]]:
        queries = self._as_query_list(query)
        if not rows or not queries:
            return []

        all_chunks: list[dict[str, Any]] = []
        all_vecs: list[list[float]] = []
        docs: dict[str, DocumentMeta] = {}
        for row in rows:
            node = row["n"]
            doc_id = node["id"]
            docs[doc_id] = self._meta_from_node(node)
            raw = node.get(chunks_field)
            if not raw:
                continue
            for rec in json.loads(raw):
                all_chunks.append({
                    "id": rec["id"],
                    "doc_id": doc_id,
                    "text": rec["text"],
                    "location": rec["location"],
                    "language": rec["language"],
                })
                all_vecs.append(rec["embedding"])

        if not all_chunks:
            return []

        embeddings = np.asarray(all_vecs, dtype=np.float32)
        qvecs = self._embed(queries)
        # max score по всем формулировкам запроса на каждый чанк
        scores = embeddings @ qvecs.T
        max_scores = scores.max(axis=1) if scores.ndim > 1 else scores
        order = np.argsort(-max_scores)

        # Пул кандидатов, прошедших семантический порог (order отсортирован по
        # убыванию, поэтому на первом же чанке ниже min_score можно останавливаться).
        # Берём шире top_k, чтобы лексический буст мог поднять чанк с точным
        # числом/кодом/формулой, оказавшийся ниже по чистому вектору.
        pool: list[tuple[int, float]] = []
        for idx in order:
            vs = float(max_scores[int(idx)])
            if vs < min_score:
                break
            pool.append((int(idx), vs))
            if len(pool) >= top_k * POOL_MULT:
                break

        signals = extract_query_signals(queries)
        if not signals.empty and BOOST_WEIGHT > 0:
            # Переранжируем пул: итог = косинус + WEIGHT * лексическое совпадение.
            # Сам отчётный score оставляем косинусным (не ломаем калибровку confidence).
            pool.sort(
                key=lambda p: p[1] + BOOST_WEIGHT * lexical_score(signals, all_chunks[p[0]]["text"]),
                reverse=True,
            )

        results = []
        for idx, vs in pool[:top_k]:
            chunk = all_chunks[idx]
            results.append({
                "chunk": _ChunkView(chunk),
                "score": vs,
                "document": docs.get(chunk["doc_id"]),
            })
        return results

    def list_documents(self) -> list[DocumentMeta]:
        with self.driver.session() as s:
            rows = s.run(
                "MATCH (n:Entity {type: 'publication'}) "
                "WHERE n.source_type IS NOT NULL "
                "AND (n.attached = true OR (n.attached IS NULL AND n.source_type IN ['file', 'link'])) "
                "RETURN n"
            )
            metas = [self._meta_from_node(r["n"]) for r in rows]
        return sorted(metas, key=lambda d: d.added_at, reverse=True)

    def delete_document(self, doc_id: str) -> bool:
        node = self._get_node(doc_id)
        if not node:
            return False
        if node.get("source_type") == "corpus":
            abstract_chunks = node.get("abstract_rag_chunks") or node.get("rag_chunks")
            props = {
                "attached": False,
                "attach_source": "",
                "index_mode": "abstract",
            }
            if abstract_chunks:
                props["rag_chunks"] = abstract_chunks
                props["num_chunks"] = len(json.loads(abstract_chunks))
            self._update_node(doc_id, props)
            return True
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:Entity {id: $id, type: 'publication'}) WHERE n.source_type IS NOT NULL "
                "DETACH DELETE n RETURN count(n) AS c",
                id=doc_id,
            ).single()
        return bool(result and result["c"] > 0)


class _ChunkView:
    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError as e:
            raise AttributeError(name) from e
