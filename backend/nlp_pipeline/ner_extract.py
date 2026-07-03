"""Этап 3: LLM-экстракция сущностей/связей против backend/schema.py.

Промпт не дублирует описание онтологии вручную — типы сущностей/связей
сериализуются прямо из EntityType/RelationType (schema.py остаётся единственным
источником истины). Ответ LLM парсится в pydantic-модели RawEntity/RawRelation,
поле `type` типизировано как EntityType/RelationType — pydantic физически не даст
экстрактору вернуть несуществующий тип, невалидные записи просто не пройдут парсинг.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from backend.llm_client import complete, is_configured
from backend.schema import EntityType, RelationType


class RawEntity(BaseModel):
    tmp_id: str
    type: EntityType
    name: str
    attrs: dict[str, Any] = Field(default_factory=dict)


class RawRelation(BaseModel):
    source: str
    target: str
    type: RelationType
    attrs: dict[str, Any] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    entities: list[RawEntity] = Field(default_factory=list)
    relations: list[RawRelation] = Field(default_factory=list)


def _schema_prompt_fragment() -> str:
    entity_types = ", ".join(t.value for t in EntityType if t != EntityType.PUBLICATION)
    relation_types = ", ".join(t.value for t in RelationType)
    return (
        f"Допустимые типы сущностей (поле \"type\"): {entity_types}. "
        f"(publication уже создана заранее для этого документа под id \"pub\" — используй его "
        f"как source/target в связях, не создавай сущность с type=publication сам).\n"
        f"experiment — это не только классический лабораторный опыт, а ЛЮБОЕ описанное в тексте "
        f"исследование/анализ/кейс: расчёт, моделирование (в т.ч. CFD), промышленное испытание, "
        f"мониторинг, полевое обследование, разбор случая на производстве. Если в чанке описывается "
        f"такая работа с использованием материалов/процессов/оборудования — заведи под неё один "
        f"experiment и подвесь material/process/equipment/condition/facility на него через "
        f"USES_MATERIAL/USES_PROCESS/ON_EQUIPMENT/AT_CONDITION/AT_FACILITY, а не оставляй их "
        f"несвязанными сущностями.\n"
        f"Допустимые типы связей (поле \"type\"): {relation_types}."
    )


SYSTEM_PROMPT_TEMPLATE = """Ты — экстрактор сущностей и связей для графа знаний R&D в горно-металлургической отрасли.
Тебе даётся фрагмент текста реального документа (статья/отчёт/презентация, RU или EN). Извлеки из него
ТОЛЬКО то, что явно написано в тексте — не придумывай факты, числа и названия. Если в чанке нет предметных
фактов (титульный лист, оглавление, реклама) — верни пустые списки.

Поле "name" у сущности — дословная цитата или устойчивое обозначение из текста чанка, НА ТОМ ЖЕ ЯЗЫКЕ,
что и сам чанк. Не переводи и не перефразируй название на другой язык (английский чанк -> английские
names, русский чанк -> русские names), даже если остальной промпт на русском.

{schema_fragment}

Числовые параметры (концентрации, температуры, проценты извлечения, CAPEX/OPEX и т.п.) клади прямо в attrs
сущности experiment/material в виде "ключ_единица": число, например "extraction_rate_pct": 95.

Направление связи всегда source -> target по сигнатуре типа связи, например DESCRIBES_EXPERIMENT
идёт от publication к experiment, USES_MATERIAL — от experiment к material, AUTHORED_BY — от
publication к expert (а не наоборот).

Верни СТРОГО JSON без пояснений и без markdown-обрамления, в формате:
{{"entities": [{{"tmp_id": "e1", "type": "experiment", "name": "...", "attrs": {{}}}},
              {{"tmp_id": "e2", "type": "material", "name": "...", "attrs": {{}}}}],
 "relations": [{{"source": "pub", "target": "e1", "type": "DESCRIBES_EXPERIMENT", "attrs": {{}}}},
               {{"source": "e1", "target": "e2", "type": "USES_MATERIAL", "attrs": {{}}}}]}}
"""


def _extract_json(raw: str) -> Optional[dict[str, Any]]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def extract_chunk_entities(chunk_text: str) -> ExtractionResult:
    if not is_configured():
        return ExtractionResult()

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema_fragment=_schema_prompt_fragment())
    raw = complete(chunk_text, system=system_prompt)
    if not raw:
        return ExtractionResult()

    parsed = _extract_json(raw)
    if parsed is None:
        print(f"[ner_extract] Не удалось распарсить JSON от LLM: {raw[:200]!r}")
        return ExtractionResult()

    entities: list[RawEntity] = []
    for e in parsed.get("entities", []):
        try:
            entities.append(RawEntity(**e))
        except ValidationError as err:
            print(f"[ner_extract] Пропущена невалидная сущность {e!r}: {err.errors()[0]['msg']}")

    relations: list[RawRelation] = []
    for r in parsed.get("relations", []):
        try:
            relations.append(RawRelation(**r))
        except ValidationError as err:
            print(f"[ner_extract] Пропущена невалидная связь {r!r}: {err.errors()[0]['msg']}")

    return ExtractionResult(entities=entities, relations=relations)
