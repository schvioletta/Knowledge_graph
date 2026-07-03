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
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from backend.llm_client import complete, is_configured
from backend.nlp_pipeline.llm_log import LlmLogContext, log_llm_exchange
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


@dataclass
class ExtractLogContext:
    llm: Optional[LlmLogContext] = None


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

ЧТО ОБЯЗАТЕЛЬНО ИЗВЛЕКАТЬ, ДАЖЕ ЕСЛИ ЭТО НЕ САМООЧЕВИДНО:
- Material — это не только вносимое вещество (сорбент, реагент, добавка), но и объект изучения/анализируемое
  вещество. Если исследуется сорбция свинца анионитами — свинец тоже material, а не только аниониты.
  Извлекай все химические вещества, явно упомянутые как участвующие в процессе, независимо от их роли.
- Process — если в тексте назван процесс (сорбция, выщелачивание, электроэкстракция, очистка и т.п.),
  заведи под него material=process сущность и свяжи с experiment через USES_PROCESS, даже если процесс
  упомянут вскользь, а не вынесен в отдельный подзаголовок.
- Property — если текст описывает ИЗМЕРЕННЫЙ ИЛИ РАССЧИТАННЫЙ РЕЗУЛЬТАТ (коэффициент распределения,
  емкость, степень извлечения, разница "в N раз выше/ниже" и т.п.) — это отдельная property-сущность
  со значением в attrs, связанная с experiment через MEASURES_PROPERTY, а не просто число внутри attrs
  самого эксперимента.
- Conclusion — если в тексте есть вывод или рекомендация (маркеры: "целесообразно", "рекомендуется",
  "следует", "оптимальн-", "лучшие результаты достигаются при", "не более/не менее X"), ОБЯЗАТЕЛЬНО
  заведи под неё conclusion-сущность и свяжи с experiment через PRODUCES_CONCLUSION. Числовой порог из
  рекомендации помести в attrs conclusion, а не оставляй только в тексте name. Не пропускай вывод только
  потому, что он сформулирован как придаточное предложение в конце абзаца, а не как отдельный тезис.

ЧИСЛОВЫЕ ПАРАМЕТРЫ И ДИАПАЗОНЫ:
Числовые параметры (концентрации, температуры, проценты извлечения, CAPEX/OPEX и т.п.) клади прямо в attrs
сущности experiment/material/property/conclusion в виде "ключ_единица": число, например "extraction_rate_pct": 95.

Если в тексте сравниваются ДВА ИЛИ БОЛЕЕ значений одного параметра (эксперимент повторён при разных
условиях), используй ТОЛЬКО формат "<параметр>_min_<единица>" и "<параметр>_max_<единица>" — никогда
суффиксы "_1"/"_2", "_start"/"_end", "_before"/"_after" и никогда массив значений.
Пример: варьировалась концентрация никеля 50, 100, 150 и 200 г/л -> "nickel_concentration_min_g_per_l": 50,
"nickel_concentration_max_g_per_l": 200.
Диапазон — всегда два отдельных числовых поля min/max, никогда строка вида "3.0-3.6". Если значение
единственное (не диапазон) — один ключ без _min/_max, как в примере выше.

Направление связи всегда source -> target по сигнатуре типа связи, например DESCRIBES_EXPERIMENT
идёт от publication к experiment, USES_MATERIAL — от experiment к material, AUTHORED_BY — от
publication к expert (а не наоборот).

Верни СТРОГО JSON без пояснений и без markdown-обрамления — никаких тройных обратных кавычек и слова
"json" до или после объекта; ответ должен начинаться символом {{ и заканчиваться символом }}, в формате:
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


def _serialize_parsed(entities: list[RawEntity], relations: list[RawRelation]) -> dict[str, Any]:
    return {
        "entities": [e.model_dump(mode="json") for e in entities],
        "relations": [r.model_dump(mode="json") for r in relations],
    }


def extract_chunk_entities(
    chunk_text: str,
    *,
    log_ctx: Optional[ExtractLogContext] = None,
) -> ExtractionResult:
    if not is_configured():
        return ExtractionResult()

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema_fragment=_schema_prompt_fragment())
    raw = complete(chunk_text, system=system_prompt)
    if not raw:
        if log_ctx and log_ctx.llm:
            log_llm_exchange(
                log_ctx.llm,
                system_prompt=system_prompt,
                chunk_text=chunk_text,
                raw_response=None,
                parse_ok=False,
                parse_error="empty LLM response",
            )
        return ExtractionResult()

    parsed = _extract_json(raw)
    if parsed is None:
        print(f"[ner_extract] Не удалось распарсить JSON от LLM: {raw[:200]!r}")
        if log_ctx and log_ctx.llm:
            log_llm_exchange(
                log_ctx.llm,
                system_prompt=system_prompt,
                chunk_text=chunk_text,
                raw_response=raw,
                parse_ok=False,
                parse_error="json parse failed",
            )
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

    result = ExtractionResult(entities=entities, relations=relations)
    if log_ctx and log_ctx.llm:
        log_llm_exchange(
            log_ctx.llm,
            system_prompt=system_prompt,
            chunk_text=chunk_text,
            raw_response=raw,
            parse_ok=True,
            parsed=_serialize_parsed(entities, relations),
        )
    return result
