"""Этап 4а: entity resolution — персистентная таблица канонических имён -> node_id.

Без этого модуля повторный запуск экстрактора на новых документах плодит дубликаты:
«Электроэкстракция никеля» из одного отчёта и «электроэкстракции никеля» из другого
стали бы двумя разными узлами графа. Таблица алиасов хранится в JSON и пополняется
по мере обработки новых документов, так что со временем сопоставление становится
только точнее (а не пересчитывается каждый раз с нуля).

Использует ту же морфологическую эвристику (backend/lexicon.word_match), что и
поиск по графу в hybrid_retriever.py — согласованность в обе стороны, как и
просили: новый узел из документа должен находиться теми же вопросами, что уже
работают в поиске.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend.graph_store import GraphStore
from backend.lexicon import name_similarity


class AliasTable:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        # {"material": {"медь": "material_ab12", ...}, ...}
        self.data: dict[str, dict[str, str]] = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def lookup_exact(self, etype: str, name: str) -> Optional[str]:
        return self.data.get(etype, {}).get(name.strip().lower())

    def register(self, etype: str, name: str, node_id: str) -> None:
        self.data.setdefault(etype, {})[name.strip().lower()] = node_id


def resolve_entity(
    gs: GraphStore,
    alias_table: AliasTable,
    etype: str,
    name: str,
    similarity_threshold: float = 0.75,
) -> Optional[str]:
    """Возвращает node_id существующей сущности того же типа, если она уже есть в
    графе или в таблице алиасов (по точному имени или по морфологическому сходству),
    иначе None (значит нужно создавать новый узел)."""
    exact = alias_table.lookup_exact(etype, name)
    if exact and exact in gs.g:
        return exact

    name_low = name.strip().lower()
    best_id, best_score = None, 0.0
    for n, d in gs.g.nodes(data=True):
        if d.get("type") != etype:
            continue
        existing_name = str(d.get("name", ""))
        if existing_name.strip().lower() == name_low:
            return n
        score = name_similarity(name, existing_name)
        if score > best_score:
            best_score, best_id = score, n

    if best_id and best_score >= similarity_threshold:
        return best_id
    return None
