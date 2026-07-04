"""Линейные цепочки «материал → процесс → оборудование → результат» через узел experiment.

Граф хранит звезду от experiment (USES_MATERIAL, USES_PROCESS, …); здесь собираем
читаемые цепочки и опциональные CHAIN_STEP-рёбра для визуализации.
"""
from __future__ import annotations

from typing import Any

from backend.graph_store import GraphStore
from backend.schema import EntityType, RelationType

_STEP_KEYS = ("material", "process", "equipment", "result")
_STEP_LABELS = {
    "material": "Материал",
    "process": "Процесс",
    "equipment": "Оборудование",
    "result": "Результат",
}


def _neighbors_by_rel(gs: GraphStore, exp_id: str, rel_type: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _, tgt, data in gs.g.out_edges(exp_id, data=True):
        if data.get("type") != rel_type:
            continue
        node = gs.node(tgt)
        if not node:
            continue
        out.append({"id": tgt, "name": node.get("name", ""), "type": node.get("type")})
    return out


def _publication_for_experiment(gs: GraphStore, exp_id: str) -> dict[str, Any] | None:
    for src, _, data in gs.g.in_edges(exp_id, data=True):
        if data.get("type") != RelationType.DESCRIBES_EXPERIMENT.value:
            continue
        node = gs.node(src)
        if node and node.get("type") == EntityType.PUBLICATION.value:
            return {"id": src, "name": node.get("name", "")}
    return None


def extract_experiment_chains(gs: GraphStore) -> list[dict[str, Any]]:
    """Собирает цепочки по каждому experiment с хотя бы одним шагом цепи."""
    chains: list[dict[str, Any]] = []

    for exp_id, attrs in gs.g.nodes(data=True):
        if attrs.get("type") != EntityType.EXPERIMENT.value:
            continue

        materials = _neighbors_by_rel(gs, exp_id, RelationType.USES_MATERIAL.value)
        processes = _neighbors_by_rel(gs, exp_id, RelationType.USES_PROCESS.value)
        equipment = _neighbors_by_rel(gs, exp_id, RelationType.ON_EQUIPMENT.value)
        properties = _neighbors_by_rel(gs, exp_id, RelationType.MEASURES_PROPERTY.value)
        conclusions = _neighbors_by_rel(gs, exp_id, RelationType.PRODUCES_CONCLUSION.value)
        results = [
            {**p, "kind": "property"} for p in properties
        ] + [
            {**c, "kind": "conclusion"} for c in conclusions
        ]

        step_items = {
            "material": materials,
            "process": processes,
            "equipment": equipment,
            "result": results,
        }
        if not any(step_items.values()):
            continue

        pub = _publication_for_experiment(gs, exp_id)
        steps = [
            {"key": key, "label": _STEP_LABELS[key], "items": step_items[key]}
            for key in _STEP_KEYS
        ]

        node_ids = [exp_id]
        if pub:
            node_ids.append(pub["id"])
        for step in steps:
            node_ids.extend(item["id"] for item in step["items"])
        node_ids = list(dict.fromkeys(node_ids))

        path_ids = [item["id"] for step in steps for item in step["items"][:1]]

        chains.append({
            "experiment_id": exp_id,
            "experiment_name": attrs.get("name", ""),
            "publication": pub,
            "steps": steps,
            "node_ids": node_ids,
            "path_ids": path_ids,
        })

    chains.sort(key=lambda c: ((c.get("publication") or {}).get("name", ""), c["experiment_name"]))
    return chains


def append_chain_step_links(subgraph: dict[str, Any], chains: list[dict[str, Any]]) -> dict[str, Any]:
    """Добавляет пунктирные CHAIN_STEP между первыми узлами каждого шага цепи."""
    if not chains:
        return subgraph

    links = list(subgraph.get("links") or [])
    existing = {(l["source"], l["target"], l.get("type")) for l in links}

    for chain in chains:
        path = chain.get("path_ids") or []
        for src, tgt in zip(path, path[1:]):
            key = (src, tgt, "CHAIN_STEP")
            if key in existing:
                continue
            links.append({"source": src, "target": tgt, "type": "CHAIN_STEP", "attrs": {}})
            existing.add(key)

    return {**subgraph, "links": links}
