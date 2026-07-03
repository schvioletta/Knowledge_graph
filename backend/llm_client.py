"""Клиент для вызова YandexGPT в экстракторе сущностей и в RAG-чате.

Единая точка входа — `complete()`. Ключ и folder ID берутся из переменных
окружения YANDEX_API_KEY/YANDEX_FOLDER_ID (не хранятся в коде — иначе секрет
попадёт в git; см. .env.example — .env подхватывается load_dotenv() в
backend/main.py). YANDEX_MODEL по умолчанию "yandexgpt-5-pro".

Если бэкенд не сконфигурирован или вызов упал, `complete()` возвращает None —
вызывающий код должен уметь работать без LLM (детерминированный fallback).
`get_last_error()` хранит причину последнего провала — не для управления
потоком, а чтобы вызывающий код (например, RAG-ответ) мог явно показать
пользователю, ПОЧЕМУ он получил fallback: ключ не задан — это не то же самое,
что ключ задан, но API вернул ошибку.
"""
from __future__ import annotations

import os
from typing import Optional

_last_error: Optional[str] = None


def _complete_yandexgpt(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    import openai

    folder_id = os.environ["YANDEX_FOLDER_ID"]
    api_key = os.environ["YANDEX_API_KEY"]
    model = os.getenv("YANDEX_MODEL", "yandexgpt-5-pro")

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://ai.api.cloud.yandex.net/v1",
    )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # chat.completions, а не более новый responses — это классический
    # OpenAI-совместимый эндпоинт, который реально поддерживают сторонние
    # шлюзы вроде Yandex Cloud; responses.create() существует в openai-python
    # SDK, но шлюз может не реализовывать сам эндпоинт /v1/responses, и вызов
    # тихо падал в общий except ниже, маскируясь под «LLM недоступен».
    response = client.chat.completions.create(
        model=f"gpt://{folder_id}/{model}",
        messages=messages,
        temperature=temperature,
        max_tokens=2000,
    )
    return response.choices[0].message.content


def complete(prompt: str, system: Optional[str] = None, temperature: float = 0.0) -> Optional[str]:
    """Единая точка вызова LLM. Возвращает None, если нет доступного бэкенда
    или произошла ошибка (вызывающий код должен деградировать gracefully).
    Причина — в get_last_error()."""
    global _last_error
    if not is_configured():
        _last_error = "не сконфигурирован (нет YANDEX_API_KEY/YANDEX_FOLDER_ID)"
        return None
    try:
        result = _complete_yandexgpt(prompt, system, temperature)
        _last_error = None
        return result
    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        print(f"[llm_client] Ошибка вызова LLM: {_last_error}")
        return None


def is_configured() -> bool:
    return bool(os.getenv("YANDEX_API_KEY") and os.getenv("YANDEX_FOLDER_ID"))


def get_last_error() -> Optional[str]:
    """Причина последнего провала complete() — None, если последний вызов
    прошёл успешно или вызовов ещё не было."""
    return _last_error
