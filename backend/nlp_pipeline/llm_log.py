"""Запись полных обменов с LLM при построении графа (prompt + response + parse result).

Каталог по умолчанию: data/llm_logs/ (gitignored). Переопределение: env LLM_LOG_DIR
или CLI --llm-log-dir. Отключение: --no-llm-log.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

DEFAULT_LLM_LOG_DIR = "data/llm_logs"
MAX_CONTEXTS_PER_NODE = 10


def default_log_root(project_root: Optional[Path] = None) -> Path:
    root = project_root or Path(__file__).resolve().parent.parent.parent
    custom = os.getenv("LLM_LOG_DIR")
    if custom:
        p = Path(custom)
        return p if p.is_absolute() else root / p
    return root / DEFAULT_LLM_LOG_DIR


def _safe_dir_name(name: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^\w\-.]+", "_", name, flags=re.UNICODE).strip("._")
    if not cleaned:
        cleaned = "unknown"
    return cleaned[:max_len]


@dataclass
class LlmLogSession:
    """Один прогон пайплайна — подкаталог с timestamp."""

    run_dir: Path
    enabled: bool = True
    _file_dirs: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def start(cls, log_root: Path, enabled: bool = True) -> LlmLogSession:
        if not enabled:
            return cls(run_dir=log_root, enabled=False)
        ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
        run_dir = log_root / ts
        run_dir.mkdir(parents=True, exist_ok=True)
        return cls(run_dir=run_dir, enabled=True)

    def file_dir(self, source_path: str) -> Path:
        stem = _safe_dir_name(Path(source_path).stem)
        if stem not in self._file_dirs:
            d = self.run_dir / stem
            d.mkdir(parents=True, exist_ok=True)
            self._file_dirs[stem] = d
        return self._file_dirs[stem]


@dataclass
class LlmLogContext:
    session: LlmLogSession
    source_path: str
    source_file: str
    chunk_index: int
    chunk_total: int
    chunk_language: str = ""
    chunk_locations: list[str] = field(default_factory=list)
    chunk_kind: str = ""


def log_llm_exchange(
    ctx: LlmLogContext,
    *,
    system_prompt: str,
    chunk_text: str,
    raw_response: Optional[str],
    parse_ok: bool,
    parsed: Optional[dict[str, Any]] = None,
    parse_error: Optional[str] = None,
) -> None:
    if not ctx.session.enabled:
        return

    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source_file": ctx.source_file,
        "source_path": ctx.source_path,
        "chunk_index": ctx.chunk_index,
        "chunk_total": ctx.chunk_total,
        "chunk_language": ctx.chunk_language,
        "chunk_locations": ctx.chunk_locations,
        "chunk_kind": ctx.chunk_kind,
        "system_prompt": system_prompt,
        "chunk_text": chunk_text,
        "raw_response": raw_response,
        "parse_ok": parse_ok,
        "parsed": parsed,
        "parse_error": parse_error,
    }

    out_dir = ctx.session.file_dir(ctx.source_path)
    out_path = out_dir / f"chunk_{ctx.chunk_index:03d}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def truncate_snippet(text: str, max_chars: int = 500) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
