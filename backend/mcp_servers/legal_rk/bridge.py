"""
Sentinel AI / legal_rk MCP — HTTP Bridge

Мост к реальному источнику — adilet.zan.kz (информационно-правовая система РК).

ВАЖНО: у adilet.zan.kz нет публичного REST API, поэтому работаем через:
  1. DuckDuckGo с фильтром site:adilet.zan.kz → находим URL
  2. httpx GET страницы → парсим HTML через BeautifulSoup4 (если установлен)
                       → или через regex fallback (если нет)

Дизайн моста:
  • Гибридный режим: всегда сначала real HTTP, при ошибке → mock_data
  • Timeout жёсткий (5 секунд) — чтобы LangGraph не висел
  • Кэш на стороне MCP-сервера (см. server.py) — повторные запросы быстрее
"""
from __future__ import annotations

import re
import logging
import asyncio
from html import unescape
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlparse

import httpx

from . import mock_data

logger = logging.getLogger("mcp.legal_rk.bridge")

ADILET_BASE = "https://adilet.zan.kz"
DDG_HTML    = "https://html.duckduckgo.com/html/"
DEFAULT_HEADERS = {
    "User-Agent": "SentinelAI-MCP/1.0 (+capstone)",
    "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "ru,en;q=0.8",
}

# ── Optional BeautifulSoup (graceful fallback) ────────────────────
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logger.warning("BeautifulSoup4 не установлен, парсинг через regex (хуже). "
                   "Установи: pip install beautifulsoup4")


# ══════════════════════════════════════════════════════════════════
# Public API of the bridge
# ══════════════════════════════════════════════════════════════════

async def search_law(query: str, limit: int = 5, timeout: float = 5.0
                     ) -> Tuple[List[Dict], str]:
    """
    Возвращает (results, source) где source ∈ {'adilet_search', 'mock_fallback'}.
    """
    if not query.strip():
        return [], "empty_query"

    # 1) Real: DuckDuckGo с site:adilet.zan.kz
    try:
        results = await asyncio.wait_for(
            _ddg_site_search(query, limit=limit), timeout=timeout
        )
        if results:
            return results, "adilet_search"
    except asyncio.TimeoutError:
        logger.warning(f"search_law timeout: {query!r}")
    except Exception as e:
        logger.warning(f"search_law error: {e}")

    # 2) Fallback: mock data (in-memory)
    mock = mock_data.search_articles(query, limit=limit)
    if mock:
        return mock, "mock_fallback"

    return [], "no_results"


async def get_article(code: str, article_number: str, timeout: float = 5.0
                      ) -> Tuple[Optional[Dict], str]:
    """
    Возвращает (article_dict | None, source).
    Пробует найти конкретную статью на adilet.zan.kz; при неудаче → mock.
    """
    # 1) Mock сразу (быстро) если знаем
    cached = mock_data.get_article(code, article_number)

    # 2) Real — попытка обогатить из adilet через поиск
    try:
        query = f"{code} статья {article_number}"
        results, _ = await search_law(query, limit=3, timeout=timeout)
        for r in results:
            if r.get("source") == "adilet_search" and str(article_number) in (r.get("snippet") or ""):
                # Нашли в реальном поиске — возвращаем его (mock как backup)
                real = {
                    "code":           mock_data.normalize_code(code) or code,
                    "article_number": str(article_number),
                    "title":          r.get("title", ""),
                    "text":           r.get("snippet", ""),
                    "url":            r.get("url", ""),
                    "source":         "adilet_search",
                }
                return real, "adilet_search"
    except Exception as e:
        logger.warning(f"get_article live lookup failed: {e}")

    if cached:
        return cached, "mock_fallback"
    return None, "not_found"


async def fetch_page(url: str, timeout: float = 5.0) -> Tuple[Optional[str], str]:
    """
    Скачивает страницу с adilet.zan.kz и извлекает основной текст.
    Возвращает (text | None, source).
    """
    if not url.startswith(ADILET_BASE):
        return None, "wrong_host"

    try:
        async with httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS,
                                     follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            text = _extract_main_text(r.text)
            return text, "adilet_fetch"
    except Exception as e:
        logger.warning(f"fetch_page error: {e}")
        return None, "fetch_error"


# ══════════════════════════════════════════════════════════════════
# Internals
# ══════════════════════════════════════════════════════════════════

async def _ddg_site_search(query: str, limit: int = 5) -> List[Dict]:
    """DuckDuckGo HTML scraping с фильтром site:adilet.zan.kz."""
    q = f"site:adilet.zan.kz {query}"
    async with httpx.AsyncClient(timeout=5.0, headers=DEFAULT_HEADERS,
                                 follow_redirects=True) as client:
        r = await client.post(DDG_HTML, data={"q": q, "kl": "ru-ru"})
        r.raise_for_status()
        html = r.text

    return _parse_ddg_results(html, limit=limit)


def _parse_ddg_results(html: str, limit: int) -> List[Dict]:
    """Парсит результаты DuckDuckGo. Использует BS4 если есть, иначе regex."""
    results: List[Dict] = []

    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for block in soup.select(".result")[: limit * 2]:
            a = block.select_one("a.result__a")
            snippet_el = block.select_one(".result__snippet")
            if not a:
                continue
            url = a.get("href", "")
            # DDG оборачивает ссылку в /l/?uddg=...
            url = _unwrap_ddg(url)
            if "adilet.zan.kz" not in url:
                continue
            results.append({
                "title":   a.get_text(strip=True),
                "url":     url,
                "snippet": snippet_el.get_text(" ", strip=True) if snippet_el else "",
                "source":  "adilet_search",
            })
            if len(results) >= limit:
                break
        return results

    # ── regex fallback ──
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL
    )
    for m in pattern.finditer(html):
        url = _unwrap_ddg(m.group(1))
        if "adilet.zan.kz" not in url:
            continue
        title   = _strip_tags(m.group(2))
        snippet = _strip_tags(m.group(3))
        results.append({
            "title": title, "url": url, "snippet": snippet,
            "source": "adilet_search",
        })
        if len(results) >= limit:
            break
    return results


def _unwrap_ddg(url: str) -> str:
    """DDG обворачивает ссылки. Достаём оригинальный URL."""
    if url.startswith("//duckduckgo.com/l/") or "uddg=" in url:
        m = re.search(r"uddg=([^&]+)", url)
        if m:
            from urllib.parse import unquote
            return unquote(m.group(1))
    return url


def _strip_tags(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _extract_main_text(html: str, max_chars: int = 4000) -> str:
    """Извлекает основной текст из HTML adilet.zan.kz."""
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        # Удаляем шум
        for sel in ["script", "style", "nav", "header", "footer", "aside"]:
            for tag in soup.select(sel):
                tag.decompose()
        # Основной контент часто в #docContent или .doc-content
        main = soup.select_one("#docContent") or soup.select_one(".doc-content") or soup.body
        if main:
            text = main.get_text("\n", strip=True)
        else:
            text = soup.get_text("\n", strip=True)
    else:
        text = _strip_tags(html)

    # Нормализуем пробелы
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text[:max_chars].strip()