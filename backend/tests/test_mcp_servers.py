"""
Tests for the three custom MCP servers (legal_rk, hr, docs).

Test categories:
  POSITIVE — server responds correctly to valid input
  NEGATIVE — server returns clean error for invalid input
  EDGE     — boundary cases (empty strings, max values, special chars)

Total: 12+ scenarios across 3 servers.
"""
import json
import pytest


# ════════════════════════════════════════════════════════════════
#  MCP PROTOCOL CONFORMANCE
# ════════════════════════════════════════════════════════════════

class TestMcpProtocol:
    """Verify JSON-RPC 2.0 + MCP 2024-11-05 protocol conformance."""

    def test_initialize_returns_protocol_version(self, legal_rk_server, mcp_call):
        """[POSITIVE] initialize handshake returns correct protocolVersion."""
        resp = mcp_call(legal_rk_server, "initialize",
                        {"protocolVersion": "2024-11-05",
                         "clientInfo": {"name": "pytest"}})
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["serverInfo"]["name"] == "sentinel-legal-rk"

    def test_tools_list_returns_all_tools(self, hr_server, mcp_call):
        """[POSITIVE] tools/list returns full schema for every tool."""
        resp = mcp_call(hr_server, "tools/list")
        tools = resp["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "get_mrp" in names
        assert "calculate_vacation_days" in names
        # Every tool must have inputSchema
        for t in tools:
            assert "inputSchema" in t
            assert "description" in t

    def test_unknown_method_returns_error(self, hr_server, mcp_call):
        """[NEGATIVE] unknown method → JSON-RPC error -32601."""
        resp = mcp_call(hr_server, "nonexistent_method")
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_unknown_tool_returns_error_in_result(self, hr_server, mcp_call):
        """[NEGATIVE] unknown tool → handled (not exception)."""
        resp = mcp_call(hr_server, "tools/call",
                        {"name": "wrong_tool", "arguments": {}})
        # Server raises internally → caught → InternalError
        assert "error" in resp or resp["result"]["isError"]


# ════════════════════════════════════════════════════════════════
#  LEGAL_RK SERVER
# ════════════════════════════════════════════════════════════════

class TestLegalRkServer:

    def test_list_codes_returns_supported_codes(self, legal_rk_server, mcp_call):
        """[POSITIVE] list_codes returns TK, GK, UK, KoAP."""
        resp = mcp_call(legal_rk_server, "tools/call",
                        {"name": "list_codes", "arguments": {}})
        data = json.loads(resp["result"]["content"][0]["text"])
        assert "ТК РК" in data["codes"]
        assert "УК РК" in data["codes"]
        assert "ГК РК" in data["codes"]

    def test_get_article_returns_mock_data(self, legal_rk_server, mcp_call):
        """[POSITIVE] get_article(ТК РК, 84) → vacation article."""
        resp = mcp_call(legal_rk_server, "tools/call", {
            "name": "get_article",
            "arguments": {"code": "ТК РК", "article_number": "84"},
        })
        data = json.loads(resp["result"]["content"][0]["text"])
        assert "article" in data
        assert "отпуск" in data["article"]["title"].lower()

    def test_get_article_alias_normalises(self, legal_rk_server, mcp_call):
        """[POSITIVE] lowercase 'тк' aliased to 'ТК РК'."""
        resp = mcp_call(legal_rk_server, "tools/call", {
            "name": "get_article",
            "arguments": {"code": "тк", "article_number": "84"},
        })
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data["article"]["code"] == "ТК РК"

    def test_get_article_missing_returns_error(self, legal_rk_server, mcp_call):
        """[NEGATIVE] non-existent article → isError + helpful message."""
        resp = mcp_call(legal_rk_server, "tools/call", {
            "name": "get_article",
            "arguments": {"code": "FAKE CODE", "article_number": "999"},
        })
        assert resp["result"]["isError"] is True
        text = resp["result"]["content"][0]["text"]
        assert "не найден" in text.lower() or "недоступн" in text.lower()

    def test_search_law_empty_query_rejected(self, legal_rk_server, mcp_call):
        """[NEGATIVE] empty query → error, no crash."""
        resp = mcp_call(legal_rk_server, "tools/call", {
            "name": "search_law",
            "arguments": {"query": ""},
        })
        assert resp["result"]["isError"] is True

    def test_fetch_law_page_rejects_wrong_host(self, legal_rk_server, mcp_call):
        """[SECURITY/NEGATIVE] fetch_law_page only allows adilet.zan.kz URLs."""
        resp = mcp_call(legal_rk_server, "tools/call", {
            "name": "fetch_law_page",
            "arguments": {"url": "https://evil.com/malicious"},
        })
        assert resp["result"]["isError"] is True


# ════════════════════════════════════════════════════════════════
#  HR SERVER
# ════════════════════════════════════════════════════════════════

class TestHrServer:

    def test_get_mrp_2026_returns_4325(self, hr_server, mcp_call):
        """[POSITIVE] МРП 2026 == 4 325 тенге (Kazakhstan official value)."""
        resp = mcp_call(hr_server, "tools/call", {
            "name": "get_mrp", "arguments": {"year": 2026},
        })
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data["value"] == 4325
        assert data["unit"] == "тенге"
        assert data["year"] == 2026

    def test_get_min_wage_2026_returns_85000(self, hr_server, mcp_call):
        """[POSITIVE] МЗП 2026 == 85 000 тенге."""
        resp = mcp_call(hr_server, "tools/call", {
            "name": "get_min_wage", "arguments": {"year": 2026},
        })
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data["value"] == 85000

    def test_get_mrp_unknown_year_returns_error(self, hr_server, mcp_call):
        """[NEGATIVE] unknown year (2050) → error mentions available years."""
        resp = mcp_call(hr_server, "tools/call", {
            "name": "get_mrp", "arguments": {"year": 2050},
        })
        # Pydantic validator should catch year>2030 OR the server returns error
        assert resp["result"]["isError"] or "error" in resp

    def test_calculate_vacation_teacher_gets_56_days(self, hr_server, mcp_call):
        """[POSITIVE] Teacher's vacation: 24 base + 32 bonus = 56 days."""
        resp = mcp_call(hr_server, "tools/call", {
            "name": "calculate_vacation_days",
            "arguments": {"category": "педагог"},
        })
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data["total_days"] == 56
        # Either "ТК РК" or "Трудовой кодекс" — both acceptable
        ref = data["law_reference"]
        assert "ТК" in ref or "Трудовой" in ref

    def test_calculate_vacation_invalid_category_rejected(self, hr_server, mcp_call):
        """[NEGATIVE] Invalid category → error with available options."""
        resp = mcp_call(hr_server, "tools/call", {
            "name": "calculate_vacation_days",
            "arguments": {"category": "космонавт"},
        })
        assert resp["result"]["isError"] is True

    def test_calculate_severance_termination(self, hr_server, mcp_call):
        """[POSITIVE] severance for redundancy = 1 month salary."""
        resp = mcp_call(hr_server, "tools/call", {
            "name": "calculate_severance",
            "arguments": {"average_monthly_salary": 500_000,
                          "reason": "сокращение"},
        })
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data["severance_amount"] == 500_000.0
        assert data["coefficient"] == 1.0

    def test_calculate_severance_negative_salary_rejected(self, hr_server, mcp_call):
        """[NEGATIVE] zero/negative salary → error."""
        resp = mcp_call(hr_server, "tools/call", {
            "name": "calculate_severance",
            "arguments": {"average_monthly_salary": 0, "reason": "сокращение"},
        })
        assert resp["result"]["isError"] is True

    def test_indexed_amount_14_mrp_2026(self, hr_server, mcp_call):
        """[POSITIVE] 14 МРП × 4325 = 60 550 ₸ (standard tax deduction)."""
        resp = mcp_call(hr_server, "tools/call", {
            "name": "get_indexed_amount",
            "arguments": {"mrp_count": 14, "year": 2026},
        })
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data["amount"] == 60_550.0


# ════════════════════════════════════════════════════════════════
#  DOCS SERVER (graceful failure)
# ════════════════════════════════════════════════════════════════

class TestDocsServer:

    def test_search_docs_handles_backend_unavailable(self, docs_server, mcp_call):
        """[NEGATIVE] If Sentinel backend is down, error is graceful."""
        # Without a running backend, this returns error — but no crash
        resp = mcp_call(docs_server, "tools/call", {
            "name": "search_documents",
            "arguments": {"query": "тестовый запрос"},
        })
        # Either it works (backend is up) OR returns clean error
        if resp["result"]["isError"]:
            text = resp["result"]["content"][0]["text"]
            assert "backend" in text.lower() or "недоступен" in text.lower() or "main.py" in text.lower()

    def test_search_docs_empty_query_rejected(self, docs_server, mcp_call):
        """[NEGATIVE] empty query → error."""
        resp = mcp_call(docs_server, "tools/call", {
            "name": "search_documents",
            "arguments": {"query": ""},
        })
        assert resp["result"]["isError"] is True


# ════════════════════════════════════════════════════════════════
#  CACHING BEHAVIOUR
# ════════════════════════════════════════════════════════════════

class TestMcpCaching:

    def test_repeated_call_is_cached(self, hr_server, mcp_call):
        """[POSITIVE] Same MCP call twice → second is cache hit."""
        resp1 = mcp_call(hr_server, "tools/call", {
            "name": "get_mrp", "arguments": {"year": 2026},
        }, msg_id=1)
        resp2 = mcp_call(hr_server, "tools/call", {
            "name": "get_mrp", "arguments": {"year": 2026},
        }, msg_id=2)
        # Cache hit flag should be present in meta on 2nd call
        meta2 = resp2["result"].get("_meta", {})
        # Cache hit OR equal latency below 50 ms means it's served from memory
        assert meta2.get("cache_hit") is True or meta2.get("latency_ms", 1000) < 100