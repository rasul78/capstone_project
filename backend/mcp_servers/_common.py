"""
Sentinel AI — MCP Server Base (Custom Implementation)

Реализует Model Context Protocol (MCP) спецификации 2024-11-05.
Поддерживает два транспорта:
  • stdio  — канонический MCP transport (для интеграции с Claude Desktop,
             LangGraph через mcp_client.stdio_client)
  • HTTP   — REST-эндпоинт + SSE notifications (для отладки и веб-демо)

Зачем своя реализация (не SDK):
  • Capstone требует "build custom MCP wrappers" (слова эксперта)
  • Полный контроль над протоколом, валидацией, логированием
  • Минимум зависимостей (asyncio + httpx)
  • Прозрачно для ревью кода

JSON-RPC 2.0 messages, которые мы поддерживаем:
  Methods:
    initialize          — handshake
    tools/list          — список инструментов
    tools/call          — выполнить инструмент
    ping                — heartbeat
  Notifications:
    notifications/initialized
    notifications/cancelled
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Awaitable

logger = logging.getLogger("mcp")

# Protocol version we implement
MCP_PROTOCOL_VERSION = "2024-11-05"
JSONRPC_VERSION = "2.0"


# ════════════════════════════════════════════════════════════════════
# Data classes — типизированные обёртки JSON-RPC и MCP
# ════════════════════════════════════════════════════════════════════

@dataclass
class JsonRpcError:
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

    # Standard JSON-RPC error codes
    PARSE_ERROR      = -32700
    INVALID_REQUEST  = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS   = -32602
    INTERNAL_ERROR   = -32603


@dataclass
class ToolSchema:
    """MCP Tool definition. Соответствует tools/list response item."""
    name: str
    description: str
    input_schema: Dict[str, Any]              # JSON Schema for arguments

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":        self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class ToolResult:
    """MCP Tool execution result. Соответствует tools/call response."""
    content: List[Dict[str, Any]]             # array of {type, text|...}
    is_error: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def text(cls, text: str, **meta) -> "ToolResult":
        return cls(content=[{"type": "text", "text": text}], meta=meta)

    @classmethod
    def json(cls, obj: Any, **meta) -> "ToolResult":
        return cls(
            content=[{"type": "text", "text": json.dumps(obj, ensure_ascii=False, indent=2)}],
            meta={"data": obj, **meta},
        )

    @classmethod
    def error(cls, message: str, **meta) -> "ToolResult":
        return cls(content=[{"type": "text", "text": f"❌ {message}"}],
                   is_error=True, meta=meta)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "content":  self.content,
            "isError":  self.is_error,
        }
        if self.meta:
            result["_meta"] = self.meta
        return result


ToolHandler = Callable[[Dict[str, Any]], Awaitable[ToolResult]]


# ── Optional FastAPI imports (top-level so annotations resolve) ───
# Если FastAPI не установлен — HTTP transport будет недоступен,
# но stdio transport продолжит работать.
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False
    FastAPI = None        # type: ignore
    Request = None        # type: ignore
    JSONResponse = None   # type: ignore


# ════════════════════════════════════════════════════════════════════
# MCPServer — базовый класс, от которого наследуются legal/hr/docs
# ════════════════════════════════════════════════════════════════════

class MCPServer(ABC):
    """
    Базовый класс MCP-сервера. Наследники реализуют:
      • register_tools(self) — регистрируют свои tool handlers
      • server_info — название и версия

    Дальше base class берёт на себя:
      • JSON-RPC обработку
      • Двух-направленный stdio loop
      • Routing методов initialize/tools/list/tools/call
      • Error handling, logging, request tracking
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self._tools:    Dict[str, ToolSchema]   = {}
        self._handlers: Dict[str, ToolHandler]  = {}
        self._initialized = False
        self._stats = {
            "started_at":   time.time(),
            "requests":     0,
            "tool_calls":   0,
            "errors":       0,
        }
        self.register_tools()
        logger.info(f"[{self.name}] MCP server initialized, "
                    f"tools={len(self._tools)} ({list(self._tools)})")

    @abstractmethod
    def register_tools(self) -> None:
        """Подкласс вызывает self.register_tool(...) для каждого tool."""
        ...

    def register_tool(self, schema: ToolSchema, handler: ToolHandler) -> None:
        if schema.name in self._tools:
            raise ValueError(f"Tool {schema.name!r} already registered")
        self._tools[schema.name] = schema
        self._handlers[schema.name] = handler

    # ───────── JSON-RPC method routing ─────────────────────────────

    async def handle_request(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Главная точка входа. Принимает JSON-RPC message, возвращает response
        (или None для notifications, которые не требуют ответа).
        """
        self._stats["requests"] += 1
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}

        # Notification (нет id) — обрабатываем, не отвечаем
        if msg_id is None:
            await self._handle_notification(method, params)
            return None

        try:
            if method == "initialize":
                result = await self._on_initialize(params)
            elif method == "tools/list":
                result = await self._on_tools_list(params)
            elif method == "tools/call":
                result = await self._on_tools_call(params)
            elif method == "ping":
                result = {}
            else:
                return self._error_response(msg_id, JsonRpcError.METHOD_NOT_FOUND,
                                            f"Method not found: {method}")

            return {
                "jsonrpc": JSONRPC_VERSION,
                "id":      msg_id,
                "result":  result,
            }
        except Exception as e:
            self._stats["errors"] += 1
            logger.exception(f"[{self.name}] Error handling {method!r}: {e}")
            return self._error_response(msg_id, JsonRpcError.INTERNAL_ERROR,
                                        f"Internal error: {e}")

    async def _handle_notification(self, method: str, params: Dict[str, Any]) -> None:
        if method == "notifications/initialized":
            self._initialized = True
            logger.info(f"[{self.name}] Client initialized successfully")
        elif method == "notifications/cancelled":
            logger.info(f"[{self.name}] Request cancelled: {params.get('requestId')}")

    # ───────── MCP standard methods ────────────────────────────────

    async def _on_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        client_protocol = params.get("protocolVersion", "unknown")
        client_info     = params.get("clientInfo", {})
        logger.info(f"[{self.name}] initialize: client={client_info.get('name')}, "
                    f"protocol={client_protocol}")
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name":    self.name,
                "version": self.version,
            },
        }

    async def _on_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"tools": [t.to_dict() for t in self._tools.values()]}

    async def _on_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        if not tool_name:
            raise ValueError("Missing 'name' in tools/call params")
        if tool_name not in self._handlers:
            raise ValueError(f"Unknown tool: {tool_name}")

        self._stats["tool_calls"] += 1
        t0 = time.time()
        logger.info(f"[{self.name}] tools/call {tool_name}({arguments})")

        handler = self._handlers[tool_name]
        try:
            result = await handler(arguments)
        except Exception as e:
            self._stats["errors"] += 1
            logger.exception(f"[{self.name}] Tool {tool_name} error: {e}")
            result = ToolResult.error(f"Tool execution failed: {e}")

        latency_ms = int((time.time() - t0) * 1000)
        logger.info(f"[{self.name}] tools/call {tool_name} done in {latency_ms}ms, "
                    f"is_error={result.is_error}")

        # Inject latency into meta
        result.meta["latency_ms"] = latency_ms
        return result.to_dict()

    # ───────── Helpers ─────────────────────────────────────────────

    def _error_response(self, msg_id: Any, code: int, message: str,
                        data: Optional[Dict] = None) -> Dict[str, Any]:
        err: Dict[str, Any] = {"code": code, "message": message}
        if data:
            err["data"] = data
        return {"jsonrpc": JSONRPC_VERSION, "id": msg_id, "error": err}

    def stats(self) -> Dict[str, Any]:
        uptime = time.time() - self._stats["started_at"]
        return {
            **self._stats,
            "name":     self.name,
            "version":  self.version,
            "uptime_s": round(uptime, 1),
            "tools":    list(self._tools),
        }

    # ───────── Transport: stdio ────────────────────────────────────

    async def run_stdio(self) -> None:
        """
        Канонический MCP transport: line-delimited JSON-RPC over stdin/stdout.
        Используется Claude Desktop, LangGraph, MCP CLI.
        """
        logger.info(f"[{self.name}] Starting STDIO transport")

        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader(loop=loop)
        protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        w_transport, w_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout)
        writer = asyncio.StreamWriter(w_transport, w_protocol, None, loop)

        try:
            while True:
                line = await reader.readline()
                if not line:
                    logger.info(f"[{self.name}] stdin closed, shutting down")
                    break
                line = line.strip()
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError as e:
                    err_resp = self._error_response(None, JsonRpcError.PARSE_ERROR,
                                                    f"Parse error: {e}")
                    writer.write((json.dumps(err_resp) + "\n").encode())
                    await writer.drain()
                    continue

                response = await self.handle_request(msg)
                if response is not None:
                    writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode())
                    await writer.drain()
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info(f"[{self.name}] stdio loop cancelled")
        finally:
            writer.close()


# ════════════════════════════════════════════════════════════════════
# HTTP/SSE transport (для отладки и веб-демо)
# ════════════════════════════════════════════════════════════════════
# Используем FastAPI если установлен, иначе чистый aiohttp/asyncio HTTP server

def build_http_app(server: MCPServer):
    """
    Создаёт FastAPI приложение которое выставляет MCP-сервер через HTTP.

    Endpoints:
      POST /mcp        — отправить JSON-RPC request, получить response
      GET  /mcp/info   — server info + tool list (human-readable)
      GET  /mcp/stats  — статистика сервера

    Это не часть MCP стандарта (stdio — каноничный), но удобно для:
      • Postman/curl тестирования
      • Frontend demo (живая визуализация)
      • Health checks от внешних сервисов
    """
    if not _HAS_FASTAPI:
        raise RuntimeError("FastAPI not installed; HTTP transport unavailable")

    app = FastAPI(
        title=f"{server.name} (MCP HTTP bridge)",
        version=server.version,
        description=(
            f"Custom MCP server for {server.name}. "
            "Implements JSON-RPC 2.0 over HTTP as alternative to stdio transport. "
            "Useful for testing, debugging, and web-based demos."
        ),
    )

    @app.post("/mcp")
    async def mcp_endpoint(request: Request):
        try:
            body = await request.json()
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content=server._error_response(None, JsonRpcError.PARSE_ERROR, str(e)),
            )
        response = await server.handle_request(body)
        if response is None:
            # Notification — no response body
            return JSONResponse(status_code=204, content=None)
        return JSONResponse(content=response)

    @app.get("/mcp/info")
    async def mcp_info():
        return {
            "server":   {"name": server.name, "version": server.version},
            "protocol": MCP_PROTOCOL_VERSION,
            "tools":    [t.to_dict() for t in server._tools.values()],
        }

    @app.get("/mcp/stats")
    async def mcp_stats():
        return server.stats()

    @app.get("/")
    async def root():
        return {
            "name":     server.name,
            "type":     "MCP server (HTTP transport)",
            "endpoints": {
                "POST /mcp":       "JSON-RPC 2.0 endpoint",
                "GET /mcp/info":   "Server info + tool list",
                "GET /mcp/stats":  "Statistics",
            },
            "tools_count": len(server._tools),
        }

    return app


async def run_http(server: MCPServer, host: str = "127.0.0.1", port: int = 0) -> None:
    """Запускает HTTP-сервер через uvicorn (если установлен)."""
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn not installed")
    app = build_http_app(server)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    logger.info(f"[{server.name}] HTTP transport on http://{host}:{port}")
    await srv.serve()


# ════════════════════════════════════════════════════════════════════
# CLI entry point (used by each server's __main__)
# ════════════════════════════════════════════════════════════════════

def serve(server: MCPServer, transport: str = "stdio",
          host: str = "127.0.0.1", port: int = 0) -> None:
    """
    Универсальный entry point:
      python -m mcp_servers.legal_rk.server --transport stdio
      python -m mcp_servers.legal_rk.server --transport http --port 8101
    """
    if transport == "stdio":
        try:
            asyncio.run(server.run_stdio())
        except KeyboardInterrupt:
            logger.info(f"[{server.name}] stopped (KeyboardInterrupt)")
    elif transport == "http":
        try:
            asyncio.run(run_http(server, host=host, port=port))
        except KeyboardInterrupt:
            logger.info(f"[{server.name}] stopped (KeyboardInterrupt)")
    else:
        raise ValueError(f"Unknown transport: {transport!r}")


def make_arg_parser(default_port: int):
    """Helper: общий argparse для серверов."""
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio",
                   help="MCP transport mode")
    p.add_argument("--host", default="127.0.0.1", help="HTTP host")
    p.add_argument("--port", type=int, default=default_port, help="HTTP port")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def setup_logging(level: str = "INFO") -> None:
    """В stdio-режиме обязательно логировать в stderr (stdout занят протоколом)."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stderr,
    )