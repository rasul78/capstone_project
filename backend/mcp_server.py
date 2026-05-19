"""
Sentinel AI — MCP Server
Экспортирует инструменты базы знаний через Model Context Protocol.

Инструменты (Tools):
  - search_knowledge_base  : поиск по документам (RAG)
  - search_web             : живой веб-поиск
  - list_documents         : список всех документов
  - get_document_content   : получить содержимое документа
  - add_document           : добавить документ в базу

Запуск standalone:
  python mcp_server.py

Или интегрируется в FastAPI через lifespan.
"""

import os
import json
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentinel.mcp_server")

# ── MCP Tool definitions ───────────────────────────────────────────────────

MCP_TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Поиск релевантных документов в корпоративной базе знаний Sentinel AI. "
            "Используй для ответов на вопросы о политиках компании, процедурах, регламентах. "
            "Возвращает список релевантных фрагментов с источниками и оценкой релевантности."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Поисковый запрос на русском или английском языке"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Количество результатов (по умолчанию 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_web",
        "description": (
            "Живой поиск в интернете через DuckDuckGo. "
            "Используй когда информация не найдена в базе знаний или нужны актуальные данные."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Поисковый запрос"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_documents",
        "description": "Получить список всех документов в базе знаний с метаданными.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_document_content",
        "description": "Получить полное содержимое конкретного документа по его ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "integer",
                    "description": "ID документа"
                }
            },
            "required": ["doc_id"]
        }
    },
]


class SentinelMCPServer:
    """
    MCP-совместимый сервер инструментов Sentinel AI.
    Реализует протокол MCP для интеграции с LangGraph агентами.
    """

    def __init__(self, kb=None, web_agent=None):
        self.kb        = kb
        self.web_agent = web_agent
        self.tools     = MCP_TOOLS
        logger.info("[MCP] Sentinel MCP Server инициализирован, инструментов: %d", len(self.tools))

    def list_tools(self) -> List[Dict]:
        """Возвращает список доступных MCP инструментов."""
        return self.tools

    async def call_tool(self, name: str, arguments: Dict) -> Dict:
        """Выполняет MCP инструмент и возвращает результат."""
        logger.info("[MCP] Вызов инструмента: %s(%s)", name, list(arguments.keys()))

        try:
            if name == "search_knowledge_base":
                return await self._search_kb(arguments)
            elif name == "search_web":
                return await self._search_web(arguments)
            elif name == "list_documents":
                return await self._list_docs()
            elif name == "get_document_content":
                return await self._get_doc(arguments)
            else:
                return {"error": f"Неизвестный инструмент: {name}"}
        except Exception as e:
            logger.error("[MCP] Ошибка инструмента %s: %s", name, e)
            return {"error": str(e)}

    async def _search_kb(self, args: Dict) -> Dict:
        """Поиск в базе знаний."""
        if not self.kb:
            return {"results": [], "error": "База знаний недоступна"}

        query  = args.get("query", "")
        top_k  = int(args.get("top_k", 5))
        results = self.kb.search(query, top_k=top_k)

        chunks = []
        for r in results:
            chunks.append({
                "content":    r.get("chunk", ""),
                "source":     r.get("source", ""),
                "score":      round(r.get("score", 0), 3),
                "doc_id":     r.get("doc_id"),
                "category":   r.get("category", ""),
            })

        found = bool(chunks) and (chunks[0]["score"] > 0.25 if chunks else False)
        return {
            "found":   found,
            "count":   len(chunks),
            "results": chunks,
            "tool":    "search_knowledge_base",
        }

    async def _search_web(self, args: Dict) -> Dict:
        """Веб-поиск."""
        if not self.web_agent:
            return {"results": [], "found": False, "error": "WebAgent недоступен"}

        query  = args.get("query", "")
        result = await self.web_agent.run(query)
        return {
            "found":   result.found,
            "results": result.results[:5],
            "source":  result.source,
            "tool":    "search_web",
        }

    async def _list_docs(self) -> Dict:
        """Список документов."""
        if not self.kb:
            return {"documents": []}
        try:
            from database import db_list_documents
            docs = await db_list_documents()
            return {
                "count":     len(docs),
                "documents": [
                    {
                        "id":       d.get("id"),
                        "name":     d.get("name", ""),
                        "category": d.get("category", ""),
                        "size":     d.get("size", 0),
                        "chunks":   d.get("chunk_count", 0),
                    }
                    for d in docs
                ],
                "tool": "list_documents",
            }
        except Exception as e:
            return {"documents": [], "error": str(e)}

    async def _get_doc(self, args: Dict) -> Dict:
        """Содержимое документа."""
        doc_id = int(args.get("doc_id", 0))
        if not self.kb:
            return {"content": "", "error": "База знаний недоступна"}
        try:
            from database import db_list_documents
            docs = await db_list_documents()
            doc  = next((d for d in docs if d.get("id") == doc_id), None)
            if not doc:
                return {"error": f"Документ {doc_id} не найден"}
            return {
                "id":       doc_id,
                "name":     doc.get("name", ""),
                "category": doc.get("category", ""),
                "tool":     "get_document_content",
            }
        except Exception as e:
            return {"error": str(e)}


# ── HTTP MCP endpoint (для интеграции с FastAPI) ───────────────────────────

def create_mcp_router(mcp_server: SentinelMCPServer):
    """Создаёт FastAPI роутер для MCP протокола."""
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter(prefix="/mcp", tags=["MCP"])

    @router.get("/tools")
    async def mcp_list_tools():
        """MCP: список доступных инструментов."""
        return {"tools": mcp_server.list_tools()}

    @router.post("/tools/{tool_name}")
    async def mcp_call_tool(tool_name: str, request: Request):
        """MCP: вызов инструмента."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        result = await mcp_server.call_tool(tool_name, body)
        return JSONResponse(content=result)

    @router.get("/resources")
    async def mcp_list_resources():
        """MCP: доступные ресурсы."""
        return {
            "resources": [
                {
                    "uri":         "sentinel://kb/documents",
                    "name":        "База знаний",
                    "description": "Все документы Sentinel AI",
                    "mimeType":    "application/json",
                },
                {
                    "uri":         "sentinel://kb/stats",
                    "name":        "Статистика базы знаний",
                    "description": "Количество документов и чанков",
                    "mimeType":    "application/json",
                },
            ]
        }

    @router.get("/info")
    async def mcp_info():
        """MCP: информация о сервере."""
        return {
            "name":        "sentinel-ai-mcp-server",
            "version":     "1.0.0",
            "description": "Sentinel AI Knowledge Base MCP Server",
            "tools_count": len(mcp_server.list_tools()),
            "protocol":    "mcp/1.0",
        }

    return router