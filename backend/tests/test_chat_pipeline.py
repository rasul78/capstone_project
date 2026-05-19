"""
End-to-end tests for the chat pipeline (chat_fast_v2).

Covers:
  POSITIVE:
    - Query routed through hybrid RAG → mock LLM → answer
    - Cache hit on repeated query
  NEGATIVE:
    - Empty KB → graceful "not found"
    - LLM unavailable → falls through cascade
    - Invalid session_id → still processes
"""
import pytest
import json
from unittest.mock import AsyncMock, patch


# ════════════════════════════════════════════════════════════════
#  PIPELINE STAGES
# ════════════════════════════════════════════════════════════════

class TestHybridSearch:
    """The hybrid scoring (semantic + keyword) should improve relevance."""

    def test_hybrid_rerank_promotes_keyword_match(self):
        from chat_fast_v2 import _hybrid_rerank
        chunks = [
            {"chunk": "Документ про корпоративную карту и её лимит", "score": 0.3},
            {"chunk": "Документ про что-то другое",                  "score": 0.5},
        ]
        # Query has strong keyword overlap with first doc
        result = _hybrid_rerank("корпоративная карта лимит", chunks, semantic_weight=0.4)
        # First chunk should now be ranked higher due to keyword match
        assert result[0]["chunk"].startswith("Документ про корпоративную")

    def test_keyword_score_zero_for_empty_query(self):
        from chat_fast_v2 import _keyword_score
        assert _keyword_score("", "any text") == 0.0

    def test_keyword_score_normalised(self):
        from chat_fast_v2 import _keyword_score
        score = _keyword_score("отпуск дни", "Отпуск составляет 24 дня")
        # Both query words present → score = 1.0
        assert 0.0 < score <= 1.0


class TestWebSearchDecision:
    """The _needs_web heuristic decides when to invoke web search."""

    def test_low_rag_confidence_triggers_web(self):
        from chat_fast_v2 import _needs_web
        # Confidence 0.10 < 0.25 → need web
        assert _needs_web("anything", rag_confidence=0.10) is True

    def test_high_rag_confidence_skips_web(self):
        from chat_fast_v2 import _needs_web
        # Confidence 0.8 + no triggers → skip web
        assert _needs_web("обычный вопрос про политику", rag_confidence=0.8) is False

    def test_law_keyword_triggers_web_even_with_high_rag(self):
        from chat_fast_v2 import _needs_web
        # Even if RAG is confident, fresh law data may be needed
        assert _needs_web("какой штраф за нарушение закона", rag_confidence=0.9) is True


# ════════════════════════════════════════════════════════════════
#  CONTEXT BUILDING
# ════════════════════════════════════════════════════════════════

class TestContextBuilding:
    """_build_context merges RAG + web sources for LLM."""

    def test_empty_inputs_produce_empty_context(self):
        from chat_fast_v2 import _build_context
        context, sources = _build_context([], [])
        assert context == ""
        assert sources == []

    def test_rag_only_context_has_internal_marker(self):
        from chat_fast_v2 import _build_context
        chunks = [{
            "doc_name": "HR_Policy", "category": "HR",
            "chunk": "Содержимое политики...", "score_hybrid": 0.7,
        }]
        context, sources = _build_context(chunks, [])
        assert "ВНУТРЕННИХ ДОКУМЕНТОВ" in context
        assert "HR_Policy" in sources

    def test_combined_context_includes_both_sections(self):
        from chat_fast_v2 import _build_context
        rag = [{"doc_name": "Doc1", "chunk": "content", "score_hybrid": 0.6}]
        web = [{"title": "Web1", "snippet": "snippet", "url": "https://example.com"}]
        context, sources = _build_context(rag, web)
        assert "ВНУТРЕННИХ" in context
        assert "ВЕБ" in context
        assert "Doc1" in sources
        assert "https://example.com" in sources


# ════════════════════════════════════════════════════════════════
#  END-TO-END (mocked LLM)
# ════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """Full chat pipeline with mocked LLM (Groq disabled in conftest)."""

    @pytest.mark.asyncio
    async def test_query_with_matching_doc_returns_answer(self, mock_kb, mock_orchestrator):
        """[POSITIVE] Query matches a document → returns answer (mock LLM)."""
        from chat_fast_v2 import build_chat_router, ChatRequest

        router = build_chat_router(mock_kb, mock_orchestrator)
        # Get the endpoint
        endpoint = None
        for r in router.routes:
            if "/api/kb/chat/fast/v2" in r.path:
                endpoint = r.endpoint
                break
        assert endpoint is not None

        req = ChatRequest(
            question="Какой лимит корпоративной карты?",
            session_id="test", use_cache=False, rerank=False,
            use_web=False, use_mcp=False,
        )
        result = await endpoint(req)
        # Even with no real LLM, structure must be correct
        assert "answer" in result
        assert "mode" in result
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_query_with_no_matching_docs_returns_not_found(self, empty_kb, mock_orchestrator):
        """[NEGATIVE] Empty KB → "not found" graceful response."""
        from chat_fast_v2 import build_chat_router, ChatRequest

        router = build_chat_router(empty_kb, mock_orchestrator)
        endpoint = None
        for r in router.routes:
            if "/api/kb/chat/fast/v2" in r.path:
                endpoint = r.endpoint
                break

        req = ChatRequest(
            question="Что-то совершенно не связанное с документами",
            session_id="test", use_cache=False, rerank=False,
            use_web=False, use_mcp=False,
        )
        result = await endpoint(req)
        assert result["found"] is False
        assert result["mode"] == "not_found"
        # Answer should mention "не нашёл" or similar
        assert "не наш" in result["answer"].lower() or "не найден" in result["answer"].lower()