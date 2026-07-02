"""Онтология knowledge graph для R&D в горно-металлургической отрасли.

Сущности и связи спроектированы так, чтобы легко расширяться на новые домены
(гидрометаллургия, пирометаллургия, экология, переработка отходов) без
изменения схемы — новый домен добавляется как набор конкретных сущностей
и связей, использующих те же типы.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    PUBLICATION = "publication"      # статьи, отчёты, патенты, диссертации
    EXPERIMENT = "experiment"        # протокол опыта / серия испытаний
    MATERIAL = "material"            # вещества, руды, реагенты, продукты
    PROCESS = "process"              # технологический процесс/метод
    PROPERTY = "property"            # измеряемое свойство/показатель
    CONDITION = "condition"          # качественное условие (климат, тип воды и т.п.)
    EQUIPMENT = "equipment"          # установки, аппараты
    FACILITY = "facility"            # предприятие/фабрика/рудник
    TEAM = "team"                    # лаборатория/подразделение
    EXPERT = "expert"                # сотрудник-эксперт
    TOPIC = "topic"                  # тематический тег
    CONCLUSION = "conclusion"        # вывод/рекомендация


class RelationType(str, Enum):
    USES_MATERIAL = "USES_MATERIAL"
    USES_PROCESS = "USES_PROCESS"
    ON_EQUIPMENT = "ON_EQUIPMENT"
    AT_CONDITION = "AT_CONDITION"
    AT_FACILITY = "AT_FACILITY"
    MEASURES_PROPERTY = "MEASURES_PROPERTY"
    PRODUCES_CONCLUSION = "PRODUCES_CONCLUSION"
    DESCRIBES_EXPERIMENT = "DESCRIBES_EXPERIMENT"
    CONDUCTED_BY = "CONDUCTED_BY"
    AUTHORED_BY = "AUTHORED_BY"
    TAGGED_AS = "TAGGED_AS"
    MEMBER_OF = "MEMBER_OF"
    CONTRADICTS = "CONTRADICTS"
    VALIDATED_BY = "VALIDATED_BY"


class Entity(BaseModel):
    """attrs — свободный словарь; общеупотребимые ключи для верификации фактов:
    source (строка/название публикации), confidence ("высокая"/"средняя"/"низкая"),
    date (дата актуализации ISO), country ("RU"/"INTL"). Числовые параметры процесса
    хранятся напрямую в attrs (например sulfate_mg_l=250) для поддержки диапазонных
    фильтров без разрастания графа отдельными узлами на каждое число.
    """
    id: str
    type: EntityType
    name: str
    attrs: dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    source: str
    target: str
    type: RelationType
    attrs: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    answer: str
    matched_experiment_ids: list[str]
    path_node_ids: list[str]
    subgraph: dict[str, Any]
    gaps_mentioned: list[str] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
