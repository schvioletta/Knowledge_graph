"""Приоритетный набор файлов корпуса (README + scripts/index_corpus_staged.sh)."""
from __future__ import annotations

from pathlib import Path

# Пути относительно корня репозитория.
PRIORITY_CORPUS_FILES: tuple[str, ...] = (
    "data/raw/Статьи/55 Приложение. Текст статьи.docx",
    "data/raw/Статьи/9 статья (2).docx",
    "data/raw/Статьи/32 Статья - Салтыков П.М. (ЛГМ).docx",
    "data/raw/Статьи/13 Приложение. Статья.pdf",
    "data/raw/Статьи/52 Solid household and industrial waste paper 28-09-2021-rus.docx",
    "data/raw/Журналы/Обогащение руд/2022/ОР № 02_22.pdf",
    "data/raw/Обзоры/Наилучшие доступные технологии последний вариант 20.08.docx",
    "data/raw/Обзоры/Обзор технических решений в области электролитического производства никеля и меди.docx",
    "data/raw/Обзоры/Электроэкстракция никеля. Влияние состава электролита.docx",
    "data/raw/Обзоры/Распределение Au, Ag и МПГ между меднымникелевым штейном и шлаком.docx",
    "data/raw/Обзоры/Переработка Cu-Ni шлаков (2024).docx",
    "data/raw/Обзоры/Методы очистки шахтных вод.docx",
    "data/raw/Журналы/Горный журнал/2024/№ 01_24.pdf",
)


def priority_corpus_paths(repo_root: str | Path) -> set[str]:
    root = Path(repo_root).resolve()
    return {str((root / rel).resolve()) for rel in PRIORITY_CORPUS_FILES}
