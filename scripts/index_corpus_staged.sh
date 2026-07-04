#!/usr/bin/env bash
# Двухэтапная индексация RAG-корпуса:
#   1) приоритетные файлы из README (тестовый набор + 4 вопроса ТЗ)
#   2) весь data/raw/** (уже проиндексированные пропускаются по манифесту)
#
# Использование:
#   ./scripts/index_corpus_staged.sh           # оба этапа
#   ./scripts/index_corpus_staged.sh --priority-only
#   ./scripts/index_corpus_staged.sh --full-only
#   ./scripts/index_corpus_staged.sh --force   # переиндексировать даже без изменений
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
  PYTHON="$ROOT/venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

PRIORITY_ONLY=0
FULL_ONLY=0
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --priority-only) PRIORITY_ONLY=1 ;;
    --full-only) FULL_ONLY=1 ;;
    --force) FORCE=1 ;;
    -h|--help)
      sed -n '2,12p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $arg (см. --help)" >&2
      exit 1
      ;;
  esac
done

if (( PRIORITY_ONLY && FULL_ONLY )); then
  echo "Нельзя одновременно --priority-only и --full-only" >&2
  exit 1
fi

run_index() {
  local -a extra=()
  if (( FORCE )); then
    extra+=(--force)
  fi
  "$PYTHON" -m backend.scripts.index_corpus "${extra[@]}" "$@"
}

PRIORITY_FILES=(
  "data/raw/Статьи/55 Приложение. Текст статьи.docx"
  "data/raw/Статьи/9 статья (2).docx"
  "data/raw/Статьи/32 Статья - Салтыков П.М. (ЛГМ).docx"
  "data/raw/Статьи/13 Приложение. Статья.pdf"
  "data/raw/Статьи/52 Solid household and industrial waste paper 28-09-2021-rus.docx"
  "data/raw/Журналы/Обогащение руд/2022/ОР № 02_22.pdf"
  "data/raw/Обзоры/Наилучшие доступные технологии последний вариант 20.08.docx"
  "data/raw/Обзоры/Обзор технических решений в области электролитического производства никеля и меди.docx"
  "data/raw/Обзоры/Электроэкстракция никеля. Влияние состава электролита.docx"
  "data/raw/Обзоры/Распределение Au, Ag и МПГ между меднымникелевым штейном и шлаком.docx"
  "data/raw/Обзоры/Переработка Cu-Ni шлаков (2024).docx"
  "data/raw/Обзоры/Методы очистки шахтных вод.docx"
  "data/raw/Журналы/Горный журнал/2024/№ 01_24.pdf"
)

if (( ! FULL_ONLY )); then
  echo "=== Этап 1/2: приоритетные файлы (${#PRIORITY_FILES[@]}) ==="
  run_index "${PRIORITY_FILES[@]}"
fi

if (( ! PRIORITY_ONLY )); then
  echo ""
  echo "=== Этап 2/2: весь корпус data/raw/** ==="
  run_index
fi

echo ""
echo "Индексация завершена."
