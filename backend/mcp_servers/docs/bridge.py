"""
Sentinel AI / docs MCP — HTTP Bridge

Мост к собственному Sentinel AI backend (FastAPI на :8000).
Это интересный inversion: тот же backend, который оркестрирует чат,
выставляется наружу через MCP — становясь поставщиком знаний для
других AI-агентов (Claude Desktop, внешние LangGraph apps).

Endpoints Sentinel AI которые мы оборачиваем:
  GET  /api/kb/documents              → list_documents
  GET  /api/kb/documents/{id}         → get_document
  POST /api/kb/chat/debug             → search_documents
  GET  /api/kb/stats                  → get_kb_stats
"""
from __future__ import annotations

import os
import logging
import asyncio
from typing import Optional, Tuple, Dict, List, Any

import httpx

logger = logging.getLogger("mcp.docs.bridge")

SENTINEL_BASE = os.getenv("SENTINEL_BASE_URL", "http://localhost:8000")
TIMEOUT = httpx.Timeout(10.0, connect=3.0)

DEFAULT_HEADERS = {
    "User-Agent": "SentinelAI-MCP-Docs/1.0",
    "Accept":     "application/json",
}


async def search_documents(query: str, top_k: int = 5
                           ) -> Tuple[Optional[Dict], str]:
    """Поиск по корпоративной базе знаний через debug endpoint."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT,
                                     headers=DEFAULT_HEADERS) as client:
            r = await client.get(
                f"{SENTINEL_BASE}/api/kb/chat/debug",
                params={"q": query, "top_k": top_k},
            )
            r.raise_for_status()
            return r.json(), "sentinel_backend"
    except httpx.HTTPStatusError as e:
        logger.warning(f"search_documents HTTP {e.response.status_code}")
        return None, f"http_{e.response.status_code}"
    except Exception as e:
        logger.warning(f"search_documents error: {e}")
        return None, "connection_error"


async def list_documents() -> Tuple[Optional[List[Dict]], str]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT,
                                     headers=DEFAULT_HEADERS) as client:
            r = await client.get(f"{SENTINEL_BASE}/api/kb/documents")
            r.raise_for_status()
            data = r.json()
            docs = data if isinstance(data, list) else data.get("documents", [])
            return docs, "sentinel_backend"
    except Exception as e:
        logger.warning(f"list_documents error: {e}")
        return None, "connection_error"


async def get_document(doc_id: int) -> Tuple[Optional[Dict], str]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT,
                                     headers=DEFAULT_HEADERS) as client:
            r = await client.get(f"{SENTINEL_BASE}/api/kb/documents/{doc_id}")
            r.raise_for_status()
            return r.json(), "sentinel_backend"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None, "not_found"
        return None, f"http_{e.response.status_code}"
    except Exception as e:
        logger.warning(f"get_document error: {e}")
        return None, "connection_error"


async def get_kb_stats() -> Tuple[Optional[Dict], str]:
    """Статистика базы знаний: сколько документов, чанков, по категориям."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT,
                                     headers=DEFAULT_HEADERS) as client:
            r = await client.get(f"{SENTINEL_BASE}/api/kb/stats")
            r.raise_for_status()
            return r.json(), "sentinel_backend"
    except Exception as e:
        logger.warning(f"get_kb_stats error: {e}")
        # Fallback: посчитаем сами через list_documents
        docs, src = await list_documents()
        if docs is not None:
            categories = {}
            total_chunks = 0
            for d in docs:
                cat = d.get("category", "Общее")
                categories[cat] = categories.get(cat, 0) + 1
                total_chunks += d.get("chunk_count", 0)
            return {
                "total_documents": len(docs),
                "total_chunks":    total_chunks,
                "by_category":     categories,
                "fallback":        True,
            }, "computed_from_list"
        return None, "connection_error"


async def health_check() -> bool:
    """Проверяет доступность Sentinel AI backend."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            r = await client.get(f"{SENTINEL_BASE}/")
            return r.status_code == 200
    except Exception:
        return False