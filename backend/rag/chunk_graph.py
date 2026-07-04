"""Построение session-графа из RAG citation-чанков (ner_extract + GraphWriter).

Граф живёт только в ответе API (префикс rg_), не персистится в real_graph.json.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from backend.graph_store import GraphStore
from backend.llm_client import is_configured
from backend.nlp_pipeline.graph_writer import GraphWriter, _stable_id_num, infer_confidence
from backend.nlp_pipeline.ner_extract import ExtractionResult, extract_chunk_entities
from backend.nlp_pipeline.resolve import AliasTable, resolve_entity
from backend.nlp_pipeline.validate import validate_entity_attrs, validate_relation
from backend.schema import Entity, EntityType, Relation, RelationType

_RG_PREFIX = "rg_"


def _safe_pub_id(doc_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", doc_id)[:48]
    return f"{_RG_PREFIX}pub_{slug}"


class RagChunkGraphWriter(GraphWriter):
    """GraphWriter с префиксом rg_ на id сущностей — без коллизий с demo-графом."""

    def ensure_publication(self, pub_id: str, title: str, source_name: str) -> None:
        if self.gs.node(pub_id):
            return
        self.gs.add_entity(Entity(
            id=pub_id,
            type=EntityType.PUBLICATION,
            name=title,
            attrs={
                "source_file": source_name,
                "date": "",
                "confidence": "не проверено",
                "sources": [source_name],
            },
        ))
        self.stats["entities_created"] += 1

    def write_chunk_results(
        self,
        pub_id: str,
        source_name: str,
        results: list[ExtractionResult],
    ) -> None:
        for result in results:
            tmp_to_real: dict[str, str] = {"pub": pub_id}
            for e in result.entities:
                real_id = self._upsert_entity(e.type.value, e.name, e.attrs, source_name)
                tmp_to_real[e.tmp_id] = real_id
            for r in result.relations:
                src = tmp_to_real.get(r.source)
                tgt = tmp_to_real.get(r.target)
                if not src or not tgt:
                    continue
                src_node = self.gs.node(src)
                tgt_node = self.gs.node(tgt)
                if not src_node or not tgt_node:
                    continue
                issues = validate_relation(EntityType(src_node["type"]), EntityType(tgt_node["type"]), r.type)
                if issues:
                    self.stats["validation_warnings"] += len(issues)
                    continue
                self.gs.add_relation(Relation(source=src, target=tgt, type=r.type, attrs=r.attrs))
                self.stats["relations"] += 1
                if r.type == RelationType.PRODUCES_CONCLUSION:
                    self._flag_similar_conclusions(tgt)

    def _upsert_entity(self, etype: str, name: str, attrs: dict[str, Any], source_file: str) -> str:
        existing_id = resolve_entity(self.gs, self.alias, etype, name)
        if existing_id:
            node = self.gs.g.nodes[existing_id]
            sources = list(node.get("sources", []))
            if source_file not in sources:
                sources.append(source_file)
            node["sources"] = sources
            from backend.nlp_pipeline.graph_writer import _apply_attrs_with_history
            _apply_attrs_with_history(node, attrs, source_file)
            node["confidence"] = infer_confidence(node, sources)
            self.stats["entities_reused"] += 1
            return existing_id

        real_id = f"{_RG_PREFIX}{etype}_{_stable_id_num(name) % 10_000_000:07d}"
        full_attrs = dict(attrs)
        full_attrs["source_file"] = source_file
        full_attrs["sources"] = [source_file]
        validate_entity_attrs(EntityType(etype), full_attrs)
        full_attrs.setdefault("date", "")
        full_attrs["confidence"] = infer_confidence(full_attrs, full_attrs["sources"])
        self.gs.add_entity(Entity(id=real_id, type=EntityType(etype), name=name, attrs=full_attrs))
        self.alias.register(etype, name, real_id)
        self.stats["entities_created"] += 1
        return real_id


def build_graph_from_hits(hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Строит merged subgraph из RAG hits (результат store.search)."""
    if not hits:
        return {
            "subgraph": {"nodes": [], "links": []},
            "node_ids": [],
            "stats": {"entities": 0, "relations": 0, "chunks": 0, "publications": 0},
        }

    gs = GraphStore()
    alias = AliasTable(":memory:")
    writer = RagChunkGraphWriter(gs, alias)

    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        chunk = hit["chunk"]
        by_doc[chunk.doc_id].append(hit)

    chunks_processed = 0
    llm_skipped = not is_configured()

    for doc_id, doc_hits in by_doc.items():
        doc = doc_hits[0].get("document")
        title = doc.title if doc else doc_id
        source_name = doc.source_name if doc else doc_id
        pub_id = _safe_pub_id(doc_id)
        writer.ensure_publication(pub_id, title, source_name)

        results: list[ExtractionResult] = []
        for hit in doc_hits:
            text = hit["chunk"].text
            if not text.strip():
                continue
            results.append(extract_chunk_entities(text))
            chunks_processed += 1

        if results:
            writer.write_chunk_results(pub_id, source_name, results)

    subgraph = gs.to_vis_json()
    node_ids = [n["id"] for n in subgraph["nodes"]]
    entity_count = sum(1 for n in subgraph["nodes"] if n.get("type") != EntityType.PUBLICATION.value)
    pub_count = sum(1 for n in subgraph["nodes"] if n.get("type") == EntityType.PUBLICATION.value)

    stats: dict[str, Any] = {
        "entities": entity_count,
        "relations": writer.stats["relations"],
        "chunks": chunks_processed,
        "publications": pub_count,
    }
    if llm_skipped:
        stats["llm_skipped"] = True

    return {"subgraph": subgraph, "node_ids": node_ids, "stats": stats}
