#!/usr/bin/env python3
"""Авто-оценка RAG eval: эвристики по retrieval + разметка из auto_eval.json.

Запуск:
    python -m backend.scripts.rag_eval_score
    python -m backend.scripts.rag_eval_score data/rag_eval/annotations.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_AUTO = Path(__file__).resolve().parent.parent.parent / "data" / "rag_eval" / "auto_eval.json"
DEFAULT_ANNOTATED = Path(__file__).resolve().parent.parent.parent / "data" / "rag_eval" / "annotations.json"


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.0f}%" if total else "—"


def summarize(data: dict) -> None:
    items = data.get("items", [])
    if not items:
        print("Нет items", file=sys.stderr)
        return

    rated = [i for i in items if i.get("rating") is not None]
    avg_rating = sum(i["rating"] for i in rated) / len(rated) if rated else 0

    def bool_field(name: str) -> tuple[int, int]:
        vals = [i.get(name) for i in items if i.get(name) is not None]
        if not vals:
            return 0, 0
        return sum(1 for v in vals if v is True), len(vals)

    ret_tp, ret_n = bool_field("retrieval_ok")
    fact_tp, fact_n = bool_field("factual_ok")
    cit_tp, cit_n = bool_field("citation_ok")

    print("=== RAG Eval — сводка ===")
    print(f"Вопросов: {len(items)}, с rating: {len(rated)}")
    print(f"Средний rating: {avg_rating:.2f} / 5")
    print(f"Retrieval OK:  {ret_tp}/{ret_n} ({_pct(ret_tp, ret_n)})")
    print(f"Factual OK:    {fact_tp}/{fact_n} ({_pct(fact_tp, fact_n)})")
    print(f"Citation OK:   {cit_tp}/{cit_n} ({_pct(cit_tp, cit_n)})")
    print()
    print(f"{'ID':<5} {'R':>2}  {'ret':>3} {'fac':>3} {'cit':>3}  expected_source")
    for i in items:
        r = i.get("rating")
        print(
            f"{i.get('id','?'):<5} {r if r is not None else '-':>2}  "
            f"{_tri(i.get('retrieval_ok')):>3} {_tri(i.get('factual_ok')):>3} {_tri(i.get('citation_ok')):>3}  "
            f"{i.get('expected_source', '')[:45]}"
        )


def _tri(v) -> str:
    if v is True:
        return "✓"
    if v is False:
        return "✗"
    return "·"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сводка метрик RAG eval")
    parser.add_argument("file", nargs="?", type=Path, default=None)
    args = parser.parse_args(argv)

    path = args.file
    if path is None:
        path = DEFAULT_ANNOTATED if DEFAULT_ANNOTATED.is_file() else DEFAULT_AUTO
    if not path.is_file():
        print(f"Файл не найден: {path}", file=sys.stderr)
        return 1

    summarize(json.loads(path.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
