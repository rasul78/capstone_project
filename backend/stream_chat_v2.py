"""
Sentinel AI — Streaming Chat with Agent Progress (Variant 9)

Server-Sent Events endpoint that yields step-by-step progress as the
agentic pipeline runs:

  event: agent_started  {agent: "Planner",   step: 1}
  event: agent_finished {agent: "Planner",   step: 1, latency_ms: 50,   summary: "..."}
  event: agent_started  {agent: "DocSearch", step: 2}
  event: agent_finished {agent: "DocSearch", step: 2, latency_ms: 200,  found: 5}
  event: agent_started  {agent: "Legal",     step: 3}
  event: agent_finished {agent: "Legal",     step: 3, latency_ms: 150,  mcp_tools: ["legal_rk.get_article"]}
  event: agent_started  {agent: "WebResearch", step: 4}
  event: agent_finished {agent: "WebResearch", step: 4, latency_ms: 0, skipped: true}
  event: agent_started  {agent: "Synthesis", step: 5}
  event: token          {chunk: "Краткий"}
  event: token          {chunk: " ответ:..."}
  event: agent_finished {agent: "Synthesis", step: 5, latency_ms: 800}
  event: agent_started  {agent: "Critic",    step: 6}
  event: agent_finished {agent: "Critic",    step: 6, ok: true}
  event: done           {answer: "...", sources: [...], mode: "rag_mcp", latency_ms: 1450}

Frontend listens via EventSource and updates a "thinking" indicator.

Endpoint: POST /api/kb/chat/stream
"""
from __future__ import annotations

import os
import json
import time
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, List

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from integrations.cache import cache_get, cache_set, cache_key
from database import db_save_chat

# Optional MCP
try:
    from mcp_integration import enrich_with_mcp
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    async def enrich_with_mcp(*args, **kw):
        return {"text": "", "tools_used": [], "results": []}

logger = logging.getLogger("sentinel.stream_chat")


# ════════════════════════════════════════════════════════════════════
# Request model
# ════════════════════════════════════════════════════════════════════

class StreamChatRequest(BaseModel):
    question:   str = Field(min_length=1, max_length=500)
    session_id: str = Field(default="default")
    use_web:    bool = Field(default=True)
    use_mcp:    bool = Field(default=True)
    use_critic: bool = Field(default=True)


# ════════════════════════════════════════════════════════════════════
# SSE helper — encode events
# ════════════════════════════════════════════════════════════════════

def _sse(event: str, data: dict) -> str:
    """Format one SSE event line."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ════════════════════════════════════════════════════════════════════
# Agent helpers — small wrappers around existing logic
# ════════════════════════════════════════════════════════════════════

AGENTS_PIPELINE = [
    ("Planner",     "🧭", "Decomposes the question and decides which agents to call"),
    ("DocSearch",   "📂", "Hybrid RAG search over the corporate knowledge base"),
    ("Legal",       "⚖️",  "Calls legal_rk MCP server (Kazakhstan law)"),
    ("WebResearch", "🌐", "DuckDuckGo fallback for fresh information"),
    ("Synthesis",   "🧠", "LLM combines all sources into one answer"),
    ("Critic",      "🔍", "Reviews the answer for hallucinations and consistency"),
]


# ════════════════════════════════════════════════════════════════════
# Planner — heuristic decision
# ════════════════════════════════════════════════════════════════════

def _planner_decide(query: str, use_web: bool, use_mcp: bool) -> Dict[str, Any]:
    """Decide which agents to invoke based on query content."""
    q = query.lower()
    decisions = {
        "doc_search":  True,                                  # always do RAG
        "legal":       use_mcp and any(kw in q for kw in
                       ["закон", "статья", "кодекс", "тк рк", "ук рк", "гк рк"]),
        "hr_mcp":      use_mcp and any(kw in q for kw in
                       ["мрп", "мзп", "зарплата", "отпуск", "пособие"]),
        "web":         use_web,
        "critic":      True,
    }
    return decisions


# ════════════════════════════════════════════════════════════════════
# Critic — simple heuristic checks
# ════════════════════════════════════════════════════════════════════

def _critic_review(answer: str, sources: List[str],
                   rag_chunks: List[Dict], mcp_used: List[str]) -> Dict[str, Any]:
    """Lightweight self-correction: looks for red flags in the answer."""
    issues = []

    # Check 1: answer mentions information not in sources?
    if "не знаю" in answer.lower() or "не нашёл" in answer.lower():
        if rag_chunks or mcp_used:
            issues.append("Hedge phrase despite having sources")

    # Check 2: numbers without source attribution
    import re
    numbers = re.findall(r"\b\d{4,}\b", answer)
    suspicious = [n for n in numbers if n not in ("2024", "2025", "2026", "2027")]
    if len(suspicious) >= 3 and not (rag_chunks or mcp_used):
        issues.append("Many specific numbers without supporting sources")

    # Check 3: lists sources that aren't actually used
    if "Источник:" in answer and not sources:
        issues.append("Mentions 'source' but no sources attached")

    ok = len(issues) == 0
    return {"ok": ok, "issues": issues, "score": 1.0 if ok else max(0.5, 1.0 - 0.2 * len(issues))}


# ════════════════════════════════════════════════════════════════════
# Main streaming generator
# ════════════════════════════════════════════════════════════════════

def build_stream_router(kb, orchestrator=None) -> APIRouter:
    router = APIRouter()

    @router.post("/api/kb/chat/stream", tags=["kb"])
    async def kb_chat_stream(req: StreamChatRequest):
        """Streams agent-by-agent progress as the chat pipeline runs."""

        async def gen() -> AsyncGenerator[str, None]:
            t_start = time.time()
            query = req.question.strip()[:500]
            session_id = (req.session_id or "default").strip()

            try:
                # ════ Step 0 — meta event with full plan ════
                yield _sse("plan", {
                    "agents": [{"name": n, "icon": i, "desc": d}
                               for n, i, d in AGENTS_PIPELINE]
                })

                # ════ Step 1 — Planner ════
                t0 = time.time()
                yield _sse("agent_started", {"agent": "Planner", "step": 1})
                decisions = _planner_decide(query, req.use_web, req.use_mcp)
                planned_agents = [k for k, v in decisions.items() if v]
                yield _sse("agent_finished", {
                    "agent": "Planner", "step": 1,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "summary": f"Will call: {', '.join(planned_agents)}",
                    "plan": decisions,
                })

                # ════ Step 2 — DocSearch ════
                t0 = time.time()
                yield _sse("agent_started", {"agent": "DocSearch", "step": 2})
                try:
                    rag_results = kb.search(query, top_k=10)
                except Exception as e:
                    logger.error("DocSearch error: %s", e)
                    rag_results = []

                # Hybrid scoring (semantic + keyword)
                rag_results = _hybrid_score(query, rag_results)
                good_chunks = [r for r in rag_results
                               if r.get("score_hybrid", r.get("score", 0)) >= 0.2][:5]

                yield _sse("agent_finished", {
                    "agent": "DocSearch", "step": 2,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "found": len(good_chunks),
                    "top_source": good_chunks[0].get("doc_name") if good_chunks else None,
                    "confidence": round(good_chunks[0].get("score_hybrid", 0) * 100, 1) if good_chunks else 0,
                })

                # ════ Step 3 — Legal / HR (MCP) ════
                t0 = time.time()
                yield _sse("agent_started", {"agent": "Legal", "step": 3})
                mcp_text = ""
                mcp_tools_used: List[str] = []

                if (decisions.get("legal") or decisions.get("hr_mcp")) and _MCP_AVAILABLE:
                    try:
                        mcp_data = await asyncio.wait_for(
                            enrich_with_mcp(query, max_tools=3, timeout=8.0),
                            timeout=10.0,
                        )
                        mcp_text = mcp_data.get("text", "")
                        mcp_tools_used = mcp_data.get("tools_used", [])
                    except Exception as e:
                        logger.warning("Legal/MCP error: %s", e)

                yield _sse("agent_finished", {
                    "agent": "Legal", "step": 3,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "skipped": not (decisions.get("legal") or decisions.get("hr_mcp")),
                    "mcp_tools": mcp_tools_used,
                })

                # ════ Step 4 — WebResearch ════
                t0 = time.time()
                yield _sse("agent_started", {"agent": "WebResearch", "step": 4})
                web_results = []

                if decisions.get("web") and orchestrator is not None:
                    try:
                        web_agent = getattr(orchestrator, "_web", None)
                        if web_agent is None:
                            from agents.web_agent import WebAgent
                            web_agent = WebAgent(timeout=5.0, max_results=3)
                        wr = await asyncio.wait_for(web_agent.run(query), timeout=6.0)
                        if wr.found:
                            web_results = wr.results[:3]
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.warning("Web error: %s", e)

                yield _sse("agent_finished", {
                    "agent": "WebResearch", "step": 4,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "skipped": not decisions.get("web"),
                    "found": len(web_results),
                })

                # ════ Step 5 — Synthesis ════
                t0 = time.time()
                yield _sse("agent_started", {"agent": "Synthesis", "step": 5})

                context, sources = _build_context(good_chunks, web_results, mcp_text)

                # If nothing at all → honest refusal
                if not good_chunks and not web_results and not mcp_text:
                    answer = _refusal_message(query)
                    used_provider = "no_llm"
                else:
                    answer, used_provider = await _call_llm_cascade(query, context)

                yield _sse("agent_finished", {
                    "agent": "Synthesis", "step": 5,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "provider": used_provider,
                    "answer_length": len(answer),
                })

                # ════ Step 6 — Critic ════
                t0 = time.time()
                yield _sse("agent_started", {"agent": "Critic", "step": 6})
                critic = _critic_review(answer, sources, good_chunks, mcp_tools_used)
                yield _sse("agent_finished", {
                    "agent": "Critic", "step": 6,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "ok": critic["ok"],
                    "issues": critic["issues"],
                    "score": critic["score"],
                    "skipped": not req.use_critic,
                })

                # ════ Done ════
                mode = "rag"
                if mcp_tools_used and web_results:
                    mode = "full_hybrid"
                elif mcp_tools_used:
                    mode = "rag_mcp"
                elif web_results:
                    mode = "hybrid"
                elif not good_chunks:
                    mode = "not_found"

                conf = round((good_chunks[0].get("score_hybrid", 0)
                              if good_chunks else 0) * 100, 1)
                total_ms = int((time.time() - t_start) * 1000)

                # Append footer with MCP tools
                if mcp_tools_used and "🔧" not in answer:
                    answer += "\n\n🔧 **MCP-инструменты:** " + ", ".join(mcp_tools_used)

                final_payload = {
                    "answer":         answer,
                    "found":          bool(good_chunks or mcp_tools_used or web_results),
                    "sources":        sources,
                    "mode":           mode,
                    "confidence":     conf,
                    "latency_ms":     total_ms,
                    "mcp_tools_used": mcp_tools_used,
                    "web_used":       bool(web_results),
                    "critic_passed":  critic["ok"],
                    "provider":       used_provider,
                }
                yield _sse("done", final_payload)

                # Persist
                try:
                    await db_save_chat(session_id, query, answer, sources, conf / 100, True)
                except Exception:
                    pass

            except Exception as e:
                logger.exception("[stream_chat] error: %s", e)
                yield _sse("error", {"message": str(e)})

        return StreamingResponse(gen(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    return router


# ════════════════════════════════════════════════════════════════════
# Helpers (mirror chat_fast_v2 logic to keep stream independent)
# ════════════════════════════════════════════════════════════════════

def _hybrid_score(query: str, chunks: List[Dict]) -> List[Dict]:
    import re
    q_words = set(re.findall(r"\w{3,}", query.lower()))
    for c in chunks:
        sem = c.get("score", 0)
        text = (c.get("chunk") or "").lower()
        c_words = set(re.findall(r"\w{3,}", text))
        kw = (len(q_words & c_words) / max(len(q_words), 1)) if q_words else 0
        c["score_hybrid"] = 0.6 * sem + 0.4 * kw
        c["score_keyword"] = kw
    return sorted(chunks, key=lambda x: -x["score_hybrid"])


def _build_context(rag_chunks, web_results, mcp_text):
    parts = []
    sources = []
    if rag_chunks:
        parts.append("📂 ВНУТРЕННИЕ ДОКУМЕНТЫ:")
        for i, ch in enumerate(rag_chunks, 1):
            name = ch.get("doc_name") or "Документ"
            parts.append(f"\n[{i}: {name}]\n{(ch.get('chunk') or '')[:1000]}")
            if name not in sources:
                sources.append(name)
    if web_results:
        parts.append("\n🌐 ВЕБ:")
        for r in web_results[:3]:
            parts.append(f"\n{r.get('title','')}: {r.get('snippet','')[:500]}")
            if r.get("url"):
                sources.append(r["url"])
    if mcp_text:
        parts.append("\n" + mcp_text)
    return "\n".join(parts), sources


def _refusal_message(query: str) -> str:
    return (
        f"**В базе знаний я не нашёл прямого ответа на вопрос «{query}».**\n\n"
        "Возможные причины:\n"
        "• Документ ещё не загружен в систему\n"
        "• Формулировка не совпала с терминологией документов\n\n"
        "Попробуй переформулировать или загрузить нужный документ."
    )


_LLM_SYSTEM = """Ты — Sentinel AI, корпоративный AI-помощник.
Отвечай умно, структурированно, на основе контекста. Используй markdown:
**Краткий ответ:** ...
**Подробнее:**
• ...
**Вывод:** ..."""


async def _call_llm_cascade(query: str, context: str):
    """Call Groq → Gemini → Anthropic in order."""
    groq_key   = os.getenv("GROQ_API_KEY",      "").strip().strip('"').strip("'")
    gemini_key = os.getenv("GEMINI_API_KEY",    "").strip().strip('"').strip("'")
    anth_key   = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")

    user_msg = f"КОНТЕКСТ:\n{context}\n\nВОПРОС: {query}\n\nДай умный markdown-ответ."
    timeout = httpx.Timeout(20.0, connect=6.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Groq
        if groq_key:
            try:
                r = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "max_tokens": 1200, "temperature": 0.3,
                        "messages": [
                            {"role": "system", "content": _LLM_SYSTEM},
                            {"role": "user",   "content": user_msg},
                        ],
                    },
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip(), "groq:llama-3.3-70b"
            except Exception:
                pass

        # Gemini
        if gemini_key:
            try:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"gemini-2.0-flash:generateContent?key={gemini_key}",
                    json={
                        "contents": [{"parts": [{"text": _LLM_SYSTEM + "\n\n" + user_msg}]}],
                        "generationConfig": {"maxOutputTokens": 1200, "temperature": 0.3},
                    },
                )
                if r.status_code == 200:
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip(), "gemini-2.0-flash"
            except Exception:
                pass

        # Anthropic
        if anth_key:
            try:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": anth_key, "anthropic-version": "2023-06-01"},
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 1200,
                        "system": _LLM_SYSTEM,
                        "messages": [{"role": "user", "content": user_msg}],
                    },
                )
                if r.status_code == 200:
                    return r.json()["content"][0]["text"].strip(), "claude-haiku-4-5"
            except Exception:
                pass

    return "⚠️ Не удалось получить ответ от LLM. Проверь GROQ_API_KEY в .env.", "no_llm"