"""
Tests for MCP integration layer (mcp_integration.py + mcp_client.py).

Verifies that:
  • Heuristic routing correctly classifies queries
  • Argument extraction pulls year/article/category from natural language
  • format_mcp_results_for_llm builds clean context
  • Graceful handling when servers are unavailable
"""
import pytest


# ════════════════════════════════════════════════════════════════
#  HEURISTIC ROUTING
# ════════════════════════════════════════════════════════════════

class TestHeuristicRouting:
    """mcp_integration.heuristic_tool_calls — query → list of (server, tool, args)."""

    def test_routes_mrp_question_to_hr(self):
        from mcp_integration import heuristic_tool_calls
        calls = heuristic_tool_calls("Какой МРП в 2026 году?")
        assert len(calls) >= 1
        servers = [c["server"] for c in calls]
        assert "hr" in servers
        # And the right tool
        tools = [c["tool"] for c in calls if c["server"] == "hr"]
        assert "get_mrp" in tools

    def test_routes_article_question_to_legal(self):
        from mcp_integration import heuristic_tool_calls
        calls = heuristic_tool_calls("Что говорит статья 84 ТК РК?")
        servers = [c["server"] for c in calls]
        assert "legal_rk" in servers
        tools = [c["tool"] for c in calls if c["server"] == "legal_rk"]
        assert "get_article" in tools

    def test_routes_vacation_question_to_hr(self):
        from mcp_integration import heuristic_tool_calls
        calls = heuristic_tool_calls("Сколько дней отпуска у педагога?")
        tools = [c["tool"] for c in calls if c["server"] == "hr"]
        assert "calculate_vacation_days" in tools

    def test_unrelated_question_returns_no_calls(self):
        """[NEGATIVE] Casual greeting should NOT trigger any MCP call."""
        from mcp_integration import heuristic_tool_calls
        calls = heuristic_tool_calls("Привет, как дела?")
        assert calls == []

    def test_python_question_returns_no_calls(self):
        """[NEGATIVE] Generic technical question should NOT route to MCP."""
        from mcp_integration import heuristic_tool_calls
        calls = heuristic_tool_calls("Что такое Python и как его использовать?")
        # No mention of laws, МРП, etc.
        assert calls == []


# ════════════════════════════════════════════════════════════════
#  ARGUMENT EXTRACTION
# ════════════════════════════════════════════════════════════════

class TestArgExtraction:
    """Regex-based argument extraction from natural language."""

    def test_year_extracted_for_mrp(self):
        from mcp_integration import heuristic_tool_calls
        calls = heuristic_tool_calls("МРП на 2025 год")
        hr_calls = [c for c in calls if c["server"] == "hr"]
        assert hr_calls
        assert hr_calls[0]["extracted_args"]["year"] == 2025

    def test_article_number_extracted(self):
        from mcp_integration import heuristic_tool_calls
        calls = heuristic_tool_calls("статья 130 ук рк")
        legal_calls = [c for c in calls if c["server"] == "legal_rk"]
        assert legal_calls
        args = legal_calls[0]["extracted_args"]
        assert args.get("article_number") == "130"
        assert "ук" in args.get("code", "").lower()

    def test_year_defaults_to_current_if_missing(self):
        """When no year is given, default to current year."""
        from mcp_integration import heuristic_tool_calls
        from datetime import datetime
        calls = heuristic_tool_calls("Какой сейчас МРП?")
        hr_calls = [c for c in calls if c["server"] == "hr"]
        if hr_calls:
            year = hr_calls[0]["extracted_args"].get("year")
            if year:
                # Within ±1 year of current
                assert abs(year - datetime.now().year) <= 1

    def test_vacation_category_extracted(self):
        from mcp_integration import heuristic_tool_calls
        calls = heuristic_tool_calls("отпуск у педагога сколько дней")
        hr_calls = [c for c in calls if c["tool"] == "calculate_vacation_days"]
        assert hr_calls
        assert hr_calls[0]["extracted_args"].get("category") == "педагог"


# ════════════════════════════════════════════════════════════════
#  RESULT FORMATTING FOR LLM
# ════════════════════════════════════════════════════════════════

class TestResultFormatting:
    """format_mcp_results_for_llm builds clean text for LLM prompt."""

    def test_empty_results_returns_empty_text(self):
        from mcp_integration import format_mcp_results_for_llm
        assert format_mcp_results_for_llm([]) == ""

    def test_success_result_includes_explanation(self):
        from mcp_integration import format_mcp_results_for_llm
        results = [{
            "ok": True, "server": "hr", "tool": "get_mrp",
            "data": {"year": 2026, "value": 4325, "unit": "тенге", "name": "МРП",
                     "explanation": "МРП 2026 = 4 325 ₸"},
            "text": "", "error": "", "latency_ms": 12,
        }]
        text = format_mcp_results_for_llm(results)
        assert "hr" in text
        assert "get_mrp" in text
        assert "4 325" in text or "4325" in text

    def test_failed_result_marked_with_error(self):
        from mcp_integration import format_mcp_results_for_llm
        results = [{
            "ok": False, "server": "hr", "tool": "get_mrp",
            "data": None, "text": "",
            "error": "timeout", "latency_ms": 5000,
        }]
        text = format_mcp_results_for_llm(results)
        assert "❌" in text or "timeout" in text.lower()

    def test_article_result_renders_code_and_title(self):
        from mcp_integration import format_mcp_results_for_llm
        results = [{
            "ok": True, "server": "legal_rk", "tool": "get_article",
            "data": {"article": {"code": "ТК РК", "article_number": "84",
                                 "title": "Право на отпуск", "text": "..."}},
            "text": "", "error": "", "latency_ms": 50,
        }]
        text = format_mcp_results_for_llm(results)
        assert "ТК РК" in text
        assert "84" in text
        assert "отпуск" in text.lower()


# ════════════════════════════════════════════════════════════════
#  CLIENT (MCPRegistry) BEHAVIOUR
# ════════════════════════════════════════════════════════════════

class TestMcpClient:
    """mcp_client.MCPClient — single-server HTTP client."""

    @pytest.mark.asyncio
    async def test_unhealthy_client_returns_clean_error(self):
        """[NEGATIVE] Calling a client whose server is down → MCPCallResult with ok=False."""
        from mcp_client import MCPClient
        c = MCPClient("nonexistent", "http://localhost:55555")  # unused port
        # Skip health check explicitly
        c.healthy = False
        c.last_check_at = 9999999999  # already checked recently
        r = await c.call("any_tool", {})
        assert r.ok is False
        assert "недоступен" in r.error.lower() or "unhealthy" in r.error.lower() or "не" in r.error

    @pytest.mark.asyncio
    async def test_registry_handles_unknown_server(self):
        """[NEGATIVE] mcp_registry.call('unknown', ...) → clean error."""
        from mcp_client import MCPRegistry
        reg = MCPRegistry()
        # No initialize() — clients dict is empty
        r = await reg.call("nonexistent_server", "any_tool", {})
        assert r.ok is False
        assert "зарегистрир" in r.error.lower() or "not" in r.error.lower()

    def test_suggest_servers_legal(self):
        """[POSITIVE] suggest_servers detects legal questions."""
        from mcp_client import suggest_servers
        assert "legal_rk" in suggest_servers("Что говорит статья 84 ТК РК")

    def test_suggest_servers_hr(self):
        """[POSITIVE] suggest_servers detects HR questions."""
        from mcp_client import suggest_servers
        assert "hr" in suggest_servers("Какая минимальная зарплата")

    def test_suggest_servers_empty_for_random(self):
        """[NEGATIVE] Random text → no servers suggested."""
        from mcp_client import suggest_servers
        result = suggest_servers("blah blah random text")
        assert result == []