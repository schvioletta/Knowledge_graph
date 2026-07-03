"""Провайдер-независимый клиент для вызова LLM в экстракторе сущностей.

Дизайн специально рассчитан на замену модели без изменения кода экстрактора
(сейчас — GigaChat, в будущем — любая быстрая небольшая модель): выбор бэкенда
идёт через переменные окружения, единая точка входа — `complete()`.

Поддерживаемые бэкенды:
- OpenAI-совместимый HTTP-эндпоинт (Groq/Together/vLLM/Ollama/LM Studio и т.п.):
  LLM_API_BASE, LLM_API_KEY (может быть пустым для локальных серверов), LLM_MODEL.
- GigaChat (уже используется в rag_qdrant.py и hybrid_retriever.py):
  GIGACHAT_API_KEY, GIGACHAT_MODEL.

Если ни один бэкенд не сконфигурирован, `complete()` возвращает None —
вызывающий код должен уметь работать без LLM (детерминированный fallback).
"""
from __future__ import annotations

import os
from typing import Optional


def _complete_openai_compatible(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    import requests

    base = os.environ["LLM_API_BASE"].rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = requests.post(
        f"{base}/chat/completions",
        json={"model": model, "messages": messages, "temperature": temperature},
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _complete_gigachat(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    from gigachat import GigaChat
    from gigachat.models import Chat, Messages, MessagesRole

    messages = []
    if system:
        messages.append(Messages(role=MessagesRole.SYSTEM, content=system))
    messages.append(Messages(role=MessagesRole.USER, content=prompt))

    with GigaChat(
        credentials=os.environ["GIGACHAT_API_KEY"],
        model=os.getenv("GIGACHAT_MODEL", "GigaChat"),
        verify_ssl_certs=False,
        scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
    ) as client:
        chat = Chat(messages=messages, temperature=max(temperature, 0.01))
        response = client.chat(chat)
        return response.choices[0].message.content


def complete(prompt: str, system: Optional[str] = None, temperature: float = 0.0) -> Optional[str]:
    """Единая точка вызова LLM. Возвращает None, если нет доступного бэкенда
    или произошла ошибка (вызывающий код должен деградировать gracefully)."""
    provider = os.getenv("LLM_PROVIDER")
    try:
        if provider == "openai_compatible" or (not provider and os.getenv("LLM_API_BASE")):
            return _complete_openai_compatible(prompt, system, temperature)
        if provider == "gigachat" or (not provider and os.getenv("GIGACHAT_API_KEY")):
            return _complete_gigachat(prompt, system, temperature)
    except Exception as e:
        print(f"[llm_client] Ошибка вызова LLM: {e}")
        return None
    return None


def is_configured() -> bool:
    return bool(os.getenv("LLM_API_BASE") or os.getenv("GIGACHAT_API_KEY"))
