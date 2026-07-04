#!/usr/bin/env bash
# Удалить из RAG (Neo4j) все корпусные документы, кроме 13 приоритетных.
# Файлы на диске не удаляются.
#
#   ./scripts/prune_corpus_keep_priority.sh           # dry-run
#   ./scripts/prune_corpus_keep_priority.sh --apply   # удалить
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

exec "$PYTHON" -m backend.scripts.prune_corpus "$@"
