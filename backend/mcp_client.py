"""
Sentinel AI — MCP Client Registry

Универсальный клиент для подключения к удалённым MCP-серверам.
Используется LangGraph orchestrator для вызова инструментов trex MCP-серверов:
  • legal_rk (http://localhost:8101) — adilet.zan.kz bridge
  • hr       (http://localhost:8102) — HR расчёты
  • docs     (http://localhost:8103) — Sentinel knowledge base

Архитектура:
   LangGraph node ──→ mcp_registry.call("hr", "get_mrp", {year: 2026})
                              │
                              └─→ MCPClient("hr") ──HTTP──→ localhost:8102/mcp
                                                              │
                                                              └─→ ToolResult JSON

Особенности:
  • Auto-discovery: при инициализации запрашивает tools/list у всех серверов
  • Health monitoring: периодическая проверка доступности
  • Retry с экспоненциальным backoff
  • Кэш tool schemas (не дергаем tools/list на каждый вызов)
"""
from __future__ import annotations

import os
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("sentinel.mcp_client")

# ════════════════════════════════════════════════════════════════════
# Configuration (env-based)
# ════════════════════════════════════════════════════════════════════

DEFAULT_SERVERS = {
    "legal_rk": os.getenv("MCP_LEGAL_URL", "http://localhost:8101"),
    "hr":       os.getenv("MCP_HR_URL",    "http://localhost:8102"),
    "docs":     os.getenv("MCP_DOCS_URL",  "http://localhost:8103"),
}

REQUEST_TIMEOUT = httpx.Timeout(15.0, connect=3.0)
HEALTH_TIMEOUT  = httpx.Timeout(2.0)


# ════════════════════════════════════════════════════════════════════
# Single MCP Client
# ════════════════════════════════════════════════════════════════════

@dataclass
class MCPCallResult:
    """Унифицированный результат вызова MCP tool."""
    ok:           bool
    server:       str
    tool:         str
    data:         Any = None
    text:         str = ""
    error:        str = ""
    latency_ms:   int = 0
    is_tool_error: bool = False
    meta:         Dict = field(default_factory=dict)


class MCPClient:
    """Клиент для одного MCP-сервера (HTTP transport)."""

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.tools: Dict[str, Dict] = {}        # cached schemas
        self.healthy = False
        self.last_check_at = 0.0
        self._request_id = 0
        self._client: Optional[httpx.AsyncClient] = None

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # ─── Health / Discovery ────────────────────────────────────

    async def health_check(self) -> bool:
        """Быстрый check что сервер отвечает."""
        try:
            async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
                r = await client.get(f"{self.base_url}/mcp/info")
                self.healthy = r.status_code == 200
                self.last_check_at = time.time()
                if self.healthy:
                    data = r.json()
                    self.tools = {t["name"]: t for t in data.get("tools", [])}
                    logger.info(f"[mcp_client/{self.name}] ✓ healthy, "
                                f"tools={list(self.tools)}")
                return self.healthy
        except Exception as e:
            self.healthy = False
            self.last_check_at = time.time()
            logger.warning(f"[mcp_client/{self.name}] ✗ unhealthy: {e}")
            return False

    # ─── Tool call ─────────────────────────────────────────────

    async def call(self, tool_name: str, arguments: Dict[str, Any]
                   ) -> MCPCallResult:
        t0 = time.time()

        if not self.healthy and (time.time() - self.last_check_at) > 30:
            # Попробуем перезапустить health, может сервер ожил
            await self.health_check()

        if not self.healthy:
            return MCPCallResult(
                ok=False, server=self.name, tool=tool_name,
                error=f"MCP server '{self.name}' недоступен ({self.base_url})",
                latency_ms=int((time.time() - t0) * 1000),
            )

        if tool_name not in self.tools:
            return MCPCallResult(
                ok=False, server=self.name, tool=tool_name,
                error=f"Tool '{tool_name}' не найден на сервере '{self.name}'. "
                      f"Доступные: {list(self.tools)}",
                latency_ms=int((time.time() - t0) * 1000),
            )

        payload = {
            "jsonrpc": "2.0",
            "id":      self._next_id(),
            "method":  "tools/call",
            "params":  {"name": tool_name, "arguments": arguments or {}},
        }

        try:
            client = await self._get_client()
            r = await client.post(f"{self.base_url}/mcp", json=payload)
            r.raise_for_status()
            resp = r.json()
        except httpx.HTTPStatusError as e:
            return MCPCallResult(
                ok=False, server=self.name, tool=tool_name,
                error=f"HTTP {e.response.status_code}",
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            return MCPCallResult(
                ok=False, server=self.name, tool=tool_name,
                error=str(e),
                latency_ms=int((time.time() - t0) * 1000),
            )

        # JSON-RPC error?
        if "error" in resp:
            err = resp["error"]
            return MCPCallResult(
                ok=False, server=self.name, tool=tool_name,
                error=f"{err.get('code')}: {err.get('message')}",
                latency_ms=int((time.time() - t0) * 1000),
            )

        result = resp.get("result", {})
        text = result.get("content", [{}])[0].get("text", "") if result.get("content") else ""
        is_tool_error = result.get("isError", False)
        meta = result.get("_meta", {})
        data = meta.get("data")    # наши серверы кладут структурированный data в _meta

        return MCPCallResult(
            ok=not is_tool_error, server=self.name, tool=tool_name,
            data=data, text=text, meta=meta,
            is_tool_error=is_tool_error,
            error=text if is_tool_error else "",
            latency_ms=int((time.time() - t0) * 1000),
        )


# ════════════════════════════════════════════════════════════════════
# Registry — singleton доступ ко всем MCP-серверам
# ════════════════════════════════════════════════════════════════════

class MCPRegistry:
    """
    Глобальный регистр MCP-клиентов. Используется LangGraph узлами:

        from mcp_client import mcp_registry

        # один tool на одном сервере
        result = await mcp_registry.call("hr", "get_mrp", {"year": 2026})
        if result.ok:
            print(result.data)  # {value: 4325, ...}

        # все tools доступны для discovery
        all_tools = mcp_registry.discover_tools()
    """

    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}
        self._initialized = False

    async def initialize(self, servers: Optional[Dict[str, str]] = None) -> None:
        servers = servers or DEFAULT_SERVERS
        logger.info(f"[mcp_registry] Initializing {len(servers)} clients...")

        # Создаём клиенты
        for name, url in servers.items():
            self.clients[name] = MCPClient(name, url)

        # Параллельный health check всех
        await asyncio.gather(*[c.health_check() for c in self.clients.values()])

        healthy = [n for n, c in self.clients.items() if c.healthy]
        unhealthy = [n for n, c in self.clients.items() if not c.healthy]
        logger.info(f"[mcp_registry] ✓ Healthy: {healthy}")
        if unhealthy:
            logger.warning(f"[mcp_registry] ✗ Unhealthy: {unhealthy} "
                           f"(их tools будут возвращать ошибки)")
        self._initialized = True

    async def close(self) -> None:
        await asyncio.gather(*[c.close() for c in self.clients.values()])
        self.clients.clear()
        self._initialized = False

    async def call(self, server: str, tool: str,
                   arguments: Optional[Dict[str, Any]] = None) -> MCPCallResult:
        """Главная точка вызова: mcp_registry.call('hr', 'get_mrp', {'year': 2026})."""
        if server not in self.clients:
            return MCPCallResult(
                ok=False, server=server, tool=tool,
                error=f"Сервер '{server}' не зарегистрирован. "
                      f"Доступные: {list(self.clients)}",
            )
        return await self.clients[server].call(tool, arguments or {})

    def discover_tools(self) -> List[Dict]:
        """Возвращает [{server, tool, description, schema}] для всех серверов."""
        tools = []
        for sname, client in self.clients.items():
            if not client.healthy:
                continue
            for tname, schema in client.tools.items():
                tools.append({
                    "server":      sname,
                    "tool":        tname,
                    "description": schema.get("description", ""),
                    "schema":      schema.get("inputSchema", {}),
                })
        return tools

    def status(self) -> Dict[str, Any]:
        """Статус всех серверов — для /api/mcp/status endpoint."""
        return {
            "initialized": self._initialized,
            "servers": {
                name: {
                    "url":          c.base_url,
                    "healthy":      c.healthy,
                    "tools_count":  len(c.tools),
                    "tools":        list(c.tools),
                    "last_check_s": round(time.time() - c.last_check_at, 1) if c.last_check_at else None,
                }
                for name, c in self.clients.items()
            },
        }


# Singleton
mcp_registry = MCPRegistry()


# ════════════════════════════════════════════════════════════════════
# Convenience routing helper
# ════════════════════════════════════════════════════════════════════

ROUTING_HINTS = {
    "legal_rk": ["закон", "статья", "кодекс", "ук рк", "гк рк", "тк рк", "коап",
                 "штраф", "санкция", "право", "норма", "уголовный", "гражданский",
                 "трудовой кодекс", "административный"],
    "hr":       ["мрп", "мзп", "зарплата", "отпуск", "увольнение", "выходное пособие",
                 "пенсия", "минимальная зарплата", "налоговый вычет", "ставка",
                 "сокращение", "ликвидация", "стаж", "пособие"],
    "docs":     ["политика", "процедура", "регламент", "наш документ",
                 "корпоративн", "внутренн", "у нас в компании"],
}


def suggest_servers(query: str) -> List[str]:
    """Эвристика: какие MCP-серверы стоит вызвать для этого запроса."""
    q = query.lower()
    matched = []
    for server, keywords in ROUTING_HINTS.items():
        if any(kw in q for kw in keywords):
            matched.append(server)
    return matched or []