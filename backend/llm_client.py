"""Клиент для вызова LLM в экстракторе сущностей, извлечении метаданных и RAG-чате.

Основной бэкенд — GigaChat (Sber). Ключ берётся из переменной окружения
GIGACHAT_API_KEY (не хранится в коде — иначе секрет попадёт в git; .env
подхватывается load_dotenv() в backend/main.py и в CLI-скриптах). Модель —
GIGACHAT_MODEL (по умолчанию "GigaChat"), scope — GIGACHAT_SCOPE (по умолчанию
"GIGACHAT_API_PERS" для физлиц; для юрлиц — "GIGACHAT_API_CORP").

Единая точка входа — `complete()`. Если бэкенд не сконфигурирован или вызов
упал, `complete()` возвращает None — вызывающий код должен уметь работать без
LLM (детерминированный fallback). `get_last_error()` хранит причину последнего
провала — не для управления потоком, а чтобы вызывающий код (например, RAG-ответ)
мог явно показать пользователю, ПОЧЕМУ он получил fallback: ключ не задан — это
не то же самое, что ключ задан, но API вернул ошибку.

verify_ssl_certs=False: сертификаты GigaChat подписаны корневым УЦ Минцифры,
которого нет в стандартном trust store — без этого каждый вызов падал бы на
проверке SSL. Клиент кэшируется (лениво) между вызовами: получение OAuth-токена
по ключу — сетевой запрос, незачем делать его на каждый чанк.

Ответы LLM кэшируются в памяти (LRU, LLM_CACHE_SIZE): одинаковые prompt+system
не отправляются в GigaChat повторно — важно для NER по чанкам и повторных
RAG-вопросов.
"""
from __future__ import annotations

import os
from typing import Iterator, Optional

from backend.llm_cache import get as cache_get
from backend.llm_cache import make_key as cache_make_key
from backend.llm_cache import put as cache_put

_CACHE_NS = "gigachat"
_last_error: Optional[str] = None
_client = None  # ленивый singleton GigaChat


def _get_client():
    """Ленивая инициализация клиента GigaChat (один OAuth-токен на процесс)."""
    global _client
    if _client is None:
        from gigachat import GigaChatSyncClient

        _client = GigaChatSyncClient(
            credentials=os.environ["GIGACHAT_API_KEY"],
            scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
            model=os.getenv("GIGACHAT_MODEL", "GigaChat"),
            verify_ssl_certs=False,
        )
    return _client


def _cache_key(prompt: str, system: Optional[str], temperature: float) -> str:
    temp = max(temperature, 1e-6)
    return cache_make_key(
        os.getenv("GIGACHAT_MODEL", "GigaChat"),
        os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        str(temp),
        system or "",
        prompt,
    )


def _build_payload(prompt: str, system: Optional[str], temperature: float):
    from gigachat.models import Chat, Messages, MessagesRole

    messages = []
    if system:
        messages.append(Messages(role=MessagesRole.SYSTEM, content=system))
    messages.append(Messages(role=MessagesRole.USER, content=prompt))

    # GigaChat не принимает temperature=0 (диапазон > 0); 0 трактуем как
    # «максимально детерминированно» — минимально допустимое значение.
    return Chat(messages=messages, temperature=max(temperature, 1e-6))


def _complete_gigachat(prompt: str, system: Optional[str], temperature: float) -> Optional[str]:
    response = _get_client().chat(_build_payload(prompt, system, temperature))
    return response.choices[0].message.content


def complete_stream(
    prompt: str, system: Optional[str] = None, temperature: float = 0.0
) -> Iterator[str]:
    """Потоковая генерация: yield-ит дельты текста по мере ответа GigaChat.
    Если бэкенд не сконфигурирован или вызов упал — не бросает исключение
    наружу, а просто ничего не yield-ит и выставляет get_last_error()
    (вызывающий код проверяет, накопился ли текст, и деградирует так же,
    как при complete() == None)."""
    global _last_error
    if not is_configured():
        _last_error = "не сконфигурирован (нет GIGACHAT_API_KEY)"
        return

    key = _cache_key(prompt, system, temperature)
    cached = cache_get(_CACHE_NS, key)
    if cached is not None:
        _last_error = None
        yield cached
        return

    try:
        parts: list[str] = []
        for chunk in _get_client().stream(_build_payload(prompt, system, temperature)):
            delta = chunk.choices[0].delta.content
            if delta:
                parts.append(delta)
                yield delta
        if parts:
            cache_put(_CACHE_NS, key, "".join(parts))
        _last_error = None
    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        print(f"[llm_client] Ошибка потокового вызова LLM: {_last_error}")


def complete(prompt: str, system: Optional[str] = None, temperature: float = 0.0) -> Optional[str]:
    """Единая точка вызова LLM. Возвращает None, если нет доступного бэкенда
    или произошла ошибка (вызывающий код должен деградировать gracefully).
    Причина — в get_last_error()."""
    global _last_error
    if not is_configured():
        _last_error = "не сконфигурирован (нет GIGACHAT_API_KEY)"
        return None

    key = _cache_key(prompt, system, temperature)
    cached = cache_get(_CACHE_NS, key)
    if cached is not None:
        _last_error = None
        return cached

    try:
        result = _complete_gigachat(prompt, system, temperature)
        if result is not None:
            cache_put(_CACHE_NS, key, result)
        _last_error = None
        return result
    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        print(f"[llm_client] Ошибка вызова LLM: {_last_error}")
        return None


def is_configured() -> bool:
    return bool(os.getenv("GIGACHAT_API_KEY"))


def get_last_error() -> Optional[str]:
    """Причина последнего провала complete() — None, если последний вызов
    прошёл успешно или вызовов ещё не было."""
    return _last_error
