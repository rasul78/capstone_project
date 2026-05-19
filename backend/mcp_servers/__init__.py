"""
Sentinel AI — Custom MCP Servers

Three standalone MCP servers that act as HTTP-to-MCP bridges:
  • legal_rk : adilet.zan.kz bridge (laws, codes, articles of Kazakhstan)
  • hr       : HR calculations (vacation days, MRP, MZP, severance)
  • docs     : Sentinel AI internal docs bridge (search, get, list)

Each server runs as an independent process with dual transport:
  • stdio (canonical MCP, used by LangGraph mcp_client.stdio_client)
  • HTTP/SSE (for debugging, demo, and Postman testing)

Usage:
  python -m mcp_servers.legal_rk.server --transport stdio
  python -m mcp_servers.hr.server       --transport http --port 8102
"""
from ._common import (
    MCPServer, ToolSchema, ToolResult, JsonRpcError,
    serve, make_arg_parser, setup_logging,
    MCP_PROTOCOL_VERSION, JSONRPC_VERSION,
)

__all__ = [
    "MCPServer", "ToolSchema", "ToolResult", "JsonRpcError",
    "serve", "make_arg_parser", "setup_logging",
    "MCP_PROTOCOL_VERSION", "JSONRPC_VERSION",
]