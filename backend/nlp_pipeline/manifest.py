"""Этап 0б: манифест обработанных файлов — чтобы повторный запуск пайплайна не
тратил LLM-вызовы (и деньги) на файлы, которые уже есть в графе и не менялись
с прошлого прогона.

Ключ идентичности файла — sha256 содержимого, а не путь/mtime: переименование
или копирование файла не считается «новым» файлом, а правка содержимого —
считается (и тогда файл переобрабатывается, а не пропускается молча).
"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path


def file_sha256(path: str | Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


class ProcessedManifest:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        # {"data/raw/foo.docx": {"sha256": "...", "processed_at": "2026-07-03T12:00:00"}}
        self.data: dict[str, dict[str, str]] = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_processed(self, path: str | Path) -> bool:
        entry = self.data.get(str(path))
        if not entry:
            return False
        return entry.get("sha256") == file_sha256(path)

    def mark_processed(self, path: str | Path) -> None:
        self.data[str(path)] = {
            "sha256": file_sha256(path),
            "processed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
