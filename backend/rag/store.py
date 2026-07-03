"""Хранилище загруженных документов и внешних ссылок для RAG-чата.

Сознательно отделено от NLP-пайплайна (backend/nlp_pipeline/) и графа знаний:
там текст проходит через LLM-экстракцию в сущности/связи графа, здесь же
исходные фрагменты текста остаются как есть и ищутся по смысловой близости
(локальные эмбеддинги sentence-transformers, без внешнего сервера векторной
БД — это демо-масштаб, сотни-тысячи чанков, косинусный поиск в numpy
достаточно быстр и не требует поднимать инфраструктуру). Это даёт то, чего
не может дать граф-поиск: точную цитату конкретного фрагмента документа
(файл + страница/абзац) под каждым утверждением ответа.

Переиспользует ingest.py/chunking.py из nlp_pipeline — те же загрузчики
docx/pptx/pdf/txt (с OCR для сканов) и тот же алгоритм чанкинга по смысловым
блокам с определением языка на уровне абзаца.
"""
from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

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


@dataclass
class ChunkRecord:
    id: str
    doc_id: str
    text: str
    location: str
    language: str


class DocumentStore:
    def __init__(self, data_dir: str | Path = "data/rag"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._docs_path = self.data_dir / "documents.json"
        self._chunks_path = self.data_dir / "chunks.json"
        self._embeddings_path = self.data_dir / "embeddings.npy"

        self.documents: dict[str, DocumentMeta] = {}
        self.chunks: list[ChunkRecord] = []
        self.embeddings: np.ndarray = np.zeros((0, _EMBED_DIM), dtype=np.float32)
        self._model = None  # ленивая загрузка — не тормозит старт бэкенда, если RAG не используется

        self._load()

    # ---------- персистентность ----------
    def _load(self) -> None:
        if self._docs_path.exists():
            raw = json.loads(self._docs_path.read_text(encoding="utf-8"))
            self.documents = {d["id"]: DocumentMeta(**d) for d in raw}
        if self._chunks_path.exists():
            raw = json.loads(self._chunks_path.read_text(encoding="utf-8"))
            self.chunks = [ChunkRecord(**c) for c in raw]
        if self._embeddings_path.exists():
            self.embeddings = np.load(self._embeddings_path)

    def _save(self) -> None:
        self._docs_path.write_text(
            json.dumps([asdict(d) for d in self.documents.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._chunks_path.write_text(
            json.dumps([asdict(c) for c in self.chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        np.save(self._embeddings_path, self.embeddings)

    # ---------- модель эмбеддингов ----------
    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(_MODEL_NAME)
        return self._model

    def _embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)

    # ---------- запись ----------
    def add_document(self, title: str, source_type: str, source_name: str, blocks: list[TextBlock]) -> DocumentMeta:
        doc_id = uuid.uuid4().hex[:12]
        chunks = chunk_blocks(blocks)

        if not chunks:
            meta = DocumentMeta(
                id=doc_id, title=title, source_type=source_type, source_name=source_name,
                added_at=_now(), num_chunks=0, status="error",
                error="Не удалось извлечь текст (пустой документ или нераспознанный формат)",
            )
            self.documents[doc_id] = meta
            self._save()
            return meta

        vecs = self._embed([c.text for c in chunks])
        records = [
            ChunkRecord(
                id=f"{doc_id}_{i}", doc_id=doc_id, text=c.text,
                location=", ".join(c.locations), language=c.language,
            )
            for i, c in enumerate(chunks)
        ]

        self.chunks.extend(records)
        self.embeddings = np.vstack([self.embeddings, vecs])

        meta = DocumentMeta(
            id=doc_id, title=title, source_type=source_type, source_name=source_name,
            added_at=_now(), num_chunks=len(records), status="ready",
        )
        self.documents[doc_id] = meta
        self._save()
        return meta

    # ---------- поиск ----------
    def search(self, query: str, top_k: int = 6, min_score: float = 0.35) -> list[dict[str, Any]]:
        if not self.chunks or self.embeddings.shape[0] == 0:
            return []
        qvec = self._embed([query])[0]
        scores = self.embeddings @ qvec  # эмбеддинги нормированы -> это косинусное сходство
        top_idx = np.argsort(-scores)[:top_k]

        results = []
        for idx in top_idx:
            score = float(scores[idx])
            if score < min_score:
                continue
            chunk = self.chunks[int(idx)]
            results.append({
                "chunk": chunk,
                "score": score,
                "document": self.documents.get(chunk.doc_id),
            })
        return results

    def list_documents(self) -> list[DocumentMeta]:
        return sorted(self.documents.values(), key=lambda d: d.added_at, reverse=True)
