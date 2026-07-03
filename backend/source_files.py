"""Поиск и отдача исходных документов из локального каталога data/raw."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_ROOT = Path(os.getenv("RAW_DATA_PATH") or (PROJECT_ROOT / "data" / "raw"))


@lru_cache(maxsize=1)
def _basename_index() -> dict[str, Path]:
    if not RAW_ROOT.is_dir():
        return {}
    index: dict[str, Path] = {}
    for path in RAW_ROOT.rglob("*"):
        if not path.is_file():
            continue
        key = path.name.casefold()
        if key not in index or len(path.parts) < len(index[key].parts):
            index[key] = path
    return index


def resolve_source_file(source_file: str) -> Path | None:
    name = Path(source_file).name.strip()
    if not name or name in {".", ".."}:
        return None
    index = _basename_index()
    return index.get(name.casefold())


def publication_source_file(
    pub_row: dict[str, Any],
    exp: dict[str, Any],
    detail: dict[str, Any],
    gs_node: Optional[dict[str, Any]] = None,
) -> str:
    """Имя файла только из данных графа — без выдуманных сопоставлений."""
    node = gs_node or {}
    candidates = [
        pub_row.get("source_file"),
        node.get("source_file"),
        exp.get("source_file"),
        detail.get("source_file"),
        *(node.get("sources") or []),
        *(exp.get("sources") or []),
        *(detail.get("sources") or []),
    ]
    for candidate in candidates:
        name = str(candidate or "").strip()
        if name:
            return Path(name).name
    return ""


def source_file_meta(source_file: str) -> dict[str, str | bool]:
    name = Path(source_file).name.strip() if source_file else ""
    if not name:
        return {"file_available": False, "file_url": ""}
    path = resolve_source_file(name)
    if path is None:
        return {"file_available": False, "file_url": ""}
    return {
        "file_available": True,
        "file_url": f"/api/sources/file?name={quote(path.name)}",
    }
