"""Удалить из Neo4j все корпусные документы, кроме приоритетных 13 из README.

Файлы на диске (data/raw/**) не трогаются — только узлы RAG в Neo4j и записи
манифеста index_corpus.

Примеры:
  python -m backend.scripts.prune_corpus              # dry-run
  python -m backend.scripts.prune_corpus --apply      # удалить
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from backend.nlp_pipeline.manifest import ProcessedManifest
from backend.rag.priority_corpus import priority_corpus_paths
from backend.rag.store import Neo4jDocumentStore

DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent.parent / "data" / "corpus_index_manifest.json"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Удалить из RAG-базы корпусные документы, кроме 13 приоритетных"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Выполнить удаление (без флага — только показать, что будет удалено)",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Манифест index_corpus")
    args = parser.parse_args(argv)

    keep_paths = priority_corpus_paths(REPO_ROOT)
    store = Neo4jDocumentStore()
    manifest = ProcessedManifest(args.manifest)

    try:
        corpus = store.list_corpus_documents()
        to_remove = [d for d in corpus if d.source_path not in keep_paths]
        kept = [d for d in corpus if d.source_path in keep_paths]

        print(f"Корпус в Neo4j: {len(corpus)} документ(ов)")
        print(f"Оставить (приоритет): {len(kept)}")
        print(f"Удалить: {len(to_remove)}")

        if kept:
            print("\n— останутся —")
            for d in kept:
                print(f"  {d.id}  {Path(d.source_path).name}")

        if not to_remove:
            print("\nНечего удалять.")
            return 0

        print("\n— будут удалены —" if args.apply else "\n— dry-run: будут удалены —")
        for d in to_remove:
            print(f"  {d.id}  {d.source_path}")

        if not args.apply:
            print("\nДобавьте --apply для удаления.")
            return 0

        removed = 0
        for d in to_remove:
            if store.remove_corpus_document(d.id):
                removed += 1
                if d.source_path in manifest.data:
                    del manifest.data[d.source_path]

        manifest.save()
        print(f"\nУдалено из Neo4j: {removed}/{len(to_remove)}")
        print(f"Записей убрано из манифеста: {len(to_remove)}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
