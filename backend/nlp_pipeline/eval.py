"""Оценка качества извлечения: precision/recall/F1 сущностей и связей против
небольшого ручного golden-набора (data/golden/*.json).

Golden-файл — это ExtractionResult в том же формате, что должен вернуть LLM
(entities с tmp_id/type/name, relations с source/target/type), плюс поля
source_file и chunk_text (фрагмент реального документа, на котором проверяем).

Запуск:
    python -m backend.nlp_pipeline.eval data/golden

Если LLM не сконфигурирован — команда явно сообщает об этом и не притворяется,
что посчитала реальные метрики (без API ключа предсказание всегда пустое).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.lexicon import name_similarity
from backend.llm_client import is_configured
from backend.nlp_pipeline.ner_extract import ExtractionResult, RawEntity, RawRelation, extract_chunk_entities

NAME_SIM_THRESHOLD = 0.5


def _load_golden(path: Path) -> tuple[ExtractionResult, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    golden = ExtractionResult(entities=data["entities"], relations=data["relations"])
    return golden, data["chunk_text"]


def match_entities(predicted: list[RawEntity], golden: list[RawEntity]) -> tuple[int, int, int, dict[str, str]]:
    """Жадное сопоставление по (type, схожесть имени). Возвращает (tp, fp, fn,
    отображение tmp_id предсказанной сущности -> tmp_id golden-сущности)."""
    unmatched_golden = list(golden)
    mapping: dict[str, str] = {"pub": "pub"}
    tp = 0
    for p in predicted:
        best, best_score = None, 0.0
        for g in unmatched_golden:
            if g.type != p.type:
                continue
            score = name_similarity(p.name, g.name)
            if score > best_score:
                best, best_score = g, score
        if best is not None and best_score >= NAME_SIM_THRESHOLD:
            tp += 1
            mapping[p.tmp_id] = best.tmp_id
            unmatched_golden.remove(best)
    fp = len(predicted) - tp
    fn = len(unmatched_golden)
    return tp, fp, fn, mapping


def match_relations(predicted: list[RawRelation], golden: list[RawRelation], id_map: dict[str, str]) -> tuple[int, int, int]:
    golden_set = {(g.source, g.target, g.type) for g in golden}
    matched = set()
    tp = 0
    for p in predicted:
        key = (id_map.get(p.source, p.source), id_map.get(p.target, p.target), p.type)
        if key in golden_set and key not in matched:
            tp += 1
            matched.add(key)
    fp = len(predicted) - tp
    fn = len(golden_set) - len(matched)
    return tp, fp, fn


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def evaluate_file(path: Path) -> dict:
    golden, chunk_text = _load_golden(path)
    predicted = extract_chunk_entities(chunk_text)

    e_tp, e_fp, e_fn, id_map = match_entities(predicted.entities, golden.entities)
    r_tp, r_fp, r_fn = match_relations(predicted.relations, golden.relations, id_map)

    e_p, e_r, e_f1 = prf(e_tp, e_fp, e_fn)
    r_p, r_r, r_f1 = prf(r_tp, r_fp, r_fn)
    return {
        "file": path.name,
        "entities": {"tp": e_tp, "fp": e_fp, "fn": e_fn, "precision": e_p, "recall": e_r, "f1": e_f1},
        "relations": {"tp": r_tp, "fp": r_fp, "fn": r_fn, "precision": r_p, "recall": r_r, "f1": r_f1},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Precision/recall NLP-экстрактора на golden-наборе")
    parser.add_argument("golden_dir", nargs="?", default="data/golden")
    args = parser.parse_args()

    if not is_configured():
        print(
            "ВНИМАНИЕ: LLM не сконфигурирован — предсказание всегда будет пустым, "
            "метрики ниже не отражают реальное качество экстрактора. Задайте "
            "YANDEX_API_KEY/YANDEX_FOLDER_ID и повторите запуск."
        )

    files = sorted(Path(args.golden_dir).glob("*.json"))
    if not files:
        print(f"Golden-файлы не найдены в {args.golden_dir}")
        return

    results = [evaluate_file(f) for f in files]

    tot_e = {"tp": 0, "fp": 0, "fn": 0}
    tot_r = {"tp": 0, "fp": 0, "fn": 0}
    for res in results:
        print(f"\n{res['file']}")
        print(f"  entities:  P={res['entities']['precision']:.2f} R={res['entities']['recall']:.2f} F1={res['entities']['f1']:.2f} "
              f"(tp={res['entities']['tp']} fp={res['entities']['fp']} fn={res['entities']['fn']})")
        print(f"  relations: P={res['relations']['precision']:.2f} R={res['relations']['recall']:.2f} F1={res['relations']['f1']:.2f} "
              f"(tp={res['relations']['tp']} fp={res['relations']['fp']} fn={res['relations']['fn']})")
        for k in ("tp", "fp", "fn"):
            tot_e[k] += res["entities"][k]
            tot_r[k] += res["relations"][k]

    ep, er, ef1 = prf(**tot_e)
    rp, rr, rf1 = prf(**tot_r)
    print("\n=== ИТОГО ===")
    print(f"entities:  P={ep:.2f} R={er:.2f} F1={ef1:.2f}")
    print(f"relations: P={rp:.2f} R={rr:.2f} F1={rf1:.2f}")


if __name__ == "__main__":
    main()
