"""
Sentinel AI / legal_rk MCP Server

Custom MCP server that bridges adilet.zan.kz (HTTP) to MCP-compliant tools.

Exposes 4 tools:
  • search_law(query)              — поиск по правовой базе РК
  • get_article(code, number)      — конкретная статья кодекса
  • fetch_law_page(url)            — содержимое страницы adilet.zan.kz
  • list_codes()                   — какие кодексы поддерживаются

Run modes:
  python -m mcp_servers.legal_rk.server --transport stdio
  python -m mcp_servers.legal_rk.server --transport http --port 8101
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Any, List

from mcp_servers import (
    MCPServer, ToolSchema, ToolResult,
    serve, make_arg_parser, setup_logging,
)
from . import bridge, mock_data

logger = logging.getLogger("mcp.legal_rk")

# Простой in-memory кэш (query → result) с TTL 10 минут
_CACHE: Dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 600


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


class LegalRkMCPServer(MCPServer):
    """MCP-сервер для законодательства РК."""

    def __init__(self):
        super().__init__("sentinel-legal-rk", "1.0.0")

    def register_tools(self) -> None:

        # ── Tool 1: search_law ───────────────────────────────────
        self.register_tool(
            ToolSchema(
                name="search_law",
                description=(
                    "Поиск по правовой базе Республики Казахстан (adilet.zan.kz). "
                    "Принимает свободный текстовый запрос. "
                    "Возвращает релевантные статьи кодексов и нормативных актов. "
                    "Используется внутренним AI-агентом для ответов на вопросы о "
                    "законах, штрафах, правах работников, налогах, и пр."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Текстовый запрос на русском",
                            "minLength": 2,
                            "maxLength": 300,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Сколько результатов вернуть (1-10)",
                            "default": 5, "minimum": 1, "maximum": 10,
                        },
                    },
                    "required": ["query"],
                },
            ),
            self._tool_search_law,
        )

        # ── Tool 2: get_article ──────────────────────────────────
        self.register_tool(
            ToolSchema(
                name="get_article",
                description=(
                    "Получить конкретную статью кодекса РК по её номеру. "
                    "Поддерживаемые кодексы: ТК РК, ГК РК, УК РК, КоАП РК. "
                    "Пример: get_article(code='ТК РК', article_number='84') "
                    "вернёт статью 84 Трудового кодекса (право на отпуск)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Код / название кодекса (ТК РК, ГК РК, УК РК, КоАП РК)",
                        },
                        "article_number": {
                            "type": "string",
                            "description": "Номер статьи как строка ('84', '143', '205'...)",
                        },
                    },
                    "required": ["code", "article_number"],
                },
            ),
            self._tool_get_article,
        )

        # ── Tool 3: fetch_law_page ───────────────────────────────
        self.register_tool(
            ToolSchema(
                name="fetch_law_page",
                description=(
                    "Скачать содержимое конкретной страницы adilet.zan.kz. "
                    "URL должен начинаться с https://adilet.zan.kz/. "
                    "Возвращает извлечённый текст (до 4000 символов)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type":   "string",
                            "format": "uri",
                            "description": "Ссылка на страницу adilet.zan.kz",
                        },
                    },
                    "required": ["url"],
                },
            ),
            self._tool_fetch_law_page,
        )

        # ── Tool 4: list_codes ───────────────────────────────────
        self.register_tool(
            ToolSchema(
                name="list_codes",
                description="Вернуть список поддерживаемых кодексов РК и их короткие коды.",
                input_schema={"type": "object", "properties": {}, "required": []},
            ),
            self._tool_list_codes,
        )

    # ────────── Handlers ──────────────────────────────────────────

    async def _tool_search_law(self, args: Dict[str, Any]) -> ToolResult:
        query = (args.get("query") or "").strip()
        limit = int(args.get("limit") or 5)
        if not query:
            return ToolResult.error("query is required")

        ck = f"search:{query.lower()}:{limit}"
        cached = _cache_get(ck)
        if cached:
            return ToolResult.json(cached, cache_hit=True)

        results, source = await bridge.search_law(query, limit=limit)
        payload = {
            "query":   query,
            "source":  source,
            "count":   len(results),
            "results": results,
        }
        _cache_set(ck, payload)
        return ToolResult.json(payload, cache_hit=False, source=source)

    async def _tool_get_article(self, args: Dict[str, Any]) -> ToolResult:
        code = (args.get("code") or "").strip()
        number = str(args.get("article_number") or "").strip()
        if not code or not number:
            return ToolResult.error("code and article_number are required")

        ck = f"article:{code.lower()}:{number}"
        cached = _cache_get(ck)
        if cached:
            return ToolResult.json(cached, cache_hit=True)

        article, source = await bridge.get_article(code, number)
        if not article:
            return ToolResult.error(
                f"Статья {number} кодекса '{code}' не найдена. "
                f"Доступные кодексы: {', '.join(mock_data.list_codes())}"
            )
        payload = {"article": article, "source": source}
        _cache_set(ck, payload)
        return ToolResult.json(payload, cache_hit=False, source=source)

    async def _tool_fetch_law_page(self, args: Dict[str, Any]) -> ToolResult:
        url = (args.get("url") or "").strip()
        if not url:
            return ToolResult.error("url is required")
        if not url.startswith("https://adilet.zan.kz/"):
            return ToolResult.error("Only adilet.zan.kz URLs are allowed")

        text, source = await bridge.fetch_page(url)
        if not text:
            return ToolResult.error(f"Failed to fetch {url} ({source})")
        return ToolResult.json(
            {"url": url, "text": text, "chars": len(text), "source": source},
            source=source,
        )

    async def _tool_list_codes(self, args: Dict[str, Any]) -> ToolResult:
        return ToolResult.json({
            "codes":   mock_data.list_codes(),
            "aliases": mock_data.ALIASES,
        })


# ══════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════

def main():
    parser = make_arg_parser(default_port=8101)
    args = parser.parse_args()
    setup_logging(args.log_level)
    server = LegalRkMCPServer()
    serve(server, transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()