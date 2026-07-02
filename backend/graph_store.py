"""In-memory knowledge graph поверх NetworkX с сохранением в JSON."""
from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from backend.schema import Entity, EntityType, Relation, RelationType


class GraphStore:
    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()

    # ---------- построение ----------
    def add_entity(self, entity: Entity) -> None:
        self.g.add_node(entity.id, type=entity.type.value, name=entity.name, **entity.attrs)

    def add_relation(self, relation: Relation) -> None:
        self.g.add_edge(
            relation.source,
            relation.target,
            key=relation.type.value,
            type=relation.type.value,
            **relation.attrs,
        )

    # ---------- персистентность ----------
    def save(self, path: str | Path) -> None:
        data = nx.node_link_data(self.g, edges="links")
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: str | Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.g = nx.node_link_graph(data, edges="links", multigraph=True, directed=True)

    # ---------- базовые выборки ----------
    def entities_by_type(self, etype: EntityType) -> list[dict[str, Any]]:
        return [
            {"id": n, **d}
            for n, d in self.g.nodes(data=True)
            if d.get("type") == etype.value
        ]

    def find_by_name(self, query: str, etypes: Optional[list[EntityType]] = None) -> list[dict[str, Any]]:
        q = query.lower().strip()
        if not q:
            return []
        allowed = {t.value for t in etypes} if etypes else None
        hits = []
        for n, d in self.g.nodes(data=True):
            if allowed and d.get("type") not in allowed:
                continue
            name = str(d.get("name", "")).lower()
            if q in name or name in q:
                hits.append({"id": n, **d})
        return hits

    def node(self, node_id: str) -> Optional[dict[str, Any]]:
        if node_id not in self.g:
            return None
        return {"id": node_id, **self.g.nodes[node_id]}

    def neighbors_subgraph(self, node_id: str, depth: int = 1) -> nx.MultiDiGraph:
        if node_id not in self.g:
            return nx.MultiDiGraph()
        nodes = {node_id}
        frontier = {node_id}
        undirected = self.g.to_undirected(as_view=True)
        for _ in range(depth):
            nxt = set()
            for n in frontier:
                nxt |= set(undirected.neighbors(n))
            frontier = nxt - nodes
            nodes |= nxt
        return self.g.subgraph(nodes)

    # ---------- предметные запросы ----------
    ENTITY_RELATION: dict[EntityType, RelationType] = {
        EntityType.MATERIAL: RelationType.USES_MATERIAL,
        EntityType.PROCESS: RelationType.USES_PROCESS,
        EntityType.CONDITION: RelationType.AT_CONDITION,
        EntityType.EQUIPMENT: RelationType.ON_EQUIPMENT,
        EntityType.FACILITY: RelationType.AT_FACILITY,
        EntityType.PROPERTY: RelationType.MEASURES_PROPERTY,
    }

    def query_experiments(self, **filters: Optional[str]) -> list[dict[str, Any]]:
        """Находит эксперименты по фильтрам вида material=..., process=..., condition=...,
        equipment=..., facility=..., prop=... (нечёткое совпадение по имени связанной сущности).
        Дополнительно можно передать numeric_filters=[(attr_key, op, value), ...] и
        country="RU"/"INTL" — они проверяются по attrs самого эксперимента.
        """
        numeric_filters = filters.pop("numeric_filters", None) or []
        country = filters.pop("country", None)

        def matches_neighbor(exp_id: str, rel_type: str, name_query: str | list[str]) -> bool:
            queries = [name_query] if isinstance(name_query, str) else name_query
            for nq in queries:
                nq = nq.lower()
                for _, tgt, data in self.g.out_edges(exp_id, data=True):
                    if data.get("type") == rel_type:
                        tname = str(self.g.nodes[tgt].get("name", "")).lower()
                        if nq in tname or tname in nq:
                            return True
            return False

        def matches_numeric(attrs: dict[str, Any], key: str, op: str, value: float) -> bool:
            actual = attrs.get(key)
            if actual is None:
                return False
            actual = float(actual)
            return {
                "<=": actual <= value,
                "<": actual < value,
                ">=": actual >= value,
                ">": actual > value,
                "=": actual == value,
            }.get(op, False)

        rel_by_type = {t.value: rel.value for t, rel in self.ENTITY_RELATION.items()}
        key_to_rel = {
            "material": rel_by_type[EntityType.MATERIAL.value],
            "process": rel_by_type[EntityType.PROCESS.value],
            "condition": rel_by_type[EntityType.CONDITION.value],
            "equipment": rel_by_type[EntityType.EQUIPMENT.value],
            "facility": rel_by_type[EntityType.FACILITY.value],
            "prop": rel_by_type[EntityType.PROPERTY.value],
        }

        results = []
        for n, d in self.g.nodes(data=True):
            if d.get("type") != EntityType.EXPERIMENT.value:
                continue
            ok = True
            for key, rel in key_to_rel.items():
                val = filters.get(key)
                if val and not matches_neighbor(n, rel, val):
                    ok = False
                    break
            if not ok:
                continue
            if country and str(d.get("country", "")).upper() != country.upper():
                continue
            if numeric_filters and not all(matches_numeric(d, k, op, v) for k, op, v in numeric_filters):
                continue
            results.append({"id": n, **d})
        return results

    def experiment_detail(self, exp_id: str) -> dict[str, Any]:
        detail: dict[str, Any] = {"id": exp_id, **self.g.nodes.get(exp_id, {})}
        for src, tgt, data in self.g.out_edges(exp_id, data=True):
            rel = data.get("type")
            target_node = {"id": tgt, **self.g.nodes[tgt]}
            detail.setdefault(rel, []).append(target_node)
        for src, tgt, data in self.g.in_edges(exp_id, data=True):
            rel = data.get("type")
            source_node = {"id": src, **self.g.nodes[src]}
            detail.setdefault(f"incoming::{rel}", []).append(source_node)
        return detail

    # ---------- анализ пробелов ----------
    def gap_matrix(
        self,
        x_type: EntityType = EntityType.MATERIAL,
        y_type: EntityType = EntityType.CONDITION,
    ) -> dict[str, Any]:
        xs = self.entities_by_type(x_type)
        ys = self.entities_by_type(y_type)
        rel_x = self.ENTITY_RELATION[x_type].value
        rel_y = self.ENTITY_RELATION[y_type].value

        experiments = self.entities_by_type(EntityType.EXPERIMENT)
        counts: dict[tuple[str, str], int] = {}
        for exp in experiments:
            exp_id = exp["id"]
            x_ids = [tgt for _, tgt, d in self.g.out_edges(exp_id, data=True) if d.get("type") == rel_x]
            y_ids = [tgt for _, tgt, d in self.g.out_edges(exp_id, data=True) if d.get("type") == rel_y]
            for xi, yi in itertools.product(x_ids, y_ids):
                counts[(xi, yi)] = counts.get((xi, yi), 0) + 1

        cells = []
        gaps = []
        for x in xs:
            for y in ys:
                c = counts.get((x["id"], y["id"]), 0)
                cell = {"x_id": x["id"], "x_name": x["name"], "y_id": y["id"], "y_name": y["name"], "count": c}
                cells.append(cell)
                if c == 0:
                    gaps.append(cell)
        return {
            "x_type": x_type.value,
            "y_type": y_type.value,
            "x_axis": [{"id": x["id"], "name": x["name"]} for x in xs],
            "y_axis": [{"id": y["id"], "name": y["name"]} for y in ys],
            "cells": cells,
            "gaps": gaps,
        }

    def contradictions_for(self, conclusion_ids: list[str]) -> list[dict[str, Any]]:
        found = []
        ids = set(conclusion_ids)
        for u, v, d in self.g.edges(data=True):
            if d.get("type") == RelationType.CONTRADICTS.value and (u in ids or v in ids):
                found.append({
                    "a": {"id": u, **self.g.nodes[u]},
                    "b": {"id": v, **self.g.nodes[v]},
                    "note": d.get("note", ""),
                })
        return found

    # ---------- экспорт для визуализации ----------
    def to_vis_json(self, subgraph: Optional[nx.MultiDiGraph] = None) -> dict[str, Any]:
        sg = subgraph if subgraph is not None else self.g
        degree = dict(self.g.to_undirected(as_view=True).degree())
        nodes = [
            {
                "id": n,
                "type": d.get("type"),
                "name": d.get("name"),
                "degree": degree.get(n, 0),
                "attrs": {k: v for k, v in d.items() if k not in ("type", "name")},
            }
            for n, d in sg.nodes(data=True)
        ]
        links = [
            {"source": u, "target": v, "type": d.get("type"), "attrs": {k: val for k, val in d.items() if k != "type"}}
            for u, v, d in sg.edges(data=True)
        ]
        return {"nodes": nodes, "links": links}
