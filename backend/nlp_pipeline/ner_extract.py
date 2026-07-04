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

from backend.ner_llm import complete_ner, is_ner_configured
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
        f"мониторинг, полевое обследование, разбор случая на производстве. Название experiment — "
        f"суть работы (что изучали и чем), а НЕ отдельный параметр вроде «увеличение pH» или "
        f"«температура 60 °C». Если в чанке описывается такая работа — заведи один experiment "
        f"и подвесь material/process/equipment/condition/facility/property/conclusion на него, "
        f"а не оставляй их несвязанными сущностями.\n"
        f"material — вещество/сорбент/руда/реагент И объект изучения (например, ион металла в "
        f"растворе). property — только ИЗМЕРЯЕМЫЙ или РАССЧИТАННЫЙ показатель (степень извлечения, "
        f"коэффициент распределения, ёмкость); химический элемент в растворе — material, не property.\n"
        f"conclusion — вывод или рекомендация («целесообразно», «рекомендуется», «лучшие результаты "
        f"при», «не выше X»); свяжи с experiment через PRODUCES_CONCLUSION.\n"
        f"MEMBER_OF — только expert → team. НЕ связывай material с material через MEMBER_OF; "
        f"каждый конкретный материал/сорбент — отдельный material с USES_MATERIAL от experiment.\n"
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

Числовые параметры (концентрации, температуры, проценты извлечения, pH, CAPEX/OPEX и т.п.) клади
в attrs сущности experiment/property/conclusion в виде "ключ_единица": число, например
"extraction_rate_pct": 95, "pH_max": 3.5.

ОБЯЗАТЕЛЬНЫЙ КАРКАС, если в чанке есть предметные факты:
1) один experiment (центр звезды);
2) связь pub → experiment (DESCRIBES_EXPERIMENT) — всегда, если experiment не пустой;
3) USES_PROCESS на названный процесс (сорбция, выщелачивание, …), если процесс упомянут;
4) USES_MATERIAL на каждый явный материал/сорбент (не группируй в «аниониты» — заводи отдельные
   material на каждое название, если в тексте перечислены конкретные марки);
5) MEASURES_PROPERTY только на property (показатель), не на material;
6) PRODUCES_CONCLUSION на рекомендацию/вывод, если она есть в тексте.

ЗАПРЕЩЕНО: material → material; experiment → material через MEASURES_PROPERTY; MEMBER_OF между
material; называть experiment одним параметром (pH, температура) без описания самой работы.

Направление связи всегда source -> target по сигнатуре типа связи, например DESCRIBES_EXPERIMENT
идёт от publication к experiment, USES_MATERIAL — от experiment к material, AUTHORED_BY — от
publication к expert (а не наоборот).

ПРИМЕР (образец формата; в ответе извлекай ТОЛЬКО из переданного чанка, не копируй этот пример):

Текст: «При выщелачивании окисленной медной руды раствором серной кислоты при 60 °C
степень извлечения меди составила 87 %.»

Ответ:
{{"entities": [
  {{"tmp_id": "e1", "type": "experiment", "name": "выщелачивание окисленной медной руды раствором серной кислоты", "attrs": {{"temperature_deg_c": 60}}}},
  {{"tmp_id": "e2", "type": "material", "name": "окисленная медная руда", "attrs": {{}}}},
  {{"tmp_id": "e3", "type": "material", "name": "серная кислота", "attrs": {{}}}},
  {{"tmp_id": "e4", "type": "process", "name": "выщелачивание", "attrs": {{}}}},
  {{"tmp_id": "e5", "type": "property", "name": "степень извлечения меди", "attrs": {{"extraction_rate_pct": 87}}}}
],
"relations": [
  {{"source": "pub", "target": "e1", "type": "DESCRIBES_EXPERIMENT", "attrs": {{}}}},
  {{"source": "e1", "target": "e2", "type": "USES_MATERIAL", "attrs": {{}}}},
  {{"source": "e1", "target": "e3", "type": "USES_MATERIAL", "attrs": {{}}}},
  {{"source": "e1", "target": "e4", "type": "USES_PROCESS", "attrs": {{}}}},
  {{"source": "e1", "target": "e5", "type": "MEASURES_PROPERTY", "attrs": {{}}}}
]}}

Обрати внимание на примере: один experiment — центр звезды; material/process/property связаны
С НИМ, а не друг с другом; pub → experiment через DESCRIBES_EXPERIMENT обязателен, если experiment есть;
MEASURES_PROPERTY только experiment → property; конкретные материалы — отдельные USES_MATERIAL от experiment.

Верни СТРОГО JSON без пояснений и без markdown-обрамления, в том же формате, что в примере:
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
    if not is_ner_configured():
        return ExtractionResult()

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema_fragment=_schema_prompt_fragment())
    raw = complete_ner(chunk_text, system=system_prompt)
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
