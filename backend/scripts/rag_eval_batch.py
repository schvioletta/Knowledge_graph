"""Пакетный прогон RAG-вопросов для ручной разметки качества ответов.

Читает data/rag_eval/questions.json, для каждого вопроса вызывает
GET /api/rag/ask?auto_attach=true и сохраняет ответ системы вместе с
полями для gold-разметки.

Запуск (бэкенд и Neo4j должны быть доступны):
    python -m backend.scripts.rag_eval_batch
    python -m backend.scripts.rag_eval_batch --base-url http://localhost:8000
    python -m backend.scripts.rag_eval_batch --out data/rag_eval/run_2026-07-04.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_QUESTIONS = Path(__file__).resolve().parent.parent.parent / "data" / "rag_eval" / "questions.json"
DEFAULT_OUT = Path(__file__).resolve().parent.parent.parent / "data" / "rag_eval" / "annotation_template.json"


def _fetch_rag(base_url: str, question: str, timeout: float = 300.0) -> dict:
    url = (
        f"{base_url.rstrip('/')}/api/rag/ask?"
        + urllib.parse.urlencode({"q": question, "auto_attach": "true"})
    )
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _slim_citations(citations: list[dict]) -> list[dict]:
    return [
        {
            "index": c.get("index"),
            "doc_id": c.get("doc_id"),
            "title": c.get("title"),
            "source_name": c.get("source_name"),
            "location": c.get("location"),
            "score": c.get("score"),
            "snippet": c.get("snippet"),
        }
        for c in citations
    ]


def _slim_attached(attached: list[dict] | None) -> list[dict]:
    if not attached:
        return []
    return [
        {
            "id": d.get("id"),
            "title": d.get("title"),
            "source_name": d.get("source_name"),
            "year": d.get("year"),
            "domain": d.get("domain"),
            "auto_attached": d.get("auto_attached"),
        }
        for d in attached
    ]


def run_batch(base_url: str, questions_path: Path, out_path: Path) -> int:
    spec = json.loads(questions_path.read_text(encoding="utf-8"))
    items_in = spec.get("items", [])
    if not items_in:
        print("Нет вопросов в", questions_path, file=sys.stderr)
        return 1

    results: list[dict] = []
    errors = 0

    for i, item in enumerate(items_in, start=1):
        qid = item["id"]
        question = item["question"]
        print(f"[{i}/{len(items_in)}] {qid}: {question[:70]}...", flush=True)
        try:
            resp = _fetch_rag(base_url, question)
        except urllib.error.URLError as e:
            print(f"  ERR  {e}", file=sys.stderr)
            errors += 1
            results.append({
                **item,
                "error": str(e),
                "system_answer": "",
                "confidence": "нет данных",
                "grounded": False,
                "llm_used": False,
                "citations": [],
                "attached_docs": [],
                "query_expansions": [],
                "chunk_graph_stats": {},
                "gold_answer": "",
                "rating": None,
                "rating_scale": "1=неверно, 2=частично, 3=верно с пробелами, 4=верно, 5=эталон",
                "retrieval_ok": None,
                "factual_ok": None,
                "citation_ok": None,
                "notes": "",
            })
            continue

        results.append({
            **item,
            "system_answer": resp.get("answer", ""),
            "confidence": resp.get("confidence"),
            "grounded": resp.get("grounded"),
            "llm_used": resp.get("llm_used"),
            "query_original": resp.get("query_original"),
            "query_expansions": resp.get("query_expansions", []),
            "expand_llm": resp.get("expand_llm"),
            "citations": _slim_citations(resp.get("citations", [])),
            "attached_docs": _slim_attached(resp.get("attached")),
            "chunk_graph_stats": resp.get("chunk_graph_stats", {}),
            "gold_answer": "",
            "rating": None,
            "rating_scale": "1=неверно, 2=частично, 3=верно с пробелами, 4=верно, 5=эталон",
            "retrieval_ok": None,
            "factual_ok": None,
            "citation_ok": None,
            "notes": "",
        })
        print(
            f"  ok   grounded={resp.get('grounded')} confidence={resp.get('confidence')} "
            f"citations={len(resp.get('citations', []))} attached={len(resp.get('attached') or [])}",
            flush=True,
        )

    payload = {
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "base_url": base_url,
            "questions_file": str(questions_path),
            "corpus_files": spec.get("corpus_files", []),
            "total": len(items_in),
            "errors": errors,
            "instructions": (
                "Заполните gold_answer (эталонный ответ по документу), rating (1–5), "
                "retrieval_ok / factual_ok / citation_ok (true/false/null) и notes. "
                "expected_source — подсказка, из какого файла ожидается ответ."
            ),
        },
        "items": results,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nСохранено: {out_path} ({len(results)} вопросов, ошибок: {errors})")
    return 1 if errors == len(items_in) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Пакетный RAG-прогон для eval-разметки")
    parser.add_argument("--base-url", default="http://localhost:8000", help="URL бэкенда")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.questions.is_file():
        print(f"Файл вопросов не найден: {args.questions}", file=sys.stderr)
        return 1

    return run_batch(args.base_url, args.questions, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
