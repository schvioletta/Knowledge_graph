"""Этап 4б: валидация извлечённых фактов перед записью в граф — аналог SHACL-проверок
поверх schema.py (тип сущности/связи допустим, source/target связи согласованы по
типам, обязательные атрибуты модели верификации проставлены).

pydantic в ner_extract.py уже гарантирует, что type — один из EntityType/RelationType
(иначе запись не распарсится). Этот модуль добавляет вторую линию проверки:
СОГЛАСОВАННОСТЬ пары (source_type, target_type, relation_type) и наличие
обязательных полей верификации (source/confidence/date) на Experiment/
Publication/Conclusion — то, что pydantic-схема связи сама по себе не проверяет.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.schema import EntityType, RelationType

# (тип источника, допустимые типы цели) для каждого типа связи.
RELATION_SIGNATURE: dict[RelationType, tuple[EntityType, set[EntityType]]] = {
    RelationType.USES_MATERIAL: (EntityType.EXPERIMENT, {EntityType.MATERIAL}),
    RelationType.USES_PROCESS: (EntityType.EXPERIMENT, {EntityType.PROCESS}),
    RelationType.AT_CONDITION: (EntityType.EXPERIMENT, {EntityType.CONDITION}),
    RelationType.AT_FACILITY: (EntityType.EXPERIMENT, {EntityType.FACILITY}),
    RelationType.ON_EQUIPMENT: (EntityType.EXPERIMENT, {EntityType.EQUIPMENT}),
    RelationType.MEASURES_PROPERTY: (EntityType.EXPERIMENT, {EntityType.PROPERTY}),
    RelationType.PRODUCES_CONCLUSION: (EntityType.EXPERIMENT, {EntityType.CONCLUSION}),
    RelationType.DESCRIBES_EXPERIMENT: (EntityType.PUBLICATION, {EntityType.EXPERIMENT}),
    RelationType.CONDUCTED_BY: (EntityType.EXPERIMENT, {EntityType.TEAM, EntityType.EXPERT}),
    RelationType.AUTHORED_BY: (EntityType.PUBLICATION, {EntityType.EXPERT}),
    RelationType.TAGGED_AS: (EntityType.PUBLICATION, {EntityType.TOPIC}),
    RelationType.MEMBER_OF: (EntityType.EXPERT, {EntityType.TEAM}),
    RelationType.CONTRADICTS: (EntityType.CONCLUSION, {EntityType.CONCLUSION}),
    RelationType.VALIDATED_BY: (EntityType.CONCLUSION, {EntityType.PUBLICATION}),
    RelationType.NEEDS_REVIEW: (EntityType.CONCLUSION, {EntityType.CONCLUSION}),
}

REQUIRES_VERIFICATION_META = {EntityType.EXPERIMENT, EntityType.CONCLUSION, EntityType.PUBLICATION}
VERIFICATION_FIELDS = ("source_file", "confidence", "date")


@dataclass
class ValidationIssue:
    level: str  # "error" | "warning"
    message: str


def validate_relation(source_type: EntityType, target_type: EntityType, rel_type: RelationType) -> list[ValidationIssue]:
    signature = RELATION_SIGNATURE.get(rel_type)
    if not signature:
        return [ValidationIssue("error", f"Неизвестный тип связи {rel_type}")]
    expected_source, expected_targets = signature
    issues = []
    if source_type != expected_source:
        issues.append(ValidationIssue(
            "error",
            f"{rel_type.value}: источник должен быть {expected_source.value}, получено {source_type.value}",
        ))
    if target_type not in expected_targets:
        expected = "/".join(t.value for t in expected_targets)
        issues.append(ValidationIssue(
            "error",
            f"{rel_type.value}: цель должна быть {expected}, получено {target_type.value}",
        ))
    return issues


def validate_entity_attrs(etype: EntityType, attrs: dict) -> list[ValidationIssue]:
    if etype not in REQUIRES_VERIFICATION_META:
        return []
    issues = []
    for field in VERIFICATION_FIELDS:
        if not attrs.get(field):
            issues.append(ValidationIssue(
                "warning",
                f"{etype.value}: отсутствует поле верификации '{field}' — будет проставлено значение по умолчанию",
            ))
    return issues
