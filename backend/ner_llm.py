"""LLM-клиент для NER (backend/nlp_pipeline/ner_extract.py).

При NER_USE_OLLAMA=1 — локальный Qwen через Ollama; при ошибке fallback на
активный бэкенд llm_client (GigaChat или YandexGPT по LLM_BACKEND /
INDEX_USE_YANDEX). Иначе только llm_client.
"""
from __future__ import annotations

import os
from typing import Optional

from backend.llm_cache import get as cache_get
from backend.llm_cache import make_key as cache_make_key
from backend.llm_cache import put as cache_put
from backend.llm_client import complete
from backend.llm_client import get_last_error as llm_get_last_error
from backend.llm_client import is_configured
from backend.llm_client import llm_backend

_CACHE_NS = "ner"
_last_error: Optional[str] = None
_ollama_client = None


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def use_ollama_for_ner() -> bool:
    return _env_truthy("NER_USE_OLLAMA")


def _ollama_model() -> str:
    return os.getenv("NER_OLLAMA_MODEL") or os.getenv("QUERY_EXPAND_MODEL", "")


def _ollama_base_url() -> str:
    return os.getenv("NER_OLLAMA_BASE_URL") or os.getenv(
        "QUERY_EXPAND_BASE_URL", "http://localhost:11434/v1"
    )


def _ollama_timeout() -> float:
    raw = os.getenv("NER_OLLAMA_TIMEOUT_SEC") or os.getenv("QUERY_EXPAND_TIMEOUT_SEC", "120")
    return float(raw)


def is_ollama_configured() -> bool:
    return use_ollama_for_ner() and bool(_ollama_model())


def is_ner_configured() -> bool:
    return is_ollama_configured() or is_configured()


def get_last_error() -> Optional[str]:
    return _last_error


def _get_ollama_client():
    global _ollama_client
    if _ollama_client is None:
        from openai import OpenAI

        _ollama_client = OpenAI(
            base_url=_ollama_base_url(),
            api_key=os.getenv("NER_OLLAMA_API_KEY") or os.getenv("QUERY_EXPAND_API_KEY", "ollama"),
        )
    return _ollama_client


def _cache_key(prompt: str, system: Optional[str], temperature: float) -> str:
    temp = max(temperature, 1e-6)
    backend = "ollama" if is_ollama_configured() else llm_backend()
    model = _ollama_model() if backend == "ollama" else (
        os.getenv("YANDEX_MODEL", "aliceai-llm-flash")
        if backend == "yandex"
        else os.getenv("GIGACHAT_MODEL", "GigaChat")
    )
    return cache_make_key(
        "ner",
        backend,
        model,
        _ollama_base_url() if backend == "ollama" else "",
        str(temp),
        system or "",
        prompt,
    )


def _complete_ollama(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = _get_ollama_client().chat.completions.create(
        model=_ollama_model(),
        messages=messages,
        temperature=temperature,
        timeout=_ollama_timeout(),
    )
    content = response.choices[0].message.content
    return content.strip() if content else None


def complete_ner(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.0,
) -> Optional[str]:
    """Единая точка NER-вызова. None — нет бэкенда или ошибка (см. get_last_error)."""
    global _last_error

    if not is_ner_configured():
        _last_error = "не сконфигурирован (NER_USE_OLLAMA + модель или LLM-ключи)"
        return None

    key = _cache_key(prompt, system, temperature)
    cached = cache_get(_CACHE_NS, key)
    if cached is not None:
        _last_error = None
        return cached

    temp = max(temperature, 1e-6)

    if is_ollama_configured():
        try:
            result = _complete_ollama(prompt, system, temp)
            if result:
                cache_put(_CACHE_NS, key, result)
                _last_error = None
                return result
            _last_error = "Ollama вернул пустой ответ"
        except Exception as e:
            _last_error = f"Ollama: {type(e).__name__}: {e}"
            print(f"[ner_llm] {_last_error}")

    if is_configured():
        result = complete(prompt, system, temperature)
        if result is not None:
            cache_put(_CACHE_NS, key, result)
            _last_error = None
            return result
        _last_error = llm_get_last_error() or f"{llm_backend()} fallback не удался"
        return None

    return None
