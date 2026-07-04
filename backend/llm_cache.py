"""In-process LRU cache for LLM completions (same prompt → no repeat API call)."""
from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from typing import Optional

_LOCK = threading.Lock()
_STORE: dict[str, OrderedDict[str, str]] = {}


def max_size() -> int:
    return int(os.getenv("LLM_CACHE_SIZE", "512"))


def make_key(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def get(namespace: str, key: str) -> Optional[str]:
    limit = max_size()
    if limit <= 0:
        return None
    with _LOCK:
        bucket = _STORE.setdefault(namespace, OrderedDict())
        if key not in bucket:
            return None
        bucket.move_to_end(key)
        return bucket[key]


def put(namespace: str, key: str, value: str) -> None:
    limit = max_size()
    if limit <= 0:
        return
    with _LOCK:
        bucket = _STORE.setdefault(namespace, OrderedDict())
        bucket[key] = value
        bucket.move_to_end(key)
        while len(bucket) > limit:
            bucket.popitem(last=False)
