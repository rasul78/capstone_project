"""
Sentinel AI — MCP Lifecycle & Status Routes

Подключается из main.py:
    from mcp_routes import init_mcp_registry, close_mcp_registry, build_mcp_status_router

    @app.on_event("startup")
    async def startup():
        ...
        await init_mcp_registry()       # discovery всех MCP-серверов
        ...

    app.include_router(build_mcp_status_router())
"""
import logging
from fastapi import APIRouter

from mcp_client import mcp_registry

logger = logging.getLogger("sentinel.mcp_routes")


async def init_mcp_registry():
    """Инициализация MCP registry на старте приложения.
    Не падает если серверы недоступны — просто помечает их unhealthy."""
    try:
        await mcp_registry.initialize()
        status = mcp_registry.status()
        healthy = [n for n, s in status["servers"].items() if s["healthy"]]
        if healthy:
            logger.info(f"✅ MCP registry: {len(healthy)} серверов готовы: {healthy}")
        else:
            logger.warning(
                "⚠️  MCP registry: ни один сервер не отвечает. "
                "Запусти отдельно в других окнах:\n"
                "    python -m mcp_servers.legal_rk.server --transport http --port 8101\n"
                "    python -m mcp_servers.hr.server       --transport http --port 8102\n"
                "    python -m mcp_servers.docs.server     --transport http --port 8103"
            )
    except Exception as e:
        logger.error(f"⚠️  init_mcp_registry error: {e}")


async def close_mcp_registry():
    try:
        await mcp_registry.close()
    except Exception:
        pass


def build_mcp_status_router() -> APIRouter:
    router = APIRouter(prefix="/api/mcp", tags=["mcp"])

    @router.get("/status")
    async def mcp_status():
        """Какие MCP-серверы активны и какие tools доступны."""
        return mcp_registry.status()

    @router.get("/tools")
    async def mcp_tools():
        """Плоский список всех инструментов всех MCP-серверов."""
        return {"tools": mcp_registry.discover_tools()}

    @router.post("/recheck")
    async def mcp_recheck():
        """Перепроверить health всех MCP-серверов (если они только что запустились)."""
        import asyncio
        await asyncio.gather(*[c.health_check() for c in mcp_registry.clients.values()])
        return mcp_registry.status()

    @router.post("/call")
    async def mcp_call(body: dict):
        """
        Прямой вызов MCP-инструмента (для отладки и фронт-демо).
        Тело: {"server": "hr", "tool": "get_mrp", "arguments": {"year": 2026}}
        """
        server = body.get("server", "")
        tool = body.get("tool", "")
        args = body.get("arguments", {})
        result = await mcp_registry.call(server, tool, args)
        return {
            "ok":         result.ok,
            "server":     result.server,
            "tool":       result.tool,
            "data":       result.data,
            "text":       result.text,
            "error":      result.error,
            "latency_ms": result.latency_ms,
        }

    return router