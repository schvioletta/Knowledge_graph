"""CLI: пакетная индексация корпуса data/raw/** для RAG.

Извлекает метаданные (LLM + fallback) и чанки полного текста документа → Neo4j.
Дополнительная активация по запросу — через activate_for_query().
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from backend.nlp_pipeline.ingest import LOADERS, file_meta, load_document
from backend.nlp_pipeline.manifest import ProcessedManifest, file_sha256
from backend.rag.metadata_extract import extract_metadata
from backend.rag.store import Neo4jDocumentStore

DEFAULT_RAW_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent.parent / "data" / "corpus_index_manifest.json"


def collect_files(raw_root: Path) -> list[Path]:
    files: list[Path] = []
    for ext in LOADERS:
        files.extend(raw_root.rglob(f"*{ext}"))
    uploads = raw_root / "uploads"
    return sorted(
        p for p in files
        if p.is_file() and not str(p).startswith(str(uploads))
    )


def _progress_label(current: int, total: int) -> str:
    remaining = total - current
    return f"[{current}/{total}] (осталось {remaining})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Индексация корпуса для RAG (полный текст + метаданные)")
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Конкретные файлы (если не указаны — сканируется --raw-root)",
    )
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT, help="Корень корпуса")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Файл манифеста")
    parser.add_argument("--force", action="store_true", help="Переиндексировать даже без изменений")
    parser.add_argument(
        "--yandex",
        action="store_true",
        help="Метаданные через YandexGPT (INDEX_USE_YANDEX=1, нужны YANDEX_API_KEY/YANDEX_FOLDER_ID)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Макс. число файлов (0 = все, только без явного списка files)")
    args = parser.parse_args(argv)

    from backend.llm_client import log_llm_startup

    log_llm_startup()

    if args.yandex:
        os.environ["INDEX_USE_YANDEX"] = "1"

    if args.files:
        files: list[Path] = []
        for p in args.files:
            path = p.expanduser().resolve()
            if not path.is_file():
                print(f"Файл не найден: {path}", file=sys.stderr)
                return 1
            if path.suffix.lower() not in LOADERS:
                print(f"Неподдерживаемый формат: {path}", file=sys.stderr)
                return 1
            files.append(path)
    else:
        raw_root = args.raw_root.resolve()
        if not raw_root.exists():
            print(f"Корень корпуса не найден: {raw_root}", file=sys.stderr)
            return 1
        files = collect_files(raw_root)
        if args.limit > 0:
            files = files[: args.limit]

    if not files:
        print("Файлы для индексации не заданы")
        return 0

    total = len(files)
    print(f"Индексация: {total} файл(ов)")

    manifest = ProcessedManifest(args.manifest)
    store = Neo4jDocumentStore()

    indexed = skipped = errors = 0
    try:
        for i, path in enumerate(files, start=1):
            tag = _progress_label(i, total)
            rel = str(path.resolve())
            if not args.force and manifest.is_processed(rel):
                skipped += 1
                print(f"{tag} skip  {path.name}")
                continue
            try:
                blocks, _ = load_document(path)
                fmeta = file_meta(path)
                metadata = extract_metadata(blocks, fmeta)
                fhash = file_sha256(path)
                _meta, is_dup = store.index_document(path, metadata, blocks, fhash, force=args.force)
                if is_dup and not args.force:
                    skipped += 1
                    print(f"{tag} skip  {path.name} (уже в Neo4j)")
                else:
                    indexed += 1
                    print(f"{tag} ok    {path.name} → {_meta.id} ({_meta.num_chunks} abstract chunks)")
                manifest.mark_processed(rel)
            except Exception as e:
                errors += 1
                print(f"{tag} ERR   {path.name}: {e}", file=sys.stderr)
        manifest.save()
    finally:
        store.close()

    done = indexed + skipped + errors
    print(
        f"\nГотово: обработано {done}/{total} | "
        f"indexed={indexed}, skipped={skipped}, errors={errors}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
