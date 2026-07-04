"""LLM-клиент только для расширения поискового запроса.

Приоритет: локальный Qwen через Ollama (OpenAI-совместимый API) → fallback на
GigaChat через backend.llm_client. Остальной пайплайн (NER, RAG-ответ) GigaChat
не затрагивает.
"""
from __future__ import annotations

import os
from typing import Literal, Optional

from backend.llm_client import complete as complete_gigachat
from backend.llm_client import is_configured as is_gigachat_configured

ExpandSource = Literal["ollama", "gigachat"]

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
    return is_ollama_configured() or is_gigachat_configured()


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


def complete_query_expand(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.2,
) -> tuple[Optional[str], Optional[ExpandSource]]:
    """Возвращает (текст ответа, источник) или (None, None) при полном провале."""
    global _last_error

    if is_ollama_configured():
        try:
            result = _complete_ollama(prompt, system, temperature)
            if result:
                _last_error = None
                return result, "ollama"
            _last_error = "Ollama вернул пустой ответ"
        except Exception as e:
            _last_error = f"Ollama: {type(e).__name__}: {e}"
            print(f"[query_expand_llm] {_last_error}")

    if is_gigachat_configured():
        result = complete_gigachat(prompt, system, temperature)
        if result:
            _last_error = None
            return result, "gigachat"
        _last_error = "GigaChat fallback не удался"

    if not is_ollama_configured() and not is_gigachat_configured():
        _last_error = "не сконфигурирован (нет QUERY_EXPAND_MODEL и GIGACHAT_API_KEY)"

    return None, None
