"""Обязательные источники для пайплайна — всегда попадают в граф, даже при --limit и --per-category."""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INCLUDES = PROJECT_ROOT / "data" / "graph_includes.json"


def load_include_paths(config_path: str | Path | None = DEFAULT_INCLUDES) -> list[str]:
    paths: list[str] = []
    cfg = Path(config_path) if config_path else DEFAULT_INCLUDES
    if not cfg.is_file():
        return paths
    raw = json.loads(cfg.read_text(encoding="utf-8"))
    for item in raw.get("paths", []):
        if item:
            paths.append(str(item))
    return paths


def resolve_include_files(
    include_paths: list[str],
    project_root: Path | None = None,
) -> list[str]:
    root = project_root or PROJECT_ROOT
    resolved: list[str] = []
    seen: set[str] = set()
    for item in include_paths:
        p = Path(item)
        if not p.is_absolute():
            p = root / p
        p = p.resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Обязательный файл для графа не найден: {p}")
        key = str(p)
        if key not in seen:
            seen.add(key)
            resolved.append(key)
    return resolved


def merge_with_includes(primary: list[str], includes: list[str]) -> list[str]:
    """Обязательные файлы — в начале списка, без дубликатов."""
    merged: list[str] = []
    seen: set[str] = set()
    for f in includes + primary:
        key = str(Path(f).resolve())
        if key not in seen:
            seen.add(key)
            merged.append(key)
    return merged


def apply_limit_preserving_includes(files: list[str], includes: list[str], limit: int | None) -> list[str]:
    if limit is None:
        return files
    include_set = {str(Path(p).resolve()) for p in includes}
    pinned = [f for f in files if str(Path(f).resolve()) in include_set]
    rest = [f for f in files if str(Path(f).resolve()) not in include_set]
    if len(pinned) >= limit:
        return pinned
    return pinned + rest[: limit - len(pinned)]
