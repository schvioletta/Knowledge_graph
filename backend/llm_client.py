"""Клиент для вызова LLM в экстракторе сущностей, извлечении метаданных и RAG-чате.

Бэкенд выбирается через LLM_BACKEND=yandex|gigachat (по умолчанию gigachat).
INDEX_USE_YANDEX=1 (или CLI index_corpus --yandex) временно переключает на Yandex.

Модель на каждый запрос берётся из env:
  - gigachat → GIGACHAT_MODEL (по умолчанию "GigaChat")
  - yandex   → YANDEX_MODEL (по умолчанию "yandexgpt-5-pro")

Единая точка входа — `complete()` / `complete_stream()`. Если бэкенд не
сконфигурирован или вызов упал, возвращается None — вызывающий код должен
уметь работать без LLM (детерминированный fallback).

verify_ssl_certs=False для GigaChat: сертификаты подписаны корневым УЦ Минцифры,
которого нет в стандартном trust store.

Ответы LLM кэшируются в памяти (LRU, LLM_CACHE_SIZE).
"""
from __future__ import annotations

import os
from typing import Iterator, Optional

from backend.llm_cache import get as cache_get
from backend.llm_cache import make_key as cache_make_key
from backend.llm_cache import put as cache_put

_CACHE_NS_GIGACHAT = "gigachat"
_CACHE_NS_YANDEX = "yandex"
_last_error: Optional[str] = None
_client = None  # ленивый singleton GigaChat
_yandex_client = None


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def index_use_yandex() -> bool:
    """INDEX_USE_YANDEX=1 — YandexGPT для index_corpus и связанных LLM-вызовов."""
    return _env_truthy("INDEX_USE_YANDEX")


def llm_backend() -> str:
    """Активный бэкенд: yandex или gigachat."""
    explicit = os.getenv("LLM_BACKEND", "").strip().lower()
    if explicit in ("yandex", "gigachat"):
        return explicit
    if index_use_yandex():
        return "yandex"
    return "gigachat"


def _gigachat_model() -> str:
    return os.getenv("GIGACHAT_MODEL", "GigaChat")


def _yandex_model() -> str:
    return os.getenv("YANDEX_MODEL", "aliceai-llm-flash")


def is_yandex_configured() -> bool:
    return bool(os.getenv("YANDEX_API_KEY") and os.getenv("YANDEX_FOLDER_ID"))


def is_gigachat_configured() -> bool:
    return bool(os.getenv("GIGACHAT_API_KEY"))


def is_configured() -> bool:
    if llm_backend() == "yandex":
        return is_yandex_configured()
    return is_gigachat_configured()


def is_index_llm_configured() -> bool:
    return is_configured()


def _get_client():
    """Ленивая инициализация клиента GigaChat (один OAuth-токен на процесс)."""
    global _client
    if _client is None:
        from gigachat import GigaChatSyncClient

        _client = GigaChatSyncClient(
            credentials=os.environ["GIGACHAT_API_KEY"],
            scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
            verify_ssl_certs=False,
        )
    return _client


def _cache_key(prompt: str, system: Optional[str], temperature: float) -> str:
    backend = llm_backend()
    if backend == "yandex":
        return cache_make_key(
            backend,
            _yandex_model(),
            os.getenv("YANDEX_FOLDER_ID", ""),
            str(temperature),
            system or "",
            prompt,
        )
    temp = max(temperature, 1e-6)
    return cache_make_key(
        backend,
        _gigachat_model(),
        os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        str(temp),
        system or "",
        prompt,
    )


def _cache_ns() -> str:
    return _CACHE_NS_YANDEX if llm_backend() == "yandex" else _CACHE_NS_GIGACHAT


def _build_payload(prompt: str, system: Optional[str], temperature: float):
    from gigachat.models import Chat, Messages, MessagesRole

    messages = []
    if system:
        messages.append(Messages(role=MessagesRole.SYSTEM, content=system))
    messages.append(Messages(role=MessagesRole.USER, content=prompt))

    return Chat(
        model=_gigachat_model(),
        messages=messages,
        temperature=max(temperature, 1e-6),
    )


def _complete_gigachat(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    response = _get_client().chat(_build_payload(prompt, system, temperature))
    return response.choices[0].message.content


def _get_yandex_client():
    global _yandex_client
    if _yandex_client is None:
        from openai import OpenAI

        _yandex_client = OpenAI(
            api_key=os.environ["YANDEX_API_KEY"],
            base_url="https://llm.api.cloud.yandex.net/v1",
            default_headers={"x-folder-id": os.environ["YANDEX_FOLDER_ID"]},
        )
    return _yandex_client


def _yandex_model_uri() -> str:
    return f"gpt://{os.environ['YANDEX_FOLDER_ID']}/{_yandex_model()}"


def _yandex_messages(prompt: str, system: Optional[str]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _complete_yandex(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    response = _get_yandex_client().chat.completions.create(
        model=_yandex_model_uri(),
        messages=_yandex_messages(prompt, system),
        temperature=temperature,
        max_tokens=2000,
    )
    return response.choices[0].message.content


def _complete_active(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    if llm_backend() == "yandex":
        return _complete_yandex(prompt, system, temperature)
    return _complete_gigachat(prompt, system, temperature)


def _stream_active(
    prompt: str, system: Optional[str], temperature: float
) -> Iterator[str]:
    if llm_backend() == "yandex":
        stream = _get_yandex_client().chat.completions.create(
            model=_yandex_model_uri(),
            messages=_yandex_messages(prompt, system),
            temperature=temperature,
            max_tokens=2000,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
        return

    for chunk in _get_client().stream(_build_payload(prompt, system, temperature)):
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def complete_stream(
    prompt: str, system: Optional[str] = None, temperature: float = 0.0
) -> Iterator[str]:
    """Потоковая генерация через активный бэкенд (GigaChat или YandexGPT)."""
    global _last_error
    if not is_configured():
        backend = llm_backend()
        if backend == "yandex":
            _last_error = "не сконфигурирован (нет YANDEX_API_KEY/YANDEX_FOLDER_ID)"
        else:
            _last_error = "не сконфигурирован (нет GIGACHAT_API_KEY)"
        return

    key = _cache_key(prompt, system, temperature)
    cached = cache_get(_cache_ns(), key)
    if cached is not None:
        _last_error = None
        yield cached
        return

    try:
        parts: list[str] = []
        for delta in _stream_active(prompt, system, temperature):
            parts.append(delta)
            yield delta
        if parts:
            cache_put(_cache_ns(), key, "".join(parts))
        _last_error = None
    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        print(f"[llm_client] Ошибка потокового вызова LLM ({llm_backend()}): {_last_error}")


def complete(prompt: str, system: Optional[str] = None, temperature: float = 0.0) -> Optional[str]:
    """Единая точка вызова LLM через активный бэкенд и модель из env."""
    global _last_error
    if not is_configured():
        backend = llm_backend()
        if backend == "yandex":
            _last_error = "не сконфигурирован (нет YANDEX_API_KEY/YANDEX_FOLDER_ID)"
        else:
            _last_error = "не сконфигурирован (нет GIGACHAT_API_KEY)"
        return None

    key = _cache_key(prompt, system, temperature)
    cached = cache_get(_cache_ns(), key)
    if cached is not None:
        _last_error = None
        return cached

    try:
        result = _complete_active(prompt, system, temperature)
        if result is not None:
            cache_put(_cache_ns(), key, result)
        _last_error = None
        return result
    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        print(f"[llm_client] Ошибка вызова LLM ({llm_backend()}, {_active_model()}): {_last_error}")
        return None


def _active_model() -> str:
    return _yandex_model() if llm_backend() == "yandex" else _gigachat_model()


def active_model() -> str:
    """Имя модели активного облачного бэкенда (YANDEX_MODEL или GIGACHAT_MODEL)."""
    return _active_model()


def format_llm_startup_message() -> str:
    """Строка для лога при старте процесса: бэкенд, модель, готовность."""
    backend = llm_backend()
    model = _active_model()
    if is_configured():
        status = "готов"
    elif backend == "yandex":
        status = "не настроен (нет YANDEX_API_KEY/YANDEX_FOLDER_ID)"
    else:
        status = "не настроен (нет GIGACHAT_API_KEY)"

    lines = [f"[llm] облако: {backend} / {model} — {status}"]
    qm = os.getenv("QUERY_EXPAND_MODEL", "").strip()
    if qm:
        lines.append(f"[llm] query expand fallback: ollama / {qm}")
    return "\n".join(lines)


def log_llm_startup() -> None:
    print(format_llm_startup_message(), flush=True)


def complete_yandex(
    prompt: str, system: Optional[str] = None, temperature: float = 0.0
) -> Optional[str]:
    """YandexGPT напрямую (без учёта LLM_BACKEND)."""
    global _last_error
    if not is_yandex_configured():
        _last_error = "не сконфигурирован (нет YANDEX_API_KEY/YANDEX_FOLDER_ID)"
        return None

    key = cache_make_key(
        "yandex-direct",
        _yandex_model(),
        os.getenv("YANDEX_FOLDER_ID", ""),
        str(temperature),
        system or "",
        prompt,
    )
    cached = cache_get(_CACHE_NS_YANDEX, key)
    if cached is not None:
        _last_error = None
        return cached

    try:
        result = _complete_yandex(prompt, system, temperature)
        if result is not None:
            cache_put(_CACHE_NS_YANDEX, key, result)
        _last_error = None
        return result
    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        print(f"[llm_client] Ошибка вызова YandexGPT ({_yandex_model()}): {_last_error}")
        return None


def complete_for_index(
    prompt: str, system: Optional[str] = None, temperature: float = 0.0
) -> Optional[str]:
    """Алиас complete() — бэкенд определяется INDEX_USE_YANDEX / LLM_BACKEND."""
    return complete(prompt, system, temperature)


def get_last_error() -> Optional[str]:
    """Причина последнего провала complete() — None, если последний вызов
    прошёл успешно или вызовов ещё не было."""
    return _last_error
