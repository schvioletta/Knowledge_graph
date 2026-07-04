"""LLM-клиент только для расширения поискового запроса.

Приоритет: локальный Qwen через Ollama (OpenAI-совместимый API) → fallback на
GigaChat через backend.llm_client. Остальной пайплайн (NER, RAG-ответ) GigaChat
не затрагивает.
"""
from __future__ import annotations

import json
import os
from typing import Literal, Optional

from backend.llm_cache import get as cache_get
from backend.llm_cache import make_key as cache_make_key
from backend.llm_cache import put as cache_put
from backend.llm_client import complete
from backend.llm_client import is_configured
from backend.llm_client import llm_backend

ExpandSource = Literal["ollama", "gigachat", "yandex"]

_CACHE_NS = "query_expand"
_last_error: Optional[str] = None
_ollama_client = None


def _get_ollama_client():
    global _ollama_client
    if _ollama_client is None:
        from openai import OpenAI

        _ollama_client = OpenAI(
            base_url=os.getenv("QUERY_EXPAND_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("QUERY_EXPAND_API_KEY", "ollama"),
        )
    return _ollama_client


def is_ollama_configured() -> bool:
    return bool(os.getenv("QUERY_EXPAND_MODEL"))


def is_query_expand_available() -> bool:
    return is_ollama_configured() or is_configured()


def get_last_error() -> Optional[str]:
    return _last_error


def _complete_ollama(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    timeout = float(os.getenv("QUERY_EXPAND_TIMEOUT_SEC", "15"))
    response = _get_ollama_client().chat.completions.create(
        model=os.environ["QUERY_EXPAND_MODEL"],
        messages=messages,
        temperature=temperature,
        timeout=timeout,
    )
    content = response.choices[0].message.content
    return content.strip() if content else None


def _expand_cache_key(prompt: str, system: Optional[str], temperature: float) -> str:
    return cache_make_key(
        "query_expand",
        os.getenv("QUERY_EXPAND_MODEL", ""),
        os.getenv("QUERY_EXPAND_BASE_URL", "http://localhost:11434/v1"),
        llm_backend(),
        os.getenv("YANDEX_MODEL", "yandexgpt-5-pro"),
        os.getenv("GIGACHAT_MODEL", "GigaChat"),
        str(temperature),
        system or "",
        prompt,
    )


def complete_query_expand(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.2,
) -> tuple[Optional[str], Optional[ExpandSource]]:
    """Возвращает (текст ответа, источник) или (None, None) при полном провале."""
    global _last_error

    key = _expand_cache_key(prompt, system, temperature)
    cached = cache_get(_CACHE_NS, key)
    if cached is not None:
        try:
            payload = json.loads(cached)
            _last_error = None
            return payload["result"], payload["source"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    if is_ollama_configured():
        try:
            result = _complete_ollama(prompt, system, temperature)
            if result:
                _last_error = None
                cache_put(_CACHE_NS, key, json.dumps({"result": result, "source": "ollama"}))
                return result, "ollama"
            _last_error = "Ollama вернул пустой ответ"
        except Exception as e:
            _last_error = f"Ollama: {type(e).__name__}: {e}"
            print(f"[query_expand_llm] {_last_error}")

    if is_configured():
        result = complete(prompt, system, temperature)
        if result:
            _last_error = None
            source: ExpandSource = "yandex" if llm_backend() == "yandex" else "gigachat"
            cache_put(_CACHE_NS, key, json.dumps({"result": result, "source": source}))
            return result, source
        _last_error = f"{llm_backend()} fallback не удался"

    if not is_ollama_configured() and not is_configured():
        _last_error = "не сконфигурирован (нет QUERY_EXPAND_MODEL и LLM-ключей)"

    return None, None
