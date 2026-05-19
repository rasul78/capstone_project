"""
Sentinel AI / docs MCP Server

Custom MCP server that exposes Sentinel AI's internal corporate knowledge base
to external MCP clients (Claude Desktop, other LangGraph apps, custom AI agents).

This is the "inversion" pattern: same backend that orchestrates the chat is
ALSO exposed as MCP, making it composable in larger AI ecosystems.

Exposes 4 tools:
  • search_documents(query, top_k)  — RAG поиск по корпоративным документам
  • list_documents(category?)       — список всех документов
  • get_document(doc_id)            — получить полное содержимое документа
  • get_kb_stats()                  — статистика базы знаний

Configuration via env:
  SENTINEL_BASE_URL=http://localhost:8000   # где запущен Sentinel AI backend

Run modes:
  python -m mcp_servers.docs.server --transport stdio
  python -m mcp_servers.docs.server --transport http --port 8103
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Any

from mcp_servers import (
    MCPServer, ToolSchema, ToolResult,
    serve, make_arg_parser, setup_logging,
)
from . import bridge

logger = logging.getLogger("mcp.docs")

# Кэш с TTL 2 минуты (RAG-результаты могут меняться при добавлении документов)
_CACHE: Dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 120


def _cache_get(key: str):
    item = _CACHE.get(key)
    if item is None:
        return None
    ts, val = item
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return val


def _cache_set(key: str, val):
    _CACHE[key] = (time.time(), val)


class DocsMCPServer(MCPServer):
    """MCP-сервер выставляющий Sentinel AI knowledge base."""

    def __init__(self):
        super().__init__("sentinel-docs", "1.0.0")

    def register_tools(self) -> None:

        # ── Tool 1: search_documents ─────────────────────────────
        self.register_tool(
            ToolSchema(
                name="search_documents",
                description=(
                    "Поиск по корпоративной базе знаний Sentinel AI (RAG). "
                    "Использует hybrid search (semantic + keyword) + reranker. "
                    "Возвращает релевантные фрагменты документов с источниками "
                    "и оценкой релевантности. Используется AI-агентами для "
                    "ответов на вопросы о политиках компании, процедурах, регламентах."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Поисковый запрос (русский или английский)",
                            "minLength": 2, "maxLength": 500,
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Количество результатов (1-20)",
                            "default": 5, "minimum": 1, "maximum": 20,
                        },
                    },
                    "required": ["query"],
                },
            ),
            self._tool_search_documents,
        )

        # ── Tool 2: list_documents ───────────────────────────────
        self.register_tool(
            ToolSchema(
                name="list_documents",
                description=(
                    "Список всех документов в корпоративной базе знаний. "
                    "Опционально фильтр по категории "
                    "(HR, Безопасность, Финансы, IT, Этика, Общее)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Фильтр по категории (опционально)",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 50, "minimum": 1, "maximum": 200,
                        },
                    },
                    "required": [],
                },
            ),
            self._tool_list_documents,
        )

        # ── Tool 3: get_document ─────────────────────────────────
        self.register_tool(
            ToolSchema(
                name="get_document",
                description=(
                    "Получить полное содержимое конкретного документа по его ID. "
                    "Используется когда search_documents нашёл релевантный фрагмент, "
                    "но AI-агенту нужен полный контекст документа."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "doc_id": {
                            "type": "integer",
                            "description": "ID документа из results search_documents",
                            "minimum": 1,
                        },
                    },
                    "required": ["doc_id"],
                },
            ),
            self._tool_get_document,
        )

        # ── Tool 4: get_kb_stats ─────────────────────────────────
        self.register_tool(
            ToolSchema(
                name="get_kb_stats",
                description=(
                    "Статистика корпоративной базы знаний: общее количество "
                    "документов, фрагментов, распределение по категориям. "
                    "Полезно для агента чтобы понять покрытие знаний."
                ),
                input_schema={"type": "object", "properties": {}, "required": []},
            ),
            self._tool_get_kb_stats,
        )

    # ─── Handlers ──────────────────────────────────────────────

    async def _tool_search_documents(self, args: Dict[str, Any]) -> ToolResult:
        query = (args.get("query") or "").strip()
        top_k = int(args.get("top_k") or 5)
        if not query:
            return ToolResult.error("query is required")

        ck = f"search:{query.lower()}:{top_k}"
        if cached := _cache_get(ck):
            return ToolResult.json(cached, cache_hit=True)

        data, src = await bridge.search_documents(query, top_k=top_k)
        if data is None:
            return ToolResult.error(
                f"Не удалось обратиться к Sentinel AI backend ({src}). "
                f"Проверь что main.py запущен на {bridge.SENTINEL_BASE}"
            )

        # Сжимаем results — оставляем только нужные поля
        compact = {
            "query":   query,
            "count":   len(data.get("results", [])),
            "results": [
                {
                    "doc_name":      r.get("doc_name"),
                    "category":      r.get("category"),
                    "score":         r.get("score_hybrid") or r.get("score_semantic"),
                    "chunk_preview": (r.get("chunk_preview") or "")[:400],
                }
                for r in data.get("results", [])
            ],
            "source": "sentinel_backend",
        }
        _cache_set(ck, compact)
        return ToolResult.json(compact, cache_hit=False, source=src)

    async def _tool_list_documents(self, args: Dict[str, Any]) -> ToolResult:
        category = (args.get("category") or "").strip()
        limit = int(args.get("limit") or 50)

        ck = f"list:{category}:{limit}"
        if cached := _cache_get(ck):
            return ToolResult.json(cached, cache_hit=True)

        docs, src = await bridge.list_documents()
        if docs is None:
            return ToolResult.error(
                f"Не удалось получить список документов ({src})"
            )

        # Фильтр по категории
        if category:
            docs = [d for d in docs if d.get("category", "").lower() == category.lower()]

        # Сжимаем поля
        compact_docs = [
            {
                "id":          d.get("id"),
                "name":        d.get("name"),
                "category":    d.get("category"),
                "size":        d.get("size"),
                "chunk_count": d.get("chunk_count"),
                "created_at":  str(d.get("created_at")),
            }
            for d in docs[:limit]
        ]

        payload = {
            "total":     len(docs),
            "returned":  len(compact_docs),
            "category":  category or "all",
            "documents": compact_docs,
        }
        _cache_set(ck, payload)
        return ToolResult.json(payload, cache_hit=False, source=src)

    async def _tool_get_document(self, args: Dict[str, Any]) -> ToolResult:
        doc_id = int(args.get("doc_id") or 0)
        if not doc_id:
            return ToolResult.error("doc_id is required")

        doc, src = await bridge.get_document(doc_id)
        if doc is None and src == "not_found":
            return ToolResult.error(f"Документ с id={doc_id} не найден")
        if doc is None:
            return ToolResult.error(f"Ошибка получения документа: {src}")

        # Полный контент может быть огромным, обрезаем для MCP-ответа
        if "content" in doc and isinstance(doc["content"], str):
            content = doc["content"]
            if len(content) > 10000:
                doc["content"] = content[:10000] + f"\n\n[... обрезано, всего {len(content)} символов]"
                doc["truncated"] = True

        return ToolResult.json(doc, source=src)

    async def _tool_get_kb_stats(self, args: Dict[str, Any]) -> ToolResult:
        stats, src = await bridge.get_kb_stats()
        if stats is None:
            return ToolResult.error(f"Не удалось получить статистику: {src}")
        return ToolResult.json(stats, source=src)


# ══════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════

def main():
    parser = make_arg_parser(default_port=8103)
    args = parser.parse_args()
    setup_logging(args.log_level)

    # Health check на старте
    import asyncio
    setup_logging(args.log_level)
    logger.info(f"[docs MCP] Sentinel backend at {bridge.SENTINEL_BASE}")
    ok = asyncio.run(bridge.health_check())
    if not ok:
        logger.warning(
            f"⚠️  Sentinel AI backend недоступен на {bridge.SENTINEL_BASE}. "
            f"Сервер всё равно запустится, но все tools будут возвращать ошибки. "
            f"Сначала запусти: uvicorn main:app --port 8000"
        )
    else:
        logger.info(f"✅ Sentinel AI backend доступен")

    server = DocsMCPServer()
    serve(server, transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()