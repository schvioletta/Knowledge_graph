"""Оркестратор: сырой файл -> граф знаний.

Полный корпус (по умолчанию):
    python -m backend.nlp_pipeline.pipeline data/raw/*.docx data/raw/*.pdf \\
        --out data/real_graph.json

Экономный режим (выборка + только ключевые секции) — для больших корпусов,
чтобы не тратить LLM-вызовы на весь объём файлов:
    python -m backend.nlp_pipeline.pipeline data/raw/**/* \\
        --per-category 3 --strategy random --out data/real_graph.json

Смоук-тест (быстрая проверка на 20 файлах перед прогоном по всему корпусу):
    python -m backend.nlp_pipeline.pipeline data/raw/**/* \\
        --limit 20 --out data/smoke_graph.json

ingest -> [sampling по категориям] -> [извлечение секций: аннотация/методы/
результаты/заключение] -> chunking -> ner_extract (LLM против schema.py) ->
resolve (alias table) -> validate -> graph_writer (confidence +
contradictions/needs-review) -> save.

Каждый шаг логируется в stdout с меткой времени и таймингом (см. `_log`),
включая прогресс по каждому чанку — на больших корпусах это единственный
способ понять, что пайплайн не завис, а последовательно проходит файлы.

Без настроенного LLM (backend/llm_client.is_configured()) создаются только узлы
Publication — это явно логируется, чтобы не создавать иллюзию работы там, где
реального извлечения не произошло (см. README, раздел про сетевые ограничения
песочницы при разработке).

Повторные запуски не жгут LLM впустую: файлы, уже отмеченные в манифесте
(data/processed_manifest.json по умолчанию, см. nlp_pipeline/manifest.py) с тем
же sha256 содержимого, пропускаются автоматически. Изменённый файл (другой
sha256) считается новым и переобрабатывается; --force переобрабатывает всё
независимо от манифеста.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from backend.graph_store import GraphStore
from backend.ner_llm import is_ner_configured
from backend.nlp_pipeline.chunking import chunk_blocks
from backend.nlp_pipeline.graph_writer import GraphWriter
from backend.nlp_pipeline.ingest import load_document
from backend.nlp_pipeline.manifest import ProcessedManifest
from backend.nlp_pipeline.ner_extract import extract_chunk_entities
from backend.nlp_pipeline.resolve import AliasTable
from backend.nlp_pipeline.sampling import select_files
from backend.nlp_pipeline.sections import extract_key_sections

DEFAULT_ALIAS_TABLE = "data/alias_table.json"
DEFAULT_MANIFEST = "data/processed_manifest.json"
DEFAULT_CHUNK_MAX_CHARS = 2200
DEFAULT_SECTION_MAX_CHARS = 6000


def _log(msg: str, indent: int = 0) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {'  ' * indent}{msg}", flush=True)


def build_chunks(path: str, sections_only: bool, chunk_max_chars: int, section_max_chars: int):
    t0 = time.time()
    blocks, meta = load_document(path)
    ocr_pages = sum(1 for b in blocks if b.meta.get("ocr"))
    _log(f"ingest: {len(blocks)} текстовых блоков за {time.time() - t0:.1f}с (OCR-страниц: {ocr_pages})", indent=1)

    if not sections_only:
        chunks = chunk_blocks(blocks, max_chars=chunk_max_chars)
        _log(f"чанкинг (документ целиком): {len(chunks)} чанков", indent=1)
        return chunks, meta, blocks, None

    t0 = time.time()
    sections = extract_key_sections(blocks, max_chars_per_section=section_max_chars)
    _log(f"секции найдены: {sorted(sections.keys())} за {time.time() - t0:.1f}с", indent=1)

    chunks = []
    for name, section_blocks in sections.items():
        section_chunks = chunk_blocks(section_blocks, max_chars=chunk_max_chars)
        chunks.extend(section_chunks)
        chars = sum(len(b.text) for b in section_blocks)
        _log(f"  '{name}': {len(section_blocks)} блоков, {chars} симв. -> {len(section_chunks)} чанков", indent=1)

    return chunks, meta, blocks, sorted(sections.keys())


def process_file(writer: GraphWriter, path: str, sections_only: bool, chunk_max_chars: int, section_max_chars: int) -> dict:
    chunks, meta, blocks, sections_found = build_chunks(path, sections_only, chunk_max_chars, section_max_chars)

    results = []
    for i, c in enumerate(chunks, start=1):
        t0 = time.time()
        result = extract_chunk_entities(c.text)
        dt = time.time() - t0
        _log(
            f"чанк {i}/{len(chunks)} (lang={c.language}, {len(c.text)} симв.) -> "
            f"сущностей: {len(result.entities)}, связей: {len(result.relations)} ({dt:.1f}с)",
            indent=1,
        )
        results.append(result)

    stats_before = dict(writer.stats)
    writer.write_document(path, meta, results)
    delta = {k: writer.stats[k] - stats_before[k] for k in writer.stats}
    _log(
        f"граф: +{delta['entities_created']} новых сущностей, +{delta['entities_reused']} переиспользовано, "
        f"+{delta['relations']} связей, +{delta['needs_review']} NEEDS_REVIEW",
        indent=1,
    )

    return {
        "chunks": len(chunks),
        "ocr_pages": sum(1 for b in blocks if b.meta.get("ocr")),
        "languages": sorted({c.language for c in chunks}) if chunks else [],
        "sections_found": sections_found,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="NLP-пайплайн извлечения сущностей из документов в граф знаний")
    parser.add_argument("files", nargs="+", help="Пути к .docx/.pptx/.pdf файлам (можно с масками)")
    parser.add_argument("--out", default="data/real_graph.json", help="Куда сохранить результирующий граф")
    parser.add_argument("--base", default=None, help="Существующий граф для дополнения (JSON)")
    parser.add_argument("--alias-table", default=DEFAULT_ALIAS_TABLE, help="Путь к персистентной таблице алиасов")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST,
                         help="Путь к манифесту обработанных файлов (по sha256 содержимого) — "
                              "файлы, уже обработанные без изменений, пропускаются без LLM-вызовов")
    parser.add_argument("--force", action="store_true",
                         help="Игнорировать манифест и переобработать все файлы, даже уже отмеченные")

    parser.add_argument("--per-category", type=int, default=None,
                         help="Взять не более N файлов из каждой категории (по подпапке в --raw-root, "
                              "либо по расширению, если файлы лежат плоско). Без флага обрабатываются все переданные файлы.")
    parser.add_argument("--strategy", default="random", choices=["random", "largest", "newest", "most_tables"],
                         help="Как выбирать файлы внутри категории при --per-category (default: random)")
    parser.add_argument("--seed", type=int, default=42, help="Seed для воспроизводимой случайной выборки")
    parser.add_argument("--raw-root", default="data/raw", help="Корень сырых данных для определения категории по подпапке")

    parser.add_argument("--limit", type=int, default=None,
                         help="Смоук-режим: обработать только первые N файлов из итогового списка "
                              "(после --per-category, если он задан) — быстрая проверка, что пайплайн "
                              "работает, прежде чем гонять на всём корпусе.")

    parser.add_argument("--full-document", action="store_true",
                         help="Обрабатывать весь документ целиком, а не только аннотацию/методы/результаты/заключение")
    parser.add_argument("--chunk-max-chars", type=int, default=DEFAULT_CHUNK_MAX_CHARS)
    parser.add_argument("--section-max-chars", type=int, default=DEFAULT_SECTION_MAX_CHARS,
                         help="Максимум символов на секцию (аннотация/методы/результаты/заключение)")
    args = parser.parse_args()

    run_t0 = time.time()

    _log("=== Этап 0: отбор файлов ===")
    files_to_process: list[str]
    if args.per_category is not None:
        selected = select_files(args.files, raw_root=args.raw_root, per_category=args.per_category,
                                 strategy=args.strategy, seed=args.seed)
        _log(f"категорий: {len(selected)}, стратегия={args.strategy!r}, seed={args.seed}", indent=1)
        files_to_process = []
        for category, paths in selected.items():
            names = ", ".join(p.name for p in paths)
            _log(f"{category}: {len(paths)} файл(ов) -> {names}", indent=1)
            files_to_process.extend(str(p) for p in paths)
    else:
        all_inputs = list(args.files)
        files_to_process = [f for f in all_inputs if Path(f).is_file()]
        skipped = len(all_inputs) - len(files_to_process)
        if skipped:
            _log(f"отбор не применяется, файлов на вход: {len(files_to_process)} "
                 f"(пропущено не-файлов, напр. директорий из маски: {skipped})", indent=1)
        else:
            _log(f"отбор не применяется, файлов на вход: {len(files_to_process)}", indent=1)

    manifest = ProcessedManifest(args.manifest)
    if args.force:
        _log("манифест: --force задан, повторно обрабатываю все файлы независимо от манифеста", indent=1)
    else:
        before = len(files_to_process)
        already_done = [f for f in files_to_process if manifest.is_processed(f)]
        if already_done:
            already_done_set = set(already_done)
            files_to_process = [f for f in files_to_process if f not in already_done_set]
            _log(
                f"манифест ({args.manifest}): пропущено {len(already_done)}/{before} файл(ов), уже "
                f"обработанных без изменений содержимого — LLM-вызовы на них не тратятся "
                f"(--force для принудительного повтора)",
                indent=1,
            )

    if args.limit is not None and len(files_to_process) > args.limit:
        _log(f"смоук-режим: ограничиваю {len(files_to_process)} файл(ов) до первых {args.limit}", indent=1)
        files_to_process = files_to_process[:args.limit]

    sections_only = not args.full_document

    gs = GraphStore()
    if args.base and Path(args.base).exists():
        gs.load(args.base)
        _log(f"базовый граф загружен из {args.base}: {gs.g.number_of_nodes()} узлов", indent=1)

    alias_table = AliasTable(args.alias_table)
    writer = GraphWriter(gs, alias_table)

    if not is_ner_configured():
        _log(
            "ВНИМАНИЕ: NER LLM не сконфигурирован (NER_USE_OLLAMA + модель или GIGACHAT_API_KEY) — "
            "будут созданы только узлы Publication без извлечённых сущностей."
        )

    _log(f"=== Этап 1-6: обработка {len(files_to_process)} файл(ов) "
         f"[{'только ключевые секции' if sections_only else 'документы целиком'}] ===")

    total_chunks = 0
    for idx, f in enumerate(files_to_process, start=1):
        file_t0 = time.time()
        _log(f"--- файл {idx}/{len(files_to_process)}: {f} ---")
        info = process_file(writer, f, sections_only, args.chunk_max_chars, args.section_max_chars)
        total_chunks += info["chunks"]
        manifest.mark_processed(f)
        _log(f"файл обработан за {time.time() - file_t0:.1f}с ({info['chunks']} чанков)", indent=1)

    _log("=== Итог ===")
    _log(
        f"вызовов LLM (1 на чанк): {total_chunks} на {len(files_to_process)} файл(ов), "
        f"общее время: {time.time() - run_t0:.1f}с",
        indent=1,
    )
    _log(
        f"создано сущностей {writer.stats['entities_created']}, "
        f"переиспользовано {writer.stats['entities_reused']}, связей {writer.stats['relations']}, "
        f"предупреждений валидации {writer.stats['validation_warnings']}, "
        f"пар NEEDS_REVIEW {writer.stats['needs_review']}",
        indent=1,
    )

    alias_table.save()
    manifest.save()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gs.save(out_path)
    _log(f"граф сохранён в {out_path} ({gs.g.number_of_nodes()} узлов, {gs.g.number_of_edges()} рёбер)", indent=1)


if __name__ == "__main__":
    main()
