"""Этап 5: запись провалидированных фактов в GraphStore.

- confidence не берётся «с потолка»: эвристика — «высокая», если факт подтверждён
  явным числом (attrs с ключом из численной конвенции проекта) и подтверждён
  ≥2 независимыми источниками (attrs["sources"] копится при повторных упоминаниях
  той же сущности в разных документах); «низкая» — единичное упоминание без чисел;
  иначе «средняя».
- версионирование фактов (_apply_attrs_with_history): при повторном упоминании
  сущности в новом документе с ДРУГИМ значением того же атрибута новое значение
  теперь обновляет факт (раньше молча отбрасывалось через setdefault — первый
  источник навсегда «замораживал» значение), а расхождение фиксируется в
  node["_history"] для аудита.
- после вставки эксперимента/вывода сразу прогоняется gs.contradictions_for()
  по явным связям CONTRADICTS (если экстрактор их вернул), а также
  полуавтоматическое сравнение нового Conclusion с существующими на той же
  связке Material+Process (через сходство текста, без embeddings) — раз ролевой
  модели и ручного review ещё нет, такие пары помечаются NEEDS_REVIEW, а не
  сразу перезаписываются в CONTRADICTS.
"""
from __future__ import annotations

import datetime
import difflib
import hashlib
from pathlib import Path
from typing import Any

from backend.graph_store import GraphStore
from backend.nlp_pipeline.chunking import Chunk
from backend.nlp_pipeline.llm_log import MAX_CONTEXTS_PER_NODE, truncate_snippet
from backend.nlp_pipeline.ner_extract import ExtractionResult
from backend.nlp_pipeline.resolve import AliasTable, resolve_entity
from backend.nlp_pipeline.validate import validate_entity_attrs, validate_relation
from backend.schema import Entity, EntityType, Relation, RelationType

_NUMERIC_HINT_SUFFIXES = (
    "_mg_l", "_pct", "_m3_h", "_a_m2", "_musd", "_m3_day", "_m", "_c", "_h", "_mpa",
)

# Технические ключи узла, которые не являются «фактами» из документа и не должны
# версионироваться через _apply_attrs_with_history (у них своя логика обновления).
_NON_FACT_KEYS = frozenset({"source_file", "sources", "confidence", "date", "source_contexts"})


def _context_key(ctx: dict[str, Any]) -> tuple[str, int]:
    return str(ctx.get("source_file", "")), int(ctx.get("chunk_index", 0))


def _append_source_context(container: dict[str, Any], ctx: dict[str, Any], label: str = "node") -> None:
    contexts: list[dict[str, Any]] = container.setdefault("source_contexts", [])
    key = _context_key(ctx)
    if any(_context_key(c) == key for c in contexts):
        return
    if len(contexts) >= MAX_CONTEXTS_PER_NODE:
        print(
            f"[graph_writer] source_contexts limit ({MAX_CONTEXTS_PER_NODE}) для {label} "
            f"({ctx.get('source_file')}, chunk {ctx.get('chunk_index')})",
            flush=True,
        )
        return
    contexts.append(ctx)


def _make_source_context(chunk: Chunk, meta, chunk_index: int) -> dict[str, Any]:
    return {
        "source_file": meta.source_file,
        "chunk_index": chunk_index,
        "locations": list(chunk.locations),
        "language": chunk.language,
        "kind": chunk.kind,
        "text": truncate_snippet(chunk.text, 500),
    }


def _apply_attrs_with_history(node: dict[str, Any], attrs: dict[str, Any], source_file: str) -> None:
    """Версионирование фактов: раньше повторное упоминание сущности в новом
    документе с ДРУГИМ значением того же атрибута молча отбрасывалось
    (node.setdefault) — первый источник навсегда «замораживал» значение, даже
    если новый источник его уточнял или опровергал. Теперь новое значение
    обновляет факт (последний источник считается самым свежим знанием), а
    расхождение фиксируется в node['_history'] — кто/когда/что изменил,
    чтобы это можно было показать эксперту, а не потерять."""
    history = node.get("_history", [])
    for k, v in attrs.items():
        if k in _NON_FACT_KEYS:
            continue
        existing = node.get(k)
        if existing is None:
            node[k] = v
        elif existing != v:
            history.append({
                "attr": k,
                "old_value": existing,
                "new_value": v,
                "source_file": source_file,
                "changed_at": datetime.date.today().isoformat(),
            })
            node[k] = v
    if history:
        node["_history"] = history


def _stable_id_num(s: str) -> int:
    """Детерминированная замена встроенному hash(): у Python str-хэш рандомизирован
    per-process (PYTHONHASHSEED), поэтому id, построенные на hash(), не совпадают
    между запусками пайплайна — повторный прогон на том же файле/имени сущности
    получал бы каждый раз новый id и плодил дубли узлов вместо апдейта существующего."""
    return int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16)


def _has_numeric_evidence(attrs: dict[str, Any]) -> bool:
    return any(
        isinstance(v, (int, float)) and any(k.endswith(suf) for suf in _NUMERIC_HINT_SUFFIXES)
        for k, v in attrs.items()
    )


def infer_confidence(attrs: dict[str, Any], sources: list[str]) -> str:
    n_sources = len(set(sources))
    if _has_numeric_evidence(attrs) and n_sources >= 2:
        return "высокая"
    if not _has_numeric_evidence(attrs) and n_sources <= 1:
        return "низкая"
    return "средняя"


class GraphWriter:
    def __init__(self, gs: GraphStore, alias_table: AliasTable):
        self.gs = gs
        self.alias = alias_table
        self.stats = {"entities_created": 0, "entities_reused": 0, "relations": 0, "validation_warnings": 0, "needs_review": 0}

    def write_document(
        self,
        path: str,
        meta,
        chunk_results: list[tuple[Chunk, ExtractionResult]],
    ) -> str:
        pub_id = f"pub_{Path(path).stem}_{_stable_id_num(path) % 10_000:04d}"
        title = Path(path).stem.replace("_", " ")
        self.gs.add_entity(Entity(
            id=pub_id, type=EntityType.PUBLICATION, name=title,
            attrs={"source_file": meta.source_file, "date": meta.modified, "confidence": "не проверено"},
        ))

        for chunk_index, (chunk, result) in enumerate(chunk_results, start=1):
            source_context = _make_source_context(chunk, meta, chunk_index)
            tmp_to_real: dict[str, str] = {"pub": pub_id}

            for e in result.entities:
                real_id = self._upsert_entity(
                    e.type.value, e.name, e.attrs, meta.source_file, source_context=source_context,
                )
                tmp_to_real[e.tmp_id] = real_id

            for r in result.relations:
                src = tmp_to_real.get(r.source)
                tgt = tmp_to_real.get(r.target)
                if not src or not tgt:
                    continue
                src_type = self.gs.node(src)["type"]
                tgt_type = self.gs.node(tgt)["type"]
                issues = validate_relation(EntityType(src_type), EntityType(tgt_type), r.type)
                if issues:
                    self.stats["validation_warnings"] += len(issues)
                    continue
                self._add_relation_with_context(src, tgt, r.type, r.attrs, source_context)
                self.stats["relations"] += 1

                if r.type == RelationType.PRODUCES_CONCLUSION:
                    self._flag_similar_conclusions(tgt)

        return pub_id

    def _add_relation_with_context(
        self,
        src: str,
        tgt: str,
        rel_type: RelationType,
        attrs: dict[str, Any],
        source_context: dict[str, Any],
    ) -> None:
        key = rel_type.value
        if self.gs.g.has_edge(src, tgt, key=key):
            edge_data = self.gs.g.edges[src, tgt, key]
            merged = dict(attrs)
            for k, v in edge_data.items():
                if k not in ("type",) and k not in merged:
                    merged[k] = v
            _append_source_context(merged, source_context, label=f"edge {src}->{tgt}")
            for k, v in merged.items():
                edge_data[k] = v
            return

        rel_attrs = dict(attrs)
        _append_source_context(rel_attrs, source_context, label=f"edge {src}->{tgt}")
        self.gs.add_relation(Relation(source=src, target=tgt, type=rel_type, attrs=rel_attrs))

    def _upsert_entity(
        self,
        etype: str,
        name: str,
        attrs: dict[str, Any],
        source_file: str,
        *,
        source_context: dict[str, Any],
    ) -> str:
        existing_id = resolve_entity(self.gs, self.alias, etype, name)
        if existing_id:
            node = self.gs.g.nodes[existing_id]
            sources = list(node.get("sources", []))
            if source_file not in sources:
                sources.append(source_file)
            node["sources"] = sources
            _apply_attrs_with_history(node, attrs, source_file)
            _append_source_context(node, source_context, label=f"{etype}:{name}")
            node["confidence"] = infer_confidence(node, sources)
            self.stats["entities_reused"] += 1
            return existing_id

        real_id = f"{etype}_{_stable_id_num(name) % 10_000_000:07d}"
        full_attrs = dict(attrs)
        full_attrs["source_file"] = source_file
        full_attrs["sources"] = [source_file]
        full_attrs["source_contexts"] = [source_context]
        issues = validate_entity_attrs(EntityType(etype), full_attrs)
        self.stats["validation_warnings"] += len(issues)
        full_attrs.setdefault("date", "")
        full_attrs["confidence"] = infer_confidence(full_attrs, full_attrs["sources"])
        self.gs.add_entity(Entity(id=real_id, type=EntityType(etype), name=name, attrs=full_attrs))
        self.alias.register(etype, name, real_id)
        self.stats["entities_created"] += 1
        return real_id

    def _flag_similar_conclusions(self, conclusion_id: str, similarity_range: tuple[float, float] = (0.2, 0.85)) -> None:
        """Ищет другие Conclusion, привязанные к экспериментам с тем же Material+Process,
        и при умеренном текстовом сходстве (не дубликат, не явное совпадение) помечает
        пару NEEDS_REVIEW — кандидат на ручную проверку экспертом."""
        gs = self.gs
        exp_ids = [src for src, tgt, d in gs.g.in_edges(conclusion_id, data=True) if d.get("type") == RelationType.PRODUCES_CONCLUSION.value]
        if not exp_ids:
            return
        exp_id = exp_ids[0]
        mat_ids = {tgt for _, tgt, d in gs.g.out_edges(exp_id, data=True) if d.get("type") == RelationType.USES_MATERIAL.value}
        proc_ids = {tgt for _, tgt, d in gs.g.out_edges(exp_id, data=True) if d.get("type") == RelationType.USES_PROCESS.value}
        if not mat_ids or not proc_ids:
            return

        this_text = gs.g.nodes[conclusion_id].get("name", "")
        for other_exp, d in gs.g.nodes(data=True):
            if d.get("type") != EntityType.EXPERIMENT.value or other_exp == exp_id:
                continue
            other_mats = {tgt for _, tgt, dd in gs.g.out_edges(other_exp, data=True) if dd.get("type") == RelationType.USES_MATERIAL.value}
            other_procs = {tgt for _, tgt, dd in gs.g.out_edges(other_exp, data=True) if dd.get("type") == RelationType.USES_PROCESS.value}
            if not (mat_ids & other_mats) or not (proc_ids & other_procs):
                continue
            for _, other_concl, dd in gs.g.out_edges(other_exp, data=True):
                if dd.get("type") != RelationType.PRODUCES_CONCLUSION.value:
                    continue
                other_text = gs.g.nodes[other_concl].get("name", "")
                if not other_text or other_concl == conclusion_id:
                    continue
                if gs.g.has_edge(conclusion_id, other_concl) or gs.g.has_edge(other_concl, conclusion_id):
                    continue
                ratio = difflib.SequenceMatcher(None, this_text, other_text).ratio()
                if similarity_range[0] <= ratio <= similarity_range[1]:
                    gs.add_relation(Relation(
                        source=conclusion_id, target=other_concl, type=RelationType.NEEDS_REVIEW,
                        attrs={"similarity": round(ratio, 2), "note": "Похожая комбинация материал+процесс, требует ручной проверки эксперта"},
                    ))
                    self.stats["needs_review"] += 1
