"""Клиент для вызова YandexGPT в экстракторе сущностей.

Единая точка входа — `complete()`. Ключ и folder ID берутся из переменных
окружения YANDEX_API_KEY/YANDEX_FOLDER_ID (не хранятся в коде — иначе секрет
попадёт в git). YANDEX_MODEL по умолчанию "yandexgpt-5-pro".

Если бэкенд не сконфигурирован, `complete()` возвращает None — вызывающий
код должен уметь работать без LLM (детерминированный fallback).
"""
from __future__ import annotations

import os
from typing import Optional


def _complete_yandexgpt(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    import openai

    folder_id = os.environ["YANDEX_FOLDER_ID"]
    api_key = os.environ["YANDEX_API_KEY"]
    model = os.getenv("YANDEX_MODEL", "yandexgpt-5-pro")

    client = openai.OpenAI(
        api_key=api_key,
        project=folder_id,
        base_url="https://ai.api.cloud.yandex.net/v1",
    )
    parts = [system, prompt] if system else [prompt]
    response = client.responses.create(
        model=f"gpt://{folder_id}/{model}",
        input="\n\n".join(parts),
        temperature=temperature,
        max_output_tokens=2000,
    )
    return response.output[0].content[0].text


def complete(prompt: str, system: Optional[str] = None, temperature: float = 0.0) -> Optional[str]:
    """Единая точка вызова LLM. Возвращает None, если нет доступного бэкенда
    или произошла ошибка (вызывающий код должен деградировать gracefully)."""
    if not is_configured():
        return None
    try:
        return _complete_yandexgpt(prompt, system, temperature)
    except Exception as e:
        print(f"[llm_client] Ошибка вызова LLM: {e}")
        return None


def is_configured() -> bool:
    return bool(os.getenv("YANDEX_API_KEY") and os.getenv("YANDEX_FOLDER_ID"))
