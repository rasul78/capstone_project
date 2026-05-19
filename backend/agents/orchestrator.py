"""
Sentinel AI — Agent Orchestrator
Координирует работу ResearchAgent → WebAgent → SynthesisAgent.
Включает: tracing, metrics, rate limiting, error handling.
"""

import time
import logging
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field
from collections import deque
import threading

from agents.research_agent import ResearchAgent, ResearchResult
from agents.web_agent import WebAgent, WebResult
from agents.synthesis_agent import SynthesisAgent, SynthesisResult

import os
logger = logging.getLogger("sentinel.orchestrator")

# ── LLM Utils (Ollama / Anthropic) ────────────────────────────────────────

class LLMUtils:
    """Утилиты для GenAI: query rewriting, auto-summary, image captioning."""

    OLLAMA_URL = "http://localhost:11434/api/generate"

    def __init__(self):
        self.ollama_model = None
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._detect_ollama()

    def _detect_ollama(self):
        try:
            import urllib.request, json
            r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            d = json.loads(r.read())
            models = [m["name"] for m in d.get("models", [])]
            preferred = ["llama3", "mistral", "gemma3", "phi3", "llama2"]
            for p in preferred:
                m = next((x for x in models if x.startswith(p)), None)
                if m:
                    self.ollama_model = m
                    break
            if not self.ollama_model and models:
                self.ollama_model = models[0]
            if self.ollama_model:
                logger.info("[LLMUtils] Ollama: %s", self.ollama_model)
        except Exception:
            pass

    def call_llm(self, prompt, max_tokens=512, temperature=0.3):
        if self.ollama_model:
            try:
                import urllib.request, json
                payload = json.dumps({
                    "model": self.ollama_model, "prompt": prompt, "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": temperature},
                }).encode()
                req = urllib.request.Request(self.OLLAMA_URL, data=payload,
                    headers={"Content-Type": "application/json"}, method="POST")
                resp = urllib.request.urlopen(req, timeout=15)
                result = json.loads(resp.read()).get("response", "").strip()
                if result:
                    return result
            except Exception as e:
                logger.info("[LLMUtils] Ollama unavailable: %s", type(e).__name__)
                self.ollama_model = None  # помечаем недоступной

        if self.api_key:
            try:
                import urllib.request, json
                payload = json.dumps({
                    "model": "claude-sonnet-4-20250514", "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }).encode()
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages", data=payload,
                    headers={"x-api-key": self.api_key,
                             "anthropic-version": "2023-06-01",
                             "Content-Type": "application/json"}, method="POST")
                resp = urllib.request.urlopen(req, timeout=15)
                data = json.loads(resp.read())
                return data["content"][0]["text"].strip()
            except Exception as e:
                logger.warning("[LLMUtils] Anthropic error: %s", e)
        return ""

    def rewrite_query(self, query):
        """Query Rewriting — улучшает запрос перед RAG поиском."""
        if len(query.split()) <= 2:
            return query
        prompt = (
            "Улучши поисковый запрос для корпоративной базы знаний. "
            "Исходный запрос: " + query + ". "
            "Перефразируй точнее, добавь синонимы если нужно. "
            "Верни ТОЛЬКО улучшенный запрос без объяснений."
        )
        result = self.call_llm(prompt, max_tokens=80, temperature=0.2)
        if result and 5 < len(result) < 300:
            logger.info("[LLMUtils] Query: %r -> %r", query, result)
            return result
        return query

    def summarize_document(self, text, name=""):
        """Auto-Summary — краткое содержание при загрузке документа."""
        preview = text[:2000]
        prompt = (
            "Проанализируй документ и верни JSON: "
            "{summary: краткое содержание 2-3 предложения, "
            "tags: [3-5 тем], "
            "category: одна из [Безопасность, HR, Финансы, IT, Этика, Общее]}. "
            "Документ '" + name + "': " + preview + ". "
            "Верни ТОЛЬКО JSON без markdown."
        )
        result = self.call_llm(prompt, max_tokens=250, temperature=0.1)
        try:
            import json as js, re
            m = re.search(r'\{[^{}]+\}', result, re.DOTALL)
            if m:
                return js.loads(m.group())
        except Exception:
            pass
        return {"summary": "", "tags": [], "category": "Общее"}

    def generate_caption(self, prediction, confidence, top5):
        """Image Captioning — LLM объясняет результат классификации."""
        top3 = ", ".join(p["class"] + " (" + str(round(p["confidence"], 1)) + "%)" for p in top5[:3])
        prompt = (
            "Нейросеть определила объект на фото: " + prediction +
            " с уверенностью " + str(round(confidence, 1)) + "%. "
            "Топ-3 варианта: " + top3 + ". "
            "Напиши 1-2 предложения по-русски: что видит модель и насколько точен результат."
        )
        result = self.call_llm(prompt, max_tokens=120, temperature=0.4)
        return result or ("Объект определён как " + prediction + " (" + str(round(confidence, 1)) + "% уверенность).")


# ── Observability / Tracing ────────────────────────────────────────────────

@dataclass
class AgentTrace:
    """Трейс одного запроса через всю pipeline."""
    session_id: str
    query: str
    started_at: float = field(default_factory=time.time)

    # Agent results
    research:  Optional[Dict] = None
    web:       Optional[Dict] = None
    synthesis: Optional[Dict] = None

    # Metrics
    total_latency_ms: float = 0.0
    rag_latency_ms:   float = 0.0
    web_latency_ms:   float = 0.0
    synth_latency_ms: float = 0.0
    success: bool = False
    error: Optional[str] = None


class MetricsCollector:
    """In-memory метрики системы (без внешних зависимостей)."""

    def __init__(self, window: int = 100):
        self._lock = threading.Lock()
        self._traces: deque = deque(maxlen=window)
        self.total_requests = 0
        self.rag_hits = 0
        self.web_hits = 0
        self.hybrid_hits = 0
        self.errors = 0
        self._latencies: deque = deque(maxlen=window)

    def record(self, trace: AgentTrace):
        with self._lock:
            self.total_requests += 1
            mode = (trace.synthesis or {}).get("mode", "none")
            if mode == "rag":     self.rag_hits += 1
            if mode == "web":     self.web_hits += 1
            if mode == "hybrid":  self.hybrid_hits += 1
            if trace.error:       self.errors += 1
            self._latencies.append(trace.total_latency_ms)
            self._traces.append(trace)

    def summary(self) -> Dict:
        with self._lock:
            lats = list(self._latencies)
            n = self.total_requests or 1
            return {
                "total_requests":   self.total_requests,
                "rag_hits":         self.rag_hits,
                "web_hits":         self.web_hits,
                "hybrid_hits":      self.hybrid_hits,
                "not_found":        self.total_requests - self.rag_hits - self.web_hits - self.hybrid_hits,
                "errors":           self.errors,
                "success_rate_pct": round((1 - self.errors / n) * 100, 1),
                "avg_latency_ms":   round(sum(lats) / len(lats), 1) if lats else 0,
                "p95_latency_ms":   round(sorted(lats)[int(len(lats) * 0.95)] if lats else 0, 1),
            }

    def recent_traces(self, limit: int = 20):
        with self._lock:
            return list(self._traces)[-limit:]


# ── Rate Limiter ───────────────────────────────────────────────────────────

class RateLimiter:
    """Простой in-memory rate limiter (sliding window)."""

    def __init__(self, max_req: int = 30, window_sec: float = 60.0):
        self.max_req = max_req
        self.window  = window_sec
        self._buckets: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = deque()
            q = self._buckets[key]
            while q and q[0] < now - self.window:
                q.popleft()
            if len(q) >= self.max_req:
                return False
            q.append(now)
            return True


# ── Orchestrator ────────────────────────────────────────────────────────────

class AgentOrchestrator:
    """
    Главный координатор агентов.

    Pipeline:
      query → ResearchAgent (RAG)
            → [если слабый] WebAgent (fallback)
            → SynthesisAgent (финальный ответ)
    """

    def __init__(self, kb, web_fallback_threshold: float = 0.35):
        self.research  = ResearchAgent(kb)
        self.web       = WebAgent()
        self.synthesis = SynthesisAgent()
        self.llm       = LLMUtils()
        self.metrics   = MetricsCollector()
        self.rate_limiter = RateLimiter(max_req=60, window_sec=60)
        self.web_threshold = web_fallback_threshold
        logger.info("[Orchestrator] All agents initialized")

    async def process(self, query: str, session_id: str = "default") -> Dict:
        """
        Основной метод: запускает pipeline и возвращает финальный ответ.
        """
        trace = AgentTrace(session_id=session_id, query=query)
        t0 = time.time()

        # ── Rate limiting ──────────────────────────────────────────────
        if not self.rate_limiter.is_allowed(session_id):
            logger.warning(f"[Orchestrator] Rate limit exceeded for session={session_id}")
            return {
                "answer": "Слишком много запросов. Пожалуйста, подождите.",
                "sources": [], "confidence": 0, "found": False,
                "mode": "rate_limited", "flags": ["rate_limited"],
            }

        # ── Input validation ────────────────────────────────────────────
        query = query.strip()[:500]
        if not query:
            return {
                "answer": "Пустой запрос.",
                "sources": [], "confidence": 0, "found": False,
                "mode": "none", "flags": ["empty_query"],
            }

        try:
            # ── Step 0: Query Rewriting (GenAI) ─────────────────────────
            original_query = query
            rewritten_query = self.llm.rewrite_query(query)
            if rewritten_query != query:
                logger.info(f"[Orchestrator] Query rewritten: {query!r} → {rewritten_query!r}")
                query = rewritten_query

            # ── Step 1: Research Agent (RAG) ────────────────────────────
            logger.info(f"[Orchestrator] Step 1: ResearchAgent for session={session_id}")
            rag_result: ResearchResult = self.research.run(query)
            trace.research = {
                "found": rag_result.found,
                "confidence": rag_result.confidence,
                "chunk_count": len(rag_result.chunks),
                "sources": rag_result.sources,
                "latency_ms": rag_result.latency_ms,
            }
            trace.rag_latency_ms = rag_result.latency_ms

            # ── Step 2: Web Agent (только если RAG слаб) ───────────────
            web_result: Optional[WebResult] = None
            needs_web = (
                not rag_result.found
                or rag_result.confidence < self.web_threshold
            )

            if needs_web:
                logger.info(f"[Orchestrator] Step 2: WebAgent fallback (rag_conf={rag_result.confidence:.2f})")
                web_result = await self.web.run(query)
                trace.web = {
                    "found": web_result.found,
                    "result_count": len(web_result.results),
                    "source": web_result.source,
                    "latency_ms": web_result.latency_ms,
                }
                trace.web_latency_ms = web_result.latency_ms
            else:
                logger.info(f"[Orchestrator] Step 2: WebAgent skipped (rag strong, conf={rag_result.confidence:.2f})")

            # ── Step 3: Synthesis Agent ─────────────────────────────────
            logger.info(f"[Orchestrator] Step 3: SynthesisAgent")
            synth: SynthesisResult = self.synthesis.run(query, rag_result, web_result)
            trace.synthesis = {
                "mode": synth.mode,
                "confidence": synth.confidence,
                "flags": synth.flags,
                "rag_used": synth.rag_used,
                "web_used": synth.web_used,
                "latency_ms": synth.latency_ms,
            }
            trace.synth_latency_ms = synth.latency_ms
            trace.success = True

            # ── Record metrics ──────────────────────────────────────────
            trace.total_latency_ms = (time.time() - t0) * 1000
            self.metrics.record(trace)

            logger.info(f"[Orchestrator] Done: mode={synth.mode}, "
                        f"conf={synth.confidence}, total={trace.total_latency_ms:.0f}ms")

            return {
                "answer":     synth.answer,
                "sources":    synth.sources,
                "confidence": synth.confidence,
                "found":      synth.found,
                "mode":       synth.mode,
                "flags":      synth.flags,
                "original_query":  original_query,
                "rewritten_query": rewritten_query if rewritten_query != original_query else None,
                "trace": {
                    "rag_latency_ms":   trace.rag_latency_ms,
                    "web_latency_ms":   trace.web_latency_ms,
                    "synth_latency_ms": trace.synth_latency_ms,
                    "total_latency_ms": trace.total_latency_ms,
                    "rag_conf":         rag_result.confidence,
                    "web_used":         web_result is not None,
                },
            }

        except Exception as e:
            trace.error = str(e)
            trace.total_latency_ms = (time.time() - t0) * 1000
            self.metrics.record(trace)
            logger.error(f"[Orchestrator] Pipeline error: {e}", exc_info=True)
            return {
                "answer": f"Системная ошибка: {e}",
                "sources": [], "confidence": 0, "found": False,
                "mode": "error", "flags": ["pipeline_error"],
            }