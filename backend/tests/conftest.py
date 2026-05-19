"""
Pytest fixtures for Sentinel AI test suite.

Defines:
  • Mock KnowledgeBase  (no real PostgreSQL needed)
  • Mock Orchestrator
  • Mock MCP servers (FastAPI test clients)
  • Real MCP server instances (in-process)
  • Sample test data
"""
from __future__ import annotations

import sys
import os
import asyncio
import pytest
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import MagicMock, AsyncMock

# Add backend/ to path so tests can import directly
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Disable noisy logs during tests
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentinel").setLevel(logging.WARNING)


# ════════════════════════════════════════════════════════════════
#  Sample data
# ════════════════════════════════════════════════════════════════

SAMPLE_DOCUMENTS = [
    {
        "id": 1,
        "name": "HR_Vacation_Policy",
        "category": "HR",
        "size": 2048,
        "chunk_count": 5,
        "content": (
            "Корпоративная политика по отпускам. Минимальный отпуск — 24 "
            "календарных дня. Педагогам предоставляется удлинённый отпуск — "
            "56 дней. Заявление подаётся за 14 дней до начала отпуска."
        ),
    },
    {
        "id": 2,
        "name": "Financial_Regulations",
        "category": "Финансы",
        "size": 4096,
        "chunk_count": 8,
        "content": (
            "Лимит корпоративной карты — 500 000 тенге в месяц для рядовых "
            "сотрудников, 1 500 000 тенге для руководителей. Превышение требует "
            "согласования с финансовым директором."
        ),
    },
    {
        "id": 3,
        "name": "Security_Policy",
        "category": "Безопасность",
        "size": 1536,
        "chunk_count": 4,
        "content": (
            "Пароли должны содержать минимум 12 символов, включая заглавные, "
            "строчные, цифры и спецсимволы. Смена пароля — каждые 90 дней."
        ),
    },
]


# ════════════════════════════════════════════════════════════════
#  Knowledge Base mock
# ════════════════════════════════════════════════════════════════

class MockKnowledgeBase:
    """Drop-in replacement for the real KB during tests."""

    def __init__(self, docs=None):
        self.docs = docs or SAMPLE_DOCUMENTS

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Naïve keyword scoring; good enough for tests."""
        q = query.lower()
        results = []
        for d in self.docs:
            content = d["content"].lower()
            # Score by keyword overlap
            q_words = set(w for w in q.split() if len(w) >= 3)
            matched = sum(1 for w in q_words if w in content)
            if matched == 0:
                continue
            score = matched / max(len(q_words), 1)
            results.append({
                "doc_name":  d["name"],
                "category":  d["category"],
                "chunk":     d["content"],
                "score":     score,
                "doc_id":    d["id"],
            })
        results.sort(key=lambda x: -x["score"])
        return results[:top_k]


@pytest.fixture
def mock_kb():
    return MockKnowledgeBase()


@pytest.fixture
def empty_kb():
    return MockKnowledgeBase(docs=[])


# ════════════════════════════════════════════════════════════════
#  Orchestrator mock
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_orchestrator():
    o = MagicMock()
    o.synthesis = MagicMock()
    o.synthesis._ollama_ok = False
    o.synthesis._model = "llama3:latest"
    o.synthesis._call_ollama = MagicMock(return_value="Mock Ollama answer.")
    o._web = None
    return o


# ════════════════════════════════════════════════════════════════
#  Real MCP server instances (in-process — fast)
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def legal_rk_server():
    from mcp_servers.legal_rk.server import LegalRkMCPServer
    return LegalRkMCPServer()


@pytest.fixture
def hr_server():
    from mcp_servers.hr.server import HrMCPServer
    return HrMCPServer()


@pytest.fixture
def docs_server():
    from mcp_servers.docs.server import DocsMCPServer
    return DocsMCPServer()


# ════════════════════════════════════════════════════════════════
#  Async helpers
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def event_loop():
    """Per-test event loop so async tests don't share state."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def call_mcp(server, method: str, params: dict = None, msg_id: int = 1):
    """Synchronous wrapper for server.handle_request()."""
    msg = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(server.handle_request(msg))
    finally:
        loop.close()


@pytest.fixture
def mcp_call():
    """Shortcut for invoking MCP servers in tests."""
    return call_mcp


# ════════════════════════════════════════════════════════════════
#  Disable real LLM calls in tests
# ════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def disable_real_llms(monkeypatch):
    """Prevent accidental real API calls during tests."""
    monkeypatch.setenv("GROQ_API_KEY",      "TEST_DISABLED")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY",    "")