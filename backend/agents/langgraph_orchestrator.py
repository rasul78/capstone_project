"""
Sentinel AI — LangGraph Orchestrator
Граф агентов без зависимости от langchain-core.

Установка: pip install langgraph mcp
(НЕ нужен langchain-core / langsmith)

Граф состояний:
  START → rewrite_query → search_kb → [если слабо: search_web] → synthesize → END
"""

import os
import time
import logging
import collections
import threading
from typing import Dict, List, Optional, Any

logger = logging.getLogger("sentinel.langgraph")

# ── Проверка установки LangGraph ───────────────────────────────────────────
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_OK = True
    logger.info("[LangGraph] ✅ langgraph установлен")
except ImportError:
    LANGGRAPH_OK = False
    logger.warning("[LangGraph] ⚠️ langgraph не установлен — используем fallback оркестратор")
    logger.warning("[LangGraph] Установи: pip install langgraph mcp")

from agents.research_agent import ResearchAgent, ResearchResult
from agents.web_agent import WebAgent, WebResult
from agents.synthesis_agent import SynthesisAgent
from mcp_server import SentinelMCPServer

# ── Состояние графа (простой dict, без TypedDict) ──────────────────────────

def initial_state(query: str, session_id: str) -> Dict:
    return {
        "query":           query,
        "session_id":      session_id,
        "rewritten_query": None,
        "rag_result":      None,
        "web_result":      None,
        "answer":          None,
        "sources":         [],
        "confidence":      0.0,
        "found":           False,
        "mode":            "none",
        "flags":           [],
        "latencies":       {},
        "error":           None,
    }


# ── Узлы графа ─────────────────────────────────────────────────────────────

class SentinelNodes:

    RAG_THRESHOLD = 0.28

    def __init__(self, kb, mcp_server: SentinelMCPServer):
        self.research  = ResearchAgent(kb)
        self.web       = WebAgent()
        self.synthesis = SynthesisAgent()
        self.mcp       = mcp_server

    async def node_rewrite_query(self, state: Dict) -> Dict:
        """Узел 1: LLM улучшает запрос перед поиском."""
        t0    = time.time()
        query = state["query"]
        logger.info("[LangGraph→rewrite] query=%r", query)

        rewritten = query
        try:
            if len(query.split()) > 2:
                answer = self.synthesis._call_ollama(
                    "Улучши поисковый запрос для корпоративной базы знаний. "
                    "Запрос: " + query + ". "
                    "Верни ТОЛЬКО улучшенный запрос, без объяснений.",
                    ""
                )
                if answer and 5 < len(answer.strip()) < 250:
                    rewritten = answer.strip()
                    logger.info("[LangGraph→rewrite] %r → %r", query, rewritten)
        except Exception as e:
            logger.debug("[LangGraph→rewrite] LLM недоступна: %s", e)

        state["rewritten_query"]  = rewritten
        state["latencies"]["rewrite"] = round((time.time() - t0) * 1000, 1)
        return state

    async def node_search_kb(self, state: Dict) -> Dict:
        """Узел 2: Поиск в базе знаний через MCP инструмент."""
        t0    = time.time()
        query = state.get("rewritten_query") or state["query"]
        logger.info("[LangGraph→search_kb] query=%r", query)

        # Вызов через MCP протокол
        mcp_result = await self.mcp.call_tool(
            "search_knowledge_base", {"query": query, "top_k": 6}
        )

        chunks  = mcp_result.get("results", [])
        conf    = max((c.get("score", 0) for c in chunks), default=0.0)
        sources = list(dict.fromkeys(
            c["source"] for c in chunks if c.get("source")
        ))

        state["rag_result"] = {
            "found":      mcp_result.get("found", False),
            "chunks":     chunks,
            "confidence": conf,
            "sources":    sources,
            "mcp_used":   True,
        }
        state["latencies"]["rag"] = round((time.time() - t0) * 1000, 1)
        logger.info("[LangGraph→search_kb] conf=%.2f, chunks=%d", conf, len(chunks))
        return state

    async def node_search_web(self, state: Dict) -> Dict:
        """Узел 3: Веб-поиск через MCP (fallback)."""
        t0    = time.time()
        query = state.get("rewritten_query") or state["query"]
        logger.info("[LangGraph→search_web] query=%r", query)

        mcp_result = await self.mcp.call_tool("search_web", {"query": query})

        state["web_result"] = {
            "found":    mcp_result.get("found", False),
            "results":  mcp_result.get("results", []),
            "source":   mcp_result.get("source", "none"),
            "mcp_used": True,
        }
        state["latencies"]["web"] = round((time.time() - t0) * 1000, 1)
        logger.info("[LangGraph→search_web] found=%s", mcp_result.get("found"))
        return state

    async def node_synthesize(self, state: Dict) -> Dict:
        """Узел 4: Генерация ответа через LLM (Ollama/Anthropic)."""
        t0    = time.time()
        query = state.get("rewritten_query") or state["query"]
        logger.info("[LangGraph→synthesize]")

        rag_result = _to_research_result(state.get("rag_result") or {})
        web_dict   = state.get("web_result")
        web_result = _to_web_result(web_dict) if web_dict else None

        synth = self.synthesis.run(query, rag_result, web_result)

        state["answer"]     = synth.answer
        state["sources"]    = synth.sources
        state["confidence"] = synth.confidence
        state["found"]      = synth.found
        state["mode"]       = synth.mode
        state["flags"]      = synth.flags + ["langgraph", "mcp"]
        state["latencies"]["synthesis"] = round((time.time() - t0) * 1000, 1)
        logger.info("[LangGraph→synthesize] mode=%s, conf=%.1f", synth.mode, synth.confidence)
        return state

    def route_after_kb(self, state: Dict) -> str:
        """Условное ветвление: нужен веб-поиск?"""
        conf = state.get("rag_result", {}).get("confidence", 0.0)
        if conf < self.RAG_THRESHOLD:
            logger.info("[LangGraph→route] conf=%.2f < %.2f → web", conf, self.RAG_THRESHOLD)
            return "search_web"
        logger.info("[LangGraph→route] conf=%.2f → synthesize (skip web)", conf)
        return "synthesize"


# ── Строим граф ────────────────────────────────────────────────────────────

def build_langgraph(kb, mcp_server: SentinelMCPServer):
    """Строит и компилирует LangGraph граф."""
    if not LANGGRAPH_OK:
        return None

    nodes = SentinelNodes(kb, mcp_server)

    from typing import TypedDict

    class State(TypedDict, total=False):
        query:           str
        session_id:      str
        rewritten_query: str
        rag_result:      dict
        web_result:      dict
        answer:          str
        sources:         list
        confidence:      float
        found:           bool
        mode:            str
        flags:           list
        latencies:       dict
        error:           str

    g = StateGraph(State)

    g.add_node("rewrite_query", nodes.node_rewrite_query)
    g.add_node("search_kb",     nodes.node_search_kb)
    g.add_node("search_web",    nodes.node_search_web)
    g.add_node("synthesize",    nodes.node_synthesize)

    g.set_entry_point("rewrite_query")
    g.add_edge("rewrite_query", "search_kb")
    g.add_conditional_edges(
        "search_kb",
        nodes.route_after_kb,
        {"search_web": "search_web", "synthesize": "synthesize"},
    )
    g.add_edge("search_web", "synthesize")
    g.add_edge("synthesize",  END)

    compiled = g.compile()
    logger.info("[LangGraph] Граф скомпилирован ✅")
    return compiled, nodes


# ── LangGraph Orchestrator ─────────────────────────────────────────────────

class LangGraphOrchestrator:
    """
    Оркестратор на базе LangGraph.
    Если LangGraph не установлен — автоматически fallback на старый оркестратор.
    """

    def __init__(self, kb, web_fallback_threshold: float = 0.28):
        self.mcp_server  = SentinelMCPServer(kb, WebAgent())
        self.synthesis   = SynthesisAgent()
        self._metrics    = _SimpleMetrics()
        self._limiter    = _RateLimiter()
        self._use_graph  = False
        self._graph      = None
        self._nodes      = None

        if LANGGRAPH_OK:
            try:
                result = build_langgraph(kb, self.mcp_server)
                if result:
                    self._graph, self._nodes = result
                    self._use_graph = True
            except Exception as e:
                logger.warning("[LangGraph] Граф не скомпилирован: %s — fallback", e)

        # Fallback агенты
        self._research = ResearchAgent(kb)
        self._web      = WebAgent()

        mode = "LangGraph граф" if self._use_graph else "Fallback цепочка"
        logger.info("[Orchestrator] Режим: %s, MCP инструментов: %d", mode, len(self.mcp_server.list_tools()))

    async def process(self, query: str, session_id: str = "default") -> Dict:

        if not self._limiter.is_allowed(session_id):
            return {"answer": "Слишком много запросов.", "sources": [], "confidence": 0, "found": False, "mode": "rate_limited", "flags": ["rate_limited"]}

        query = query.strip()[:500]
        if not query:
            return {"answer": "Пустой запрос.", "sources": [], "confidence": 0, "found": False, "mode": "none", "flags": []}

        if self._use_graph:
            return await self._process_langgraph(query, session_id)
        else:
            return await self._process_fallback(query, session_id)

    async def _process_langgraph(self, query: str, session_id: str) -> Dict:
        """Обработка через LangGraph граф."""
        t0    = time.time()
        state = initial_state(query, session_id)
        try:
            final = await self._graph.ainvoke(state)
            total = (time.time() - t0) * 1000
            self._metrics.record(final.get("mode", "none"), total)
            return {
                "answer":          final.get("answer", ""),
                "sources":         final.get("sources", []),
                "confidence":      final.get("confidence", 0.0),
                "found":           final.get("found", False),
                "mode":            final.get("mode", "none"),
                "flags":           final.get("flags", []),
                "original_query":  query,
                "rewritten_query": final.get("rewritten_query") if final.get("rewritten_query") != query else None,
                "trace": {
                    "total_latency_ms": round(total, 1),
                    "latencies":        final.get("latencies", {}),
                    "langgraph":        True,
                    "mcp_used":         True,
                },
            }
        except Exception as e:
            logger.error("[LangGraph] Ошибка графа: %s", e, exc_info=True)
            return await self._process_fallback(query, session_id)

    async def _process_fallback(self, query: str, session_id: str) -> Dict:
        """Fallback: простая цепочка агентов."""
        t0         = time.time()
        rag_result = self._research.run(query)
        web_result = None
        if not rag_result.found or rag_result.confidence < 0.28:
            web_result = await self._web.run(query)
        synth = self.synthesis.run(query, rag_result, web_result)
        total = (time.time() - t0) * 1000
        self._metrics.record(synth.mode, total)
        return {
            "answer":     synth.answer,
            "sources":    synth.sources,
            "confidence": synth.confidence,
            "found":      synth.found,
            "mode":       synth.mode,
            "flags":      synth.flags,
            "trace": {"total_latency_ms": round(total, 1), "langgraph": False},
        }

    def get_graph_schema(self) -> Dict:
        return {
            "framework":    "LangGraph" if self._use_graph else "Fallback",
            "langgraph_ok": self._use_graph,
            "nodes": [
                {"id": "rewrite_query", "type": "genai", "description": "LLM улучшает запрос"},
                {"id": "search_kb",     "type": "mcp",   "description": "MCP: поиск в базе знаний"},
                {"id": "search_web",    "type": "mcp",   "description": "MCP: веб-поиск (fallback)"},
                {"id": "synthesize",    "type": "genai", "description": "LLM генерирует ответ (Ollama)"},
            ],
            "edges": [
                {"from": "rewrite_query", "to": "search_kb",  "type": "always"},
                {"from": "search_kb",     "to": "search_web", "type": "conditional", "condition": "confidence < 0.28"},
                {"from": "search_kb",     "to": "synthesize", "type": "conditional", "condition": "confidence >= 0.28"},
                {"from": "search_web",    "to": "synthesize", "type": "always"},
                {"from": "synthesize",    "to": "END",         "type": "always"},
            ],
            "mcp_tools":   [t["name"] for t in self.mcp_server.list_tools()],
        }

    def summary(self) -> Dict:
        return self._metrics.summary()

    def recent_traces(self, limit=20):
        return []

    @property
    def metrics(self):
        return self._metrics


# ── Helpers ────────────────────────────────────────────────────────────────

def _to_research_result(d: Dict) -> ResearchResult:
    chunks = [
        {"chunk": c.get("content", c.get("chunk", "")),
         "source": c.get("source", ""),
         "score":  c.get("score", 0),
         "doc_id": c.get("doc_id")}
        for c in d.get("chunks", [])
    ]
    return ResearchResult(
        found=d.get("found", False), chunks=chunks,
        confidence=d.get("confidence", 0.0),
        sources=d.get("sources", []), latency_ms=0.0,
    )

def _to_web_result(d: Dict) -> WebResult:
    return WebResult(
        found=d.get("found", False), results=d.get("results", []),
        source=d.get("source", "none"), latency_ms=0.0,
    )


class _SimpleMetrics:
    def __init__(self):
        self.total = 0; self.modes = {}; self.latencies = []
    def record(self, mode, lat):
        self.total += 1
        self.modes[mode] = self.modes.get(mode, 0) + 1
        self.latencies.append(lat)
        if len(self.latencies) > 100: self.latencies.pop(0)
    def summary(self):
        lats = self.latencies
        return {
            "total_requests": self.total,
            "modes":          self.modes,
            "avg_latency_ms": round(sum(lats)/len(lats), 1) if lats else 0,
            "rag_hits":       self.modes.get("rag", 0),
            "web_hits":       self.modes.get("web", 0),
            "hybrid_hits":    self.modes.get("hybrid", 0),
            "errors":         0,
            "success_rate_pct": 100.0,
            "p95_latency_ms": round(sorted(lats)[int(len(lats)*0.95)] if lats else 0, 1),
        }
    def recent_traces(self, limit=20): return []

class _RateLimiter:
    def __init__(self, max_req=60, window=60):
        self.max_req = max_req; self.window = window
        self._b = collections.defaultdict(collections.deque)
        self._l = threading.Lock()
    def is_allowed(self, key):
        now = time.time()
        with self._l:
            q = self._b[key]
            while q and q[0] < now - self.window: q.popleft()
            if len(q) >= self.max_req: return False
            q.append(now); return True