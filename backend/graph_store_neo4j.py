"""Neo4j-бэкенд графа знаний: тот же читающий интерфейс, что и GraphStore
(backend/graph_store.py, NetworkX), но обход связей — настоящий Cypher, а не
самописный Python поверх in-memory структуры. Переключается через
GRAPH_BACKEND=neo4j в backend/main.py (см. README про docker-compose и
backend/neo4j_sync.py).

Почему не переписан весь NLP-пайплайн на Neo4j: построение графа
(nlp_pipeline/graph_writer.py) — это тысячи мелких мутаций с фаззи-резолвом
сущностей по имени, где каждая операция обращается к in-memory графу
целиком (resolve.py итерирует все узлы типа). Гонять это по сети в Neo4j на
каждый чанк было бы на порядки медленнее. Поэтому построение графа остаётся
на NetworkX, а Neo4j — это serving-слой: результат одной пакетной
синхронизацией (`sync_from_graph_store`) заливается в Neo4j, дальше все
поисковые/навигационные запросы (main.py, hybrid_retriever.py) идут туда.

Единственная сущность имеет единственную метку :Entity (без метки на тип),
а тип хранится как свойство `type` — это осознанное упрощение: динамические
метки в Cypher без APOC не параметризуются, а без APOC поднимать Neo4j в
docker-compose проще и быстрее. Типы связей (RelationType) по той же причине
нельзя параметризовать — их имена подставляются в текст запроса напрямую,
но это безопасно: они всегда берутся из фиксированного enum backend/schema.py,
а не из пользовательского ввода.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, Optional

from neo4j import GraphDatabase

from backend.schema import EntityType, RelationType

_VALID_RELATION_TYPES = {t.value for t in RelationType}

# Свойства узла, которые могут содержать вложенные структуры (список словарей) —
# Neo4j допускает только примитивы и массивы примитивов в свойствах узла/ребра,
# поэтому такие поля сериализуются в JSON-строку при записи и парсятся обратно при чтении.
_JSON_ENCODED_ATTRS = ("_history",)

# rag_chunks — JSON-блоб с текстом чанков И их эмбеддингами (backend/rag/store.py,
# Neo4jDocumentStore) на узлах Publication, загруженных через RAG-чат. Может быть
# десятками КБ на документ (384 float на чанк) — незачем гонять это в каждом
# ответе /api/graph и /api/graph/{id}, где нужны только name/type/обычные атрибуты.
# Сам RAG-стор читает/пишет это поле напрямую через свои Cypher-запросы, минуя
# _node_dict.
_HIDDEN_FROM_VIS = {"rag_chunks"}

ENTITY_RELATION: dict[EntityType, str] = {
    EntityType.MATERIAL: "USES_MATERIAL",
    EntityType.PROCESS: "USES_PROCESS",
    EntityType.CONDITION: "AT_CONDITION",
    EntityType.EQUIPMENT: "ON_EQUIPMENT",
    EntityType.FACILITY: "AT_FACILITY",
    EntityType.PROPERTY: "MEASURES_PROPERTY",
}


def _encode_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    out = dict(attrs)
    for k in _JSON_ENCODED_ATTRS:
        if k in out and not isinstance(out[k], str):
            out[k] = json.dumps(out[k], ensure_ascii=False)
    return out


def _decode_attrs(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    for k in _JSON_ENCODED_ATTRS:
        if k in out and isinstance(out[k], str):
            try:
                out[k] = json.loads(out[k])
            except (json.JSONDecodeError, TypeError):
                pass
    return out


class Neo4jGraphStore:
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "changeme12345")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self) -> None:
        self.driver.close()

    def ensure_constraints(self) -> None:
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")
            s.run("CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.type)")

    @staticmethod
    def _node_dict(n) -> dict[str, Any]:
        d = _decode_attrs(dict(n))
        node_id = d.pop("id")
        for k in _HIDDEN_FROM_VIS:
            d.pop(k, None)
        return {"id": node_id, **d}

    # ---------- загрузка из NetworkX-графа, построенного пайплайном ----------
    def sync_from_graph_store(self, gs) -> dict[str, int]:
        """Полная пересинхронизация: чистит граф в Neo4j и заливает заново из
        gs.g (NetworkX). MERGE по id делает узлы идемпотентными; для рёбер тоже
        MERGE, но заходу предшествует DETACH DELETE всего графа, так что по
        факту это не инкрементальный апдейт, а замена снимком — соответствует
        тому, как сейчас работает pipeline.py (весь граф пересобирается и
        сохраняется одним файлом на прогон)."""
        self.ensure_constraints()
        nodes = [
            {"id": n, "type": d.get("type"), "name": d.get("name"),
             "attrs": _encode_attrs({k: v for k, v in d.items() if k not in ("type", "name")})}
            for n, d in gs.g.nodes(data=True)
        ]
        edges_by_type: dict[str, list[dict[str, Any]]] = {}
        for u, v, d in gs.g.edges(data=True):
            rel_type = d.get("type")
            if rel_type not in _VALID_RELATION_TYPES:
                continue
            edges_by_type.setdefault(rel_type, []).append({
                "source": u, "target": v,
                "attrs": _encode_attrs({k: val for k, val in d.items() if k != "type"}),
            })

        with self.driver.session() as s:
            # rag_chunks IS NULL — не трогаем узлы документов, загруженных через
            # RAG-чат (backend/rag/store.py): это отдельная, управляемая
            # пользователем коллекция, а не часть NLP-пайплайна, и пересборка
            # демо/боевого графа не должна её стирать.
            s.run("MATCH (n:Entity) WHERE n.rag_chunks IS NULL DETACH DELETE n")
            s.run(
                """
                UNWIND $nodes AS row
                MERGE (n:Entity {id: row.id})
                SET n.type = row.type, n.name = row.name
                SET n += row.attrs
                """,
                nodes=nodes,
            )
            for rel_type, rows in edges_by_type.items():
                s.run(
                    f"""
                    UNWIND $rows AS row
                    MATCH (a:Entity {{id: row.source}}), (b:Entity {{id: row.target}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET r += row.attrs
                    """,
                    rows=rows,
                )
        return {"nodes": len(nodes), "edges": sum(len(v) for v in edges_by_type.values())}

    # ---------- базовые выборки ----------
    def entities_by_type(self, etype: EntityType) -> list[dict[str, Any]]:
        with self.driver.session() as s:
            return [self._node_dict(r["n"]) for r in s.run("MATCH (n:Entity {type: $t}) RETURN n", t=etype.value)]

    def node(self, node_id: str) -> Optional[dict[str, Any]]:
        with self.driver.session() as s:
            rec = s.run("MATCH (n:Entity {id: $id}) RETURN n", id=node_id).single()
            return self._node_dict(rec["n"]) if rec else None

    # ---------- предметные запросы (Cypher) ----------
    def query_experiments(self, **filters: Any) -> list[dict[str, Any]]:
        numeric_filters = filters.pop("numeric_filters", None) or []
        country = filters.pop("country", None)

        rel_by_key = {
            "material": "USES_MATERIAL", "process": "USES_PROCESS", "condition": "AT_CONDITION",
            "equipment": "ON_EQUIPMENT", "facility": "AT_FACILITY", "prop": "MEASURES_PROPERTY",
        }

        where_clauses: list[str] = []
        params: dict[str, Any] = {}
        for key, rel in rel_by_key.items():
            val = filters.get(key)
            if not val:
                continue
            queries = [val] if isinstance(val, str) else list(val)
            pname = f"q_{key}"
            params[pname] = [q.lower() for q in queries]
            where_clauses.append(
                f"EXISTS {{ MATCH (e)-[:{rel}]->(x_{key}:Entity) "
                f"WHERE ANY(q IN ${pname} WHERE toLower(x_{key}.name) CONTAINS q OR q CONTAINS toLower(x_{key}.name)) }}"
            )

        if country:
            where_clauses.append("toUpper(coalesce(e.country, '')) = toUpper($country)")
            params["country"] = country

        allowed_ops = {"<=", "<", ">=", ">", "="}
        for i, (key, op, value) in enumerate(numeric_filters):
            if op not in allowed_ops:
                continue
            pname = f"num_{i}"
            where_clauses.append(f"e.`{key}` IS NOT NULL AND toFloat(e.`{key}`) {op} ${pname}")
            params[pname] = value

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        cypher = f"MATCH (e:Entity {{type: 'experiment'}}){where_sql} RETURN e"
        with self.driver.session() as s:
            return [self._node_dict(r["e"]) for r in s.run(cypher, **params)]

    def experiment_detail(self, exp_id: str) -> dict[str, Any]:
        with self.driver.session() as s:
            rec = s.run("MATCH (e:Entity {id: $id}) RETURN e", id=exp_id).single()
            if rec is None:
                return {"id": exp_id}
            detail = self._node_dict(rec["e"])
            for row in s.run("MATCH (e:Entity {id: $id})-[r]->(t:Entity) RETURN type(r) AS rel, t", id=exp_id):
                detail.setdefault(row["rel"], []).append(self._node_dict(row["t"]))
            for row in s.run("MATCH (src:Entity)-[r]->(e:Entity {id: $id}) RETURN type(r) AS rel, src", id=exp_id):
                detail.setdefault(f"incoming::{row['rel']}", []).append(self._node_dict(row["src"]))
        return detail

    # ---------- анализ пробелов ----------
    def gap_matrix(
        self,
        x_type: EntityType = EntityType.MATERIAL,
        y_type: EntityType = EntityType.CONDITION,
    ) -> dict[str, Any]:
        rel_x = ENTITY_RELATION[x_type]
        rel_y = ENTITY_RELATION[y_type]
        with self.driver.session() as s:
            xs = [self._node_dict(r["x"]) for r in s.run("MATCH (x:Entity {type: $t}) RETURN x", t=x_type.value)]
            ys = [self._node_dict(r["y"]) for r in s.run("MATCH (y:Entity {type: $t}) RETURN y", t=y_type.value)]
            pair_rows = s.run(
                f"""
                MATCH (e:Entity {{type: 'experiment'}})-[:{rel_x}]->(x:Entity {{type: $xt}})
                MATCH (e)-[:{rel_y}]->(y:Entity {{type: $yt}})
                RETURN x.id AS x_id, y.id AS y_id, count(DISTINCT e) AS c
                """,
                xt=x_type.value, yt=y_type.value,
            )
            counts = {(row["x_id"], row["y_id"]): row["c"] for row in pair_rows}

        cells, gaps = [], []
        for x in xs:
            for y in ys:
                c = counts.get((x["id"], y["id"]), 0)
                cell = {"x_id": x["id"], "x_name": x["name"], "y_id": y["id"], "y_name": y["name"], "count": c}
                cells.append(cell)
                if c == 0:
                    gaps.append(cell)
        return {
            "x_type": x_type.value, "y_type": y_type.value,
            "x_axis": [{"id": x["id"], "name": x["name"]} for x in xs],
            "y_axis": [{"id": y["id"], "name": y["name"]} for y in ys],
            "cells": cells, "gaps": gaps,
        }

    def contradictions_for(self, conclusion_ids: list[str]) -> list[dict[str, Any]]:
        if not conclusion_ids:
            return []
        with self.driver.session() as s:
            rows = s.run(
                """
                MATCH (a:Entity)-[r:CONTRADICTS]->(b:Entity)
                WHERE a.id IN $ids OR b.id IN $ids
                RETURN a, b, properties(r) AS attrs
                """,
                ids=list(conclusion_ids),
            )
            return [
                {"a": self._node_dict(row["a"]), "b": self._node_dict(row["b"]), "note": dict(row["attrs"]).get("note", "")}
                for row in rows
            ]

    # ---------- визуализация ----------
    def vis_subgraph(self, node_ids: Iterable[str]) -> dict[str, Any]:
        ids = list(node_ids)
        if not ids:
            return {"nodes": [], "links": []}
        with self.driver.session() as s:
            node_rows = s.run(
                """
                MATCH (n:Entity) WHERE n.id IN $ids
                OPTIONAL MATCH (n)-[r]-()
                RETURN n, count(r) AS degree
                """,
                ids=ids,
            )
            nodes = []
            for row in node_rows:
                d = self._node_dict(row["n"])
                attrs = {k: v for k, v in d.items() if k not in ("id", "type", "name")}
                nodes.append({"id": d["id"], "type": d.get("type"), "name": d.get("name"),
                               "degree": row["degree"], "attrs": attrs})

            link_rows = s.run(
                """
                MATCH (a:Entity)-[r]->(b:Entity)
                WHERE a.id IN $ids AND b.id IN $ids
                RETURN a.id AS source, b.id AS target, type(r) AS type, properties(r) AS attrs
                """,
                ids=ids,
            )
            links = [
                {"source": row["source"], "target": row["target"], "type": row["type"], "attrs": dict(row["attrs"])}
                for row in link_rows
            ]
        return {"nodes": nodes, "links": links}

    def to_vis_json(self) -> dict[str, Any]:
        with self.driver.session() as s:
            ids = [r["id"] for r in s.run("MATCH (n:Entity) RETURN n.id AS id")]
        return self.vis_subgraph(ids)

    def neighbors_vis_json(self, node_id: str, depth: int = 1) -> dict[str, Any]:
        depth = max(1, min(int(depth), 3))  # ge/le уже проверены на уровне FastAPI Query, здесь — вторая линия защиты
        with self.driver.session() as s:
            if s.run("MATCH (n:Entity {id: $id}) RETURN n LIMIT 1", id=node_id).single() is None:
                return {"nodes": [], "links": []}
            rows = s.run(
                f"MATCH (start:Entity {{id: $id}})-[*0..{depth}]-(other:Entity) RETURN DISTINCT other.id AS id",
                id=node_id,
            )
            ids = [r["id"] for r in rows]
        return self.vis_subgraph(ids)

    def dated_nodes(self) -> list[dict[str, Any]]:
        with self.driver.session() as s:
            rows = s.run(
                "MATCH (n:Entity) WHERE n.date IS NOT NULL AND n.date <> '' "
                "RETURN n.id AS id, n.type AS type, n.name AS name, n.date AS date"
            )
            result = [dict(r) for r in rows]
        result.sort(key=lambda x: x["date"])
        return result

    def counts(self) -> dict[str, int]:
        with self.driver.session() as s:
            n = s.run("MATCH (n:Entity) RETURN count(n) AS c").single()["c"]
            e = s.run("MATCH (:Entity)-[r]->(:Entity) RETURN count(r) AS c").single()["c"]
        return {"nodes": n, "edges": e}
