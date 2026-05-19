"""
Sentinel AI / hr MCP — HTTP Bridge

Мост к публичным источникам данных по МРП/МЗП РК.

Стратегия:
  1. Real:  попытка скачать страницу 1cbit.kz / mybuh.kz / pro1c.kz
            (стабильные источники, регулярно обновляются)
  2. Mock:  встроенный справочник за 2020-2026

Возвращает (value, source) где source ∈ {'live_fetch', 'mock_fallback'}.
"""
from __future__ import annotations

import re
import logging
import asyncio
from typing import Optional, Tuple, Dict

import httpx

from . import mock_data

logger = logging.getLogger("mcp.hr.bridge")

DEFAULT_HEADERS = {
    "User-Agent": "SentinelAI-MCP/1.0 (+capstone)",
    "Accept":     "text/html,application/xhtml+xml",
    "Accept-Language": "ru,en;q=0.8",
}

# Источники где регулярно публикуют свежие МРП/МЗП
_LIVE_SOURCES = [
    "https://mybuh.kz/news/mrp-v-kazakhstane/",
    "https://www.bcc.kz/bcc-journal/mpr-mzp/",
]


async def fetch_current_mrp_mzp(timeout: float = 5.0) -> Tuple[Optional[Dict], str]:
    """
    Пытается получить актуальные МРП и МЗП из живого источника.
    Возвращает ({mrp, mzp, year}, source) или (None, error).
    """
    for url in _LIVE_SOURCES:
        try:
            result = await asyncio.wait_for(_fetch_one(url), timeout=timeout)
            if result:
                return result, "live_fetch"
        except asyncio.TimeoutError:
            logger.warning(f"hr.bridge timeout: {url}")
        except Exception as e:
            logger.warning(f"hr.bridge error on {url}: {e}")
    return None, "no_live_data"


async def _fetch_one(url: str) -> Optional[Dict]:
    async with httpx.AsyncClient(timeout=5.0, headers=DEFAULT_HEADERS,
                                 follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        html = r.text

    # Простой regex-парсер: ищем паттерны вида
    #   "МРП ... 4 325 тенге"
    #   "МЗП ... 85 000 тенге"
    mrp = _extract_value(html, r"МРП[^0-9]{0,40}([0-9][0-9\s]{2,8})\s*тенге")
    mzp = _extract_value(html, r"МЗП[^0-9]{0,40}([0-9][0-9\s]{2,8})\s*тенге")
    year = _extract_year(html)
    if not (mrp and mzp):
        return None
    return {"mrp": mrp, "mzp": mzp, "year": year, "url": url}


def _extract_value(html: str, pattern: str) -> Optional[int]:
    m = re.search(pattern, html, flags=re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace("\xa0", "")
    try:
        v = int(raw)
        # Sanity: МРП — 1000-10000, МЗП — 30000-200000
        if 1000 <= v <= 200_000:
            return v
    except ValueError:
        pass
    return None


def _extract_year(html: str) -> Optional[int]:
    m = re.search(r"\b(20\d{2})\s+год", html)
    return int(m.group(1)) if m else None