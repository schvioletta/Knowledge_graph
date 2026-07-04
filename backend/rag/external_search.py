"""Внешний поиск источников: научные публикации (Google Scholar) и патенты
(Google Patents) по ключевым словам, извлечённым из запроса, найденных фрагментов
и сущностей графа знаний.

Дополняет внутреннюю RAG-базу актуальными внешними ссылками, НО никогда её не
подменяет и не ломает: любой сбой сети/провайдера/парсинга ловится и превращается
в пустой результат (+ сообщение), а не в исключение наружу — ответ по внутренней
базе формируется независимо от того, нашлось ли что-то снаружи.

Провайдеры (выбор автоматический):
  • SerpAPI (если задан SERPAPI_KEY) — надёжный платный шлюз к Scholar/Patents;
  • иначе бесплатно и без ключа: Google Patents через неофициальный XHR-JSON
    (patents.google.com/xhr/query — стабилен) и Google Scholar через парсинг HTML
    (нестабилен: Google периодически отдаёт CAPTCHA при частых запросах — тогда
    просто вернётся пусто, что штатно обрабатывается как «не найдено»).

Оба источника ищутся параллельно с общим таймаутом, чтобы не задерживать ответ.
"""
from __future__ import annotations

import concurrent.futures
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import requests

from backend.lexicon import STOPWORDS

# Типы сущностей графа, из которых имеет смысл строить внешние поисковые запросы
# (организации, технологии, материалы, продукты, процессы, авторы и т.п.).
_KEYWORD_TYPES = {
    "material", "process", "equipment", "facility", "team", "expert", "topic", "conclusion",
}

_ENABLED = os.getenv("EXTERNAL_SEARCH_ENABLED", "true").lower() not in ("0", "false", "no")
_TIMEOUT = float(os.getenv("EXTERNAL_SEARCH_TIMEOUT", "12"))
_MAX_PER_SOURCE = int(os.getenv("EXTERNAL_SEARCH_MAX", "5"))
_SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_NOT_FOUND_MESSAGE = "По данным ключевым словам релевантные публикации и патенты не найдены"


@dataclass
class ExternalSource:
    kind: str                    # "scholar" | "patent"
    title: str
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""              # журнал/конференция ИЛИ номер патента
    snippet: str = ""
    url: str = ""
    matched_keywords: list[str] = field(default_factory=list)
    relevance: float = 0.0       # 0..1


# ---------------- извлечение ключевых слов ----------------

def extract_search_keywords(
    question: str, entities: list[dict[str, Any]], top_n: int = 6
) -> list[str]:
    """Ключевые термины для внешнего поиска: сначала сущности графа подходящих
    типов (материалы/процессы/оборудование/организации/авторы...), отсортированные
    по числу упоминаний и связности, затем — при нехватке — содержательные слова
    из самого вопроса. Слишком длинные фразы (>45 симв.) отбрасываем — из них
    получаются плохие поисковые запросы."""
    seen: set[str] = set()
    keywords: list[str] = []

    ranked = sorted(
        (e for e in entities if e.get("type") in _KEYWORD_TYPES),
        key=lambda e: (e.get("mentions", 0), e.get("degree", 0), -len(e.get("name", ""))),
        reverse=True,
    )
    for e in ranked:
        name = (e.get("name") or "").strip()
        key = name.lower()
        if 3 <= len(name) <= 45 and key not in seen:
            seen.add(key)
            keywords.append(name)
        if len(keywords) >= top_n:
            return keywords

    # Добор из слов вопроса, если сущностей не хватило.
    for w in re.findall(r"[А-Яа-яЁёA-Za-z\-]{4,}", question):
        key = w.lower()
        if key in STOPWORDS or key in seen:
            continue
        seen.add(key)
        keywords.append(w)
        if len(keywords) >= top_n:
            break
    return keywords


def _relevance(keywords: list[str], title: str, snippet: str, rank: int, total: int) -> tuple[float, list[str]]:
    text = f"{title} {snippet}".lower()
    matched = [k for k in keywords if k.lower() in text]
    kw_frac = len(matched) / max(1, len(keywords))
    rank_score = 1.0 - (rank / max(1, total))
    return round(0.6 * kw_frac + 0.4 * rank_score, 2), matched


# ---------------- провайдеры: бесплатно, без ключа ----------------

def _search_patents_free(query: str, keywords: list[str], limit: int) -> list[ExternalSource]:
    # Неофициальный XHR-эндпоинт Google Patents отдаёт JSON без ключа/капчи.
    url = "https://patents.google.com/xhr/query"
    params = {"url": f"q={requests.utils.quote(query)}", "exp": ""}
    resp = requests.get(url, params=params, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    resp.raise_for_status()
    clusters = resp.json().get("results", {}).get("cluster", [])
    rows = clusters[0].get("result", []) if clusters else []

    out: list[ExternalSource] = []
    for i, row in enumerate(rows[:limit]):
        p = row.get("patent", {})
        title = _strip_tags(p.get("title", ""))
        snippet = _strip_tags(p.get("snippet", ""))
        number = p.get("publication_number", "")
        date = p.get("publication_date") or p.get("priority_date") or p.get("filing_date") or ""
        year = _year(date)
        inventor = p.get("inventor", "")
        authors = [a.strip() for a in re.split(r",|;", inventor) if a.strip()] if inventor else []
        rel, matched = _relevance(keywords, title, snippet, i, len(rows[:limit]))
        out.append(ExternalSource(
            kind="patent", title=title, authors=authors, year=year,
            venue=number, snippet=snippet,
            url=f"https://patents.google.com/patent/{number}/en" if number else "",
            matched_keywords=matched, relevance=rel,
        ))
    return out


def _search_scholar_free(query: str, keywords: list[str], limit: int) -> list[ExternalSource]:
    from bs4 import BeautifulSoup

    resp = requests.get(
        "https://scholar.google.com/scholar",
        params={"q": query, "hl": "ru"},
        headers={"User-Agent": _UA},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    if "gs_ri" not in resp.text:  # капча/блокировка/пусто — штатно возвращаем ничего
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[ExternalSource] = []
    blocks = soup.select("div.gs_ri")
    for i, b in enumerate(blocks[:limit]):
        title_el = b.select_one(".gs_rt a") or b.select_one(".gs_rt")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        link = title_el.get("href", "") if title_el and title_el.name == "a" else ""
        meta = b.select_one(".gs_a")
        meta_text = meta.get_text(" ", strip=True) if meta else ""
        snippet = b.select_one(".gs_rs")
        snippet_text = snippet.get_text(" ", strip=True) if snippet else ""
        authors, venue, year = _parse_scholar_meta(meta_text)
        rel, matched = _relevance(keywords, title, snippet_text, i, len(blocks[:limit]))
        out.append(ExternalSource(
            kind="scholar", title=title, authors=authors, year=year,
            venue=venue, snippet=snippet_text, url=link,
            matched_keywords=matched, relevance=rel,
        ))
    return out


# ---------------- провайдер: SerpAPI (если задан ключ) ----------------

def _serpapi(engine: str, query: str, keywords: list[str], limit: int, kind: str) -> list[ExternalSource]:
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={"engine": engine, "q": query, "api_key": _SERPAPI_KEY, "hl": "ru", "num": limit},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("organic_results") or data.get("results") or []
    out: list[ExternalSource] = []
    for i, r in enumerate(results[:limit]):
        title = r.get("title", "")
        snippet = r.get("snippet", "") or r.get("description", "")
        info = r.get("publication_info", {}) or {}
        authors = [a.get("name", "") for a in info.get("authors", [])] if info.get("authors") else []
        summary = info.get("summary", "")
        year = _year(summary) or _year(r.get("priority_date", "")) or _year(r.get("filing_date", ""))
        venue = r.get("patent_id") or r.get("publication_number") or summary
        rel, matched = _relevance(keywords, title, snippet, i, len(results[:limit]))
        out.append(ExternalSource(
            kind=kind, title=title, authors=[a for a in authors if a], year=year,
            venue=venue, snippet=snippet, url=r.get("link", "") or r.get("patent_link", ""),
            matched_keywords=matched, relevance=rel,
        ))
    return out


# ---------------- оркестратор ----------------

def search_external(question: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    """Возвращает {enabled, keywords, query, scholar, patents, provider, message, errors}.
    Никогда не бросает исключений — при любой ошибке источник просто пустой."""
    if not _ENABLED:
        return {"enabled": False, "keywords": [], "query": "", "scholar": [], "patents": [],
                "provider": None, "message": None, "errors": {}}

    keywords = extract_search_keywords(question, entities)
    if not keywords:
        return {"enabled": True, "keywords": [], "query": "", "scholar": [], "patents": [],
                "provider": None, "message": _NOT_FOUND_MESSAGE, "errors": {}}

    # Запрос — из нескольких самых сильных ключевых слов (комбинация терминов
    # даёт релевантнее, чем полный текст вопроса).
    query = " ".join(keywords[:3])
    use_serp = bool(_SERPAPI_KEY)
    provider = "serpapi" if use_serp else "free"

    def run_scholar() -> list[ExternalSource]:
        return _serpapi("google_scholar", query, keywords, _MAX_PER_SOURCE, "scholar") if use_serp \
            else _search_scholar_free(query, keywords, _MAX_PER_SOURCE)

    def run_patents() -> list[ExternalSource]:
        return _serpapi("google_patents", query, keywords, _MAX_PER_SOURCE, "patent") if use_serp \
            else _search_patents_free(query, keywords, _MAX_PER_SOURCE)

    scholar: list[ExternalSource] = []
    patents: list[ExternalSource] = []
    errors: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = {"scholar": ex.submit(run_scholar), "patents": ex.submit(run_patents)}
        for name, fut in futs.items():
            try:
                res = fut.result(timeout=_TIMEOUT + 2)
                if name == "scholar":
                    scholar = res
                else:
                    patents = res
            except Exception as e:  # сеть/капча/парсинг — источник просто пустой
                errors[name] = f"{type(e).__name__}: {e}"

    message = None if (scholar or patents) else _NOT_FOUND_MESSAGE
    return {
        "enabled": True, "keywords": keywords, "query": query,
        "scholar": [asdict(s) for s in scholar],
        "patents": [asdict(p) for p in patents],
        "provider": provider, "message": message, "errors": errors,
    }


# ---------------- утилиты парсинга ----------------

def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _year(text: str) -> Optional[int]:
    m = re.search(r"(19|20)\d{2}", text or "")
    return int(m.group(0)) if m else None


def _parse_scholar_meta(meta: str) -> tuple[list[str], str, Optional[int]]:
    # Формат gs_a: "Авторы - журнал, год - издатель". Разбираем грубо, но устойчиво.
    year = _year(meta)
    parts = [p.strip() for p in meta.split(" - ")]
    authors_raw = parts[0] if parts else ""
    authors = [a.strip() for a in re.split(r",|;", authors_raw) if a.strip() and "…" not in a]
    venue = ""
    if len(parts) > 1:
        venue = re.sub(r",?\s*(19|20)\d{2}.*$", "", parts[1]).strip()
    return authors, venue, year
