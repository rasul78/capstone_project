"""
Sentinel AI — Web Agent
Выполняет живой поиск через MCP (Brave Search / DuckDuckGo fallback).
Используется когда ResearchAgent не нашёл релевантного контента.
"""

import time
import logging
import os
import httpx
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("sentinel.web_agent")

# MCP / Brave Search API config
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# DuckDuckGo (бесплатный fallback)
DDG_URL = "https://api.duckduckgo.com/"


@dataclass
class WebResult:
    found: bool
    results: List[Dict]          # [{title, url, snippet}]
    source: str                  # "brave" | "duckduckgo" | "none"
    latency_ms: float
    agent: str = "WebAgent"
    error: Optional[str] = None


class WebAgent:
    """
    Agent 2: Живой веб-поиск через MCP-совместимый интерфейс.
    Primary: Brave Search API (если BRAVE_API_KEY задан).
    Fallback: DuckDuckGo Instant Answer API (бесплатный).
    """

    def __init__(self, timeout: float = 5.0, max_results: int = 5):
        self.timeout = timeout
        self.max_results = max_results
        self.name = "WebAgent"
        self._use_brave = bool(BRAVE_API_KEY)
        logger.info(f"[{self.name}] initialized, backend={'brave' if self._use_brave else 'duckduckgo'}")

    async def run(self, query: str) -> WebResult:
        """Выполняет веб-поиск по запросу."""
        t0 = time.time()
        query = query.strip()[:300]

        if not query:
            return WebResult(found=False, results=[], source="none",
                             latency_ms=0, error="Empty query")

        logger.info(f"[{self.name}] Searching: {query!r}")

        try:
            if self._use_brave:
                result = await self._brave_search(query)
            else:
                result = await self._ddg_search(query)

            result.latency_ms = (time.time() - t0) * 1000
            logger.info(f"[{self.name}] {len(result.results)} results via {result.source}, "
                        f"latency={result.latency_ms:.0f}ms")
            return result

        except Exception as e:
            logger.error(f"[{self.name}] Search error: {e}")
            return WebResult(
                found=False, results=[], source="none",
                latency_ms=(time.time() - t0) * 1000, error=str(e)
            )

    async def _brave_search(self, query: str) -> WebResult:
        """Brave Search через MCP-совместимый REST API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": BRAVE_API_KEY,
                },
                params={"q": query, "count": self.max_results, "lang": "ru"},
            )
            resp.raise_for_status()
            data = resp.json()

        items = data.get("web", {}).get("results", [])
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
            }
            for r in items[: self.max_results]
        ]
        return WebResult(found=bool(results), results=results, source="brave",
                         latency_ms=0)

    async def _ddg_search(self, query: str) -> WebResult:
        """DuckDuckGo Instant Answer API (бесплатный, без ключа)."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                DDG_URL,
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                headers={"User-Agent": "SentinelAI/3.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []

        # Abstract (основной ответ)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "url": data.get("AbstractURL", ""),
                "snippet": data["AbstractText"],
            })

        # Related Topics
        for topic in data.get("RelatedTopics", [])[:self.max_results - len(results)]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                })

        # Answer box
        if data.get("Answer") and not results:
            results.append({
                "title": "Прямой ответ",
                "url": "",
                "snippet": data["Answer"],
            })

        return WebResult(found=bool(results), results=results, source="duckduckgo",
                         latency_ms=0)