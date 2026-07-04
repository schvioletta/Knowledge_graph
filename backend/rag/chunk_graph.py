"""Построение session-графа из RAG citation-чанков (ner_extract + GraphWriter).

Граф живёт только в ответе API (префикс rg_), не персистится в real_graph.json.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from backend.graph_store import GraphStore
from backend.llm_client import is_configured
from backend.nlp_pipeline.graph_writer import GraphWriter, _stable_id_num, infer_confidence
from backend.nlp_pipeline.ner_extract import ExtractionResult, extract_chunk_entities
from backend.nlp_pipeline.resolve import AliasTable, resolve_entity
from backend.nlp_pipeline.validate import validate_entity_attrs, validate_relation
from backend.rag.experiment_chains import append_chain_step_links, extract_experiment_chains
from backend.schema import Entity, EntityType, Relation, RelationType

_RG_PREFIX = "rg_"

# Тип ребра «внешняя публикация упоминает сущность графа». В schema.RelationType
# такого нет (там онтология экспериментов), а онтологию расширять ради session-
# графа не нужно — кладём ребро прямо в networkx со строковым типом (to_vis_json
# сериализует любой d["type"], фронт рисует незнакомый тип нейтральным стилем).
_EXTERNAL_LINK = "MENTIONS"


def _safe_pub_id(doc_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", doc_id)[:48]
    return f"{_RG_PREFIX}pub_{slug}"


def _external_pub_id(kind: str, item: dict[str, Any]) -> str:
    basis = item.get("url") or item.get("title") or ""
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", basis)[:48].strip("_")
    if not slug:
        slug = f"{_stable_id_num(basis) % 10_000_000:07d}"
    return f"{_RG_PREFIX}ext_{kind}_{slug}"


def _external_items(external: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    """Плоский список (kind, item) внешних источников из результата search_external."""
    if not external or not external.get("enabled"):
        return []
    items: list[tuple[str, dict[str, Any]]] = []
    for s in external.get("scholar") or []:
        items.append(("scholar", s))
    for p in external.get("patents") or []:
        items.append(("patent", p))
    return items


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

    def add_external_source(
        self, kind: str, item: dict[str, Any], name_to_id: dict[str, str]
    ) -> bool:
        """Добавляет внешний источник (Scholar/Patent) как узел-публикацию и
        связывает его рёбрами MENTIONS с уже извлечёнными сущностями графа по
        ключевым словам находки (matched_keywords). Возвращает True, если узел
        создан. NER по сниппету не гоняем — связь по ключевым словам даёт
        достаточную привязку без лишних LLM-вызовов на каждый внешний источник."""
        title = (item.get("title") or "").strip()
        url = item.get("url") or ""
        if not title and not url:
            return False  # мусорная запись без названия и ссылки — пропускаем

        pub_id = _external_pub_id(kind, item)
        if self.gs.node(pub_id):
            return False

        self.gs.add_entity(Entity(
            id=pub_id,
            type=EntityType.PUBLICATION,
            name=title or "(без названия)",
            attrs={
                # origin отличает внешние публикации от загруженных пользователем
                # (у тех origin нет) — по нему фронт/детали могут показать бейдж.
                "origin": kind,                       # "scholar" | "patent"
                "url": url,
                "authors": item.get("authors") or [],
                "year": item.get("year"),
                "venue": item.get("venue") or "",     # журнал/конференция или номер патента
                "snippet": item.get("snippet") or "",
                "matched_keywords": item.get("matched_keywords") or [],
                "relevance": item.get("relevance"),
                "source_file": item.get("venue") or url,
                "date": str(item.get("year") or ""),
                "confidence": "внешний источник",
                "sources": [url or item.get("venue") or ""],
            },
        ))
        self.stats["entities_created"] += 1

        linked: set[str] = set()
        for kw in item.get("matched_keywords") or []:
            tgt = name_to_id.get(kw.lower())
            if tgt and tgt not in linked:
                # Ребро кладём напрямую в networkx: тип строковый (_EXTERNAL_LINK),
                # вне онтологии RelationType, поэтому через Relation/add_relation не идём.
                self.gs.g.add_edge(pub_id, tgt, key=_EXTERNAL_LINK,
                                   type=_EXTERNAL_LINK, keyword=kw)
                linked.add(tgt)
                self.stats["relations"] += 1
        return True

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


@dataclass
class ChunkGraphBuild:
    """Промежуточное состояние session-графа между фазами: внутренний build →
    (highlight → внешний поиск) → добавление внешних источников → finalize.
    Разделение нужно, чтобы внутренний LLM-NER выполнялся ровно один раз, а
    внешние источники (дешёвая привязка по ключевым словам) добавлялись поверх
    уже готового внутреннего графа, не пересчитывая его."""

    gs: GraphStore
    writer: RagChunkGraphWriter
    chunks_processed: int = 0
    llm_skipped: bool = False
    external_pubs: int = 0


def _empty_graph() -> dict[str, Any]:
    return {
        "subgraph": {"nodes": [], "links": []},
        "node_ids": [],
        "stats": {"entities": 0, "relations": 0, "chunks": 0, "publications": 0, "external_pubs": 0},
        "experiment_chains": [],
    }


def build_internal_graph(hits: list[dict[str, Any]]) -> ChunkGraphBuild:
    """Фаза 1: строит граф из внутренних RAG-hits (LLM-NER по чанкам)."""
    gs = GraphStore()
    alias = AliasTable(":memory:")
    writer = RagChunkGraphWriter(gs, alias)
    build = ChunkGraphBuild(gs=gs, writer=writer, llm_skipped=not is_configured())

    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        by_doc[hit["chunk"].doc_id].append(hit)

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
            build.chunks_processed += 1

        if results:
            writer.write_chunk_results(pub_id, source_name, results)

    return build


def add_external_sources(build: ChunkGraphBuild, external: dict[str, Any] | None) -> None:
    """Фаза 2 (опционально): добавляет внешние источники Scholar/Patents как
    узлы-публикации, связывая их с уже извлечёнными сущностями графа по ключевым
    словам находки. Дёшево (без LLM), не трогает внутренние узлы."""
    ext_sources = _external_items(external)
    if not ext_sources:
        return
    # Карта имя→id по внутренним сущностям (без публикаций) — цели рёбер MENTIONS.
    name_to_id = {
        (d.get("name") or "").lower(): n
        for n, d in build.gs.g.nodes(data=True)
        if d.get("type") != EntityType.PUBLICATION.value and d.get("name")
    }
    for kind, item in ext_sources:
        if build.writer.add_external_source(kind, item, name_to_id):
            build.external_pubs += 1


def finalize_graph(build: ChunkGraphBuild) -> dict[str, Any]:
    """Фаза 3: цепочки экспериментов, сериализация subgraph и статистика."""
    gs, writer = build.gs, build.writer
    experiment_chains = extract_experiment_chains(gs)
    subgraph = append_chain_step_links(gs.to_vis_json(), experiment_chains)
    node_ids = [n["id"] for n in subgraph["nodes"]]
    entity_count = sum(1 for n in subgraph["nodes"] if n.get("type") != EntityType.PUBLICATION.value)
    pub_count = sum(1 for n in subgraph["nodes"] if n.get("type") == EntityType.PUBLICATION.value)

    stats: dict[str, Any] = {
        "entities": entity_count,
        "relations": writer.stats["relations"],
        "chunks": build.chunks_processed,
        "publications": pub_count,
        "external_pubs": build.external_pubs,
    }
    if build.llm_skipped:
        stats["llm_skipped"] = True

    return {
        "subgraph": subgraph,
        "node_ids": node_ids,
        "stats": stats,
        "experiment_chains": experiment_chains,
    }


def build_graph_from_hits(
    hits: list[dict[str, Any]], external: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Строит merged subgraph из RAG hits (+ опционально внешних источников).
    Удобный однократный вызов для случаев, когда highlight-сущности между фазами
    не нужны (напр. ветка «внутренних фрагментов не нашлось»)."""
    if not hits and not _external_items(external):
        return _empty_graph()
    build = build_internal_graph(hits)
    add_external_sources(build, external)
    return finalize_graph(build)
