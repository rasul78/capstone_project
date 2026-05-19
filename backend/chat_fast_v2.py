"""
Sentinel AI — Smart Chat v3 (Hybrid RAG + Web + Reasoning)

Что нового vs v2:
  • Не строгий RAG — модель ДУМАЕТ как ChatGPT, использует документы как основу,
    дополняет общими знаниями (право РК, практики), при необходимости делает
    веб-поиск (актуальные данные).
  • Multi-stage pipeline:
        1) Hybrid search (semantic + keyword)
        2) Reranker для точности
        3) Решение: достаточно ли документов? нужен ли web?
        4) Web search если нужно (DuckDuckGo через WebAgent)
        5) LLM с reasoning-промптом — структурированный markdown-ответ
  • Если RAG и Web ничего не дали — честное «не нашёл», а не галлюцинации.

Эндпоинт: POST /api/kb/chat/fast/v2
Диагностика: GET  /api/kb/chat/debug?q=...
"""
import os, re, time, logging, asyncio
from typing import Optional, List, Dict, Tuple

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from integrations.cache import cache_get, cache_set, cache_key
from integrations.reranker import rerank_chunks
from database import db_save_chat

# ── НОВОЕ: MCP integration ─────────────────────────────────────────
try:
    from mcp_integration import enrich_with_mcp
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    async def enrich_with_mcp(*args, **kwargs):
        return {"text": "", "tools_used": [], "results": []}

logger = logging.getLogger("sentinel.chat_v3")

# ════════════════════════════════════════════════════════════════════
# СИСТЕМНЫЙ ПРОМПТ — ChatGPT-style + использование контекста
# ════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Ты — Sentinel AI, умный корпоративный AI-помощник для сотрудников компании.

╔══════ ТВОЯ РОЛЬ ══════╗
Ты как ChatGPT, но специализируешься на внутренних документах компании (политики, процедуры, регламенты) и законодательстве Республики Казахстан. Помогаешь сотрудникам разобраться в вопросах работы, права, процедур.

╔══════ КАК ОТВЕЧАТЬ ══════╗
1. **ДУМАЙ как эксперт.** Не пересказывай контекст слово в слово. Анализируй, объясняй, давай примеры. Контекст — это исходные данные, а не готовый ответ.

2. **Используй ИЕРАРХИЮ источников:**
   • ПЕРВОЕ — внутренние документы из контекста (политики, регламенты)
   • ВТОРОЕ — общие знания о праве РК и лучших практиках (можно дополнить)
   • ТРЕТЬЕ — результаты веб-поиска (если они есть в контексте)

3. **Если контекст НЕ связан с вопросом** — честно скажи: «В предоставленных документах прямого ответа нет», и:
   • ИЛИ дай общий ответ из своих знаний (с пометкой «общая информация»)
   • ИЛИ предложи уточнить вопрос / загрузить нужный документ
   • ❌ НЕ выдумывай факты, цифры, названия документов.

4. **СТРУКТУРА ОТВЕТА (markdown):**
   ```
   **Краткий ответ:** [1-2 предложения сути]

   **Подробнее:**
   • Пункт 1 — конкретика, цифры, ссылки на документы
   • Пункт 2 — ...
   • Пункт 3 — ...

   **Дополнительно** (если уместно):
   [Контекст из права РК / практик / связанные нюансы]

   **Вывод:** [1 предложение]
   ```

5. **ЯЗЫК:** Русский. Чёткий, профессиональный, дружелюбный. Без канцелярита.

6. **ФОРМАТ:** Используй markdown — **жирный**, маркеры `•`, нумерованные списки, цитаты `> ...`. Это красиво отрендерится на фронте.

7. **НЕ начинай** с фраз «Согласно контексту…», «На основе данных…», «Из предоставленной информации следует…». Сразу к сути.

8. **НЕ говори «как искусственный интеллект…»** — отвечай как живой эксперт.

╔══════ ПРИМЕР ══════╗
Вопрос: «Какой лимит корпоративной карты?»
ПЛОХО: «Согласно контексту, лимит составляет 500 000 тенге.»
ХОРОШО:
**Краткий ответ:** Стандартный лимит корпоративной карты — **500 000 ₸** в месяц.

**Подробнее:**
• Лимит можно поднять до 1 500 000 ₸ через заявку руководителю отдела
• Разовый платёж — не более 200 000 ₸ без согласования
• Снятие наличных не предусмотрено

**Вывод:** Для повышения лимита оформи заявку через HR-портал заранее."""


# ════════════════════════════════════════════════════════════════════


class ChatRequest(BaseModel):
    question:   str = Field(min_length=1, max_length=500)
    session_id: str = Field(default="default")
    use_cache:  bool = Field(default=True)
    rerank:     bool = Field(default=True)
    use_web:    bool = Field(default=True)
    use_mcp:    bool = Field(default=True)   # вызывать MCP-серверы


# ─── Hybrid search: semantic + keyword ─────────────────────────────

def _keyword_score(query: str, chunk_text: str) -> float:
    """BM25-подобный keyword scoring без внешних либ."""
    q_words = set(re.findall(r"\w{3,}", query.lower()))
    if not q_words:
        return 0.0
    c_words = set(re.findall(r"\w{3,}", chunk_text.lower()))
    common = q_words & c_words
    return len(common) / len(q_words)


def _hybrid_rerank(query: str, chunks: List[Dict],
                   semantic_weight: float = 0.6) -> List[Dict]:
    """Объединяет semantic + keyword score."""
    if not chunks:
        return chunks
    for c in chunks:
        sem = c.get("score", 0)
        kw = _keyword_score(query, c.get("chunk") or "")
        c["score_hybrid"] = semantic_weight * sem + (1 - semantic_weight) * kw
        c["score_keyword"] = kw
    return sorted(chunks, key=lambda x: -x["score_hybrid"])


# ─── Нужен ли web? ─────────────────────────────────────────────────

WEB_TRIGGER_WORDS = [
    "закон", "статья", "кодекс", "ук рк", "гк рк", "трудовой кодекс",
    "налог", "штраф", "санкци", "регистрац", "лицензи",
    "актуальн", "сегодня", "сейчас", "новост",
    "курс", "ставка", "минимальн", "мрп", "мзп",
]


def _needs_web(query: str, rag_confidence: float) -> bool:
    if rag_confidence < 0.25:
        return True
    q = query.lower()
    return any(w in q for w in WEB_TRIGGER_WORDS)


# ─── LLM calls ─────────────────────────────────────────────────────

def _build_user_message(query: str, context: str) -> str:
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
КОНТЕКСТ ИЗ ВНУТРЕННИХ ДОКУМЕНТОВ И ВЕБА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ВОПРОС СОТРУДНИКА: {query}

Дай умный, структурированный ответ. Если в контексте нет прямого ответа — используй общие знания о праве РК и корпоративных практиках, но честно укажи что это общая информация. Не выдумывай конкретные цифры и названия документов."""


async def _call_groq(client: httpx.AsyncClient, query: str, context: str,
                     key: str) -> Optional[str]:
    if not key:
        return None
    try:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens": 1500,
                "temperature": 0.3,
                "top_p": 0.9,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": _build_user_message(query, context)},
                ],
            },
        )
        if r.status_code != 200:
            logger.warning("[Groq] HTTP %s: %s", r.status_code, r.text[:160])
            return None
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("[Groq] error: %s", e)
        return None


async def _call_gemini(client: httpx.AsyncClient, query: str, context: str,
                       key: str) -> Optional[str]:
    if not key:
        return None
    try:
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text":
                    f"{SYSTEM_PROMPT}\n\n{_build_user_message(query, context)}"
                }]}],
                "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.3},
            },
        )
        if r.status_code != 200:
            logger.warning("[Gemini] HTTP %s: %s", r.status_code, r.text[:160])
            return None
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.warning("[Gemini] error: %s", e)
        return None


async def _call_anthropic(client: httpx.AsyncClient, query: str, context: str,
                          key: str) -> Optional[str]:
    if not key:
        return None
    try:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1500,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user",
                              "content": _build_user_message(query, context)}],
            },
        )
        if r.status_code != 200:
            logger.warning("[Anthropic] HTTP %s: %s", r.status_code, r.text[:160])
            return None
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        logger.warning("[Anthropic] error: %s", e)
        return None


def _build_context(rag_chunks: List[Dict],
                   web_results: List[Dict]) -> Tuple[str, List[str]]:
    parts = []
    sources = []

    if rag_chunks:
        parts.append("📂 ИЗ ВНУТРЕННИХ ДОКУМЕНТОВ:")
        for i, ch in enumerate(rag_chunks, 1):
            name = ch.get("doc_name") or ch.get("source") or f"Документ {i}"
            text = (ch.get("chunk") or "").strip()
            if not text:
                continue
            score = ch.get("score_hybrid", ch.get("score", 0))
            parts.append(f"\n[Источник {i}: «{name}» | релевантность {score*100:.0f}%]\n{text[:1200]}")
            if name not in sources:
                sources.append(name)

    if web_results:
        parts.append("\n\n🌐 ИЗ ВЕБ-ПОИСКА (актуальная информация):")
        for i, r in enumerate(web_results[:3], 1):
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            if not snippet:
                continue
            parts.append(f"\n[Веб {i}: {title}]\n{snippet[:600]}")
            if url:
                sources.append(url)

    return "\n".join(parts), sources


# ─── Главный endpoint ──────────────────────────────────────────────

def build_chat_router(kb, orchestrator=None) -> APIRouter:
    router = APIRouter()

    @router.post("/api/kb/chat/fast/v2", tags=["kb"])
    async def kb_chat_fast_v2(req: ChatRequest):
        t0 = time.time()
        query      = req.question.strip()[:500]
        session_id = (req.session_id or "default").strip()
        flags      = []

        # 1) Cache
        ck = cache_key("kb_chat_v3", session_id, query)
        if req.use_cache:
            hit = await cache_get(ck)
            if hit:
                hit["latency_ms"] = int((time.time() - t0) * 1000)
                hit["flags"] = (hit.get("flags") or []) + ["cache_hit"]
                return hit

        # 2) Retrieve top-15
        try:
            results = kb.search(query, top_k=15 if req.rerank else 5)
        except Exception as e:
            logger.error("[chat_v3] kb.search error: %s", e)
            results = []

        # 3) Hybrid scoring
        results = _hybrid_rerank(query, results)
        flags.append("hybrid")

        # 4) Reranker
        if req.rerank and len(results) > 5:
            try:
                results = await rerank_chunks(query, results, top_k=5, min_score=0.0)
                flags.append("rerank")
            except Exception as e:
                logger.warning("[chat_v3] rerank error: %s", e)
                results = results[:5]

        # 5) Качество RAG
        top_score_hybrid = (results[0].get("score_hybrid",
                            results[0].get("score", 0)) if results else 0)
        rag_confidence = top_score_hybrid
        rag_chunks_good = [r for r in results
                           if r.get("score_hybrid", r.get("score", 0)) >= 0.20][:5]

        logger.info("[chat_v3] q='%s' rag_conf=%.2f good=%d",
                    query[:50], rag_confidence, len(rag_chunks_good))

        # 6) Решаем — нужен ли веб?
        web_results = []
        if req.use_web and orchestrator is not None and _needs_web(query, rag_confidence):
            try:
                web_agent = getattr(orchestrator, "_web", None)
                if web_agent is None:
                    from agents.web_agent import WebAgent
                    web_agent = WebAgent(timeout=5.0, max_results=3)
                wr = await asyncio.wait_for(web_agent.run(query), timeout=6.0)
                if wr.found:
                    web_results = wr.results[:3]
                    flags.append(f"web:{wr.source}")
            except asyncio.TimeoutError:
                logger.info("[chat_v3] web timeout")
            except Exception as e:
                logger.warning("[chat_v3] web error: %s", e)

        # 7) MCP enrichment — БЕЗ зависимости от RAG (может сработать без него)
        mcp_text = ""
        mcp_tools_used = []
        mcp_results = []
        if req.use_mcp and _MCP_AVAILABLE:
            try:
                mcp_data = await enrich_with_mcp(query, max_tools=3, timeout=8.0)
                mcp_text = mcp_data.get("text", "")
                mcp_tools_used = mcp_data.get("tools_used", [])
                mcp_results = mcp_data.get("results", [])
                if mcp_tools_used:
                    flags.append(f"mcp:{','.join(mcp_tools_used)}")
                    logger.info("[chat_v3] MCP tools used: %s", mcp_tools_used)
            except Exception as e:
                logger.warning("[chat_v3] mcp_integration error: %s", e)

        # 7b) Если ничего нет ВООБЩЕ (ни RAG, ни Web, ни MCP) — честный отказ
        if not rag_chunks_good and not web_results and not mcp_text:
            answer = (
                f"**В базе знаний я не нашёл прямого ответа на вопрос «{query}».**\n\n"
                "Возможные причины:\n"
                "• Документ с этой информацией ещё не загружен в систему\n"
                "• Формулировка вопроса не совпала с терминологией документов\n\n"
                "**Что попробовать:**\n"
                "1. Переформулируй вопрос — используй ключевые слова из документов\n"
                "2. Загрузи нужный документ через раздел «Документы»\n"
                "3. Уточни область — HR, безопасность, финансы и т.д."
            )
            return {
                "answer": answer, "found": False, "sources": [], "source_details": [],
                "confidence": 0, "mode": "not_found",
                "flags": flags + ["not_found"],
                "latency_ms": int((time.time() - t0) * 1000),
            }

        # 8) Build context (RAG + Web + MCP)
        context, sources = _build_context(rag_chunks_good, web_results)
        if mcp_text:
            context = context + "\n\n" + mcp_text
            # MCP-источники тоже в sources
            for tu in mcp_tools_used:
                src_label = f"MCP:{tu}"
                if src_label not in sources:
                    sources.append(src_label)

        source_details = [{
            "name":     ch.get("doc_name") or ch.get("source") or "Документ",
            "category": ch.get("category", ""),
            "score":    round(ch.get("score_hybrid", ch.get("score", 0)) * 100, 1),
            "preview":  (ch.get("chunk") or "")[:200] + "...",
        } for ch in rag_chunks_good]

        # 9) LLM
        groq_key   = os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
        anth_key   = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")

        answer = ""
        used = "no_llm"

        timeout = httpx.Timeout(20.0, connect=6.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            answer = await _call_groq(client, query, context, groq_key) or ""
            if answer:
                used = "groq:llama-3.3-70b"
            else:
                tasks = []
                if gemini_key:
                    tasks.append(asyncio.create_task(
                        _call_gemini(client, query, context, gemini_key), name="gemini"))
                if anth_key:
                    tasks.append(asyncio.create_task(
                        _call_anthropic(client, query, context, anth_key), name="anthropic"))
                if tasks:
                    try:
                        done, pending = await asyncio.wait(
                            tasks, timeout=18.0, return_when=asyncio.FIRST_COMPLETED)
                        for d in done:
                            res = d.result()
                            if res:
                                answer = res
                                used = d.get_name()
                                break
                        for p in pending:
                            p.cancel()
                    except Exception as e:
                        logger.warning("[chat_v3] parallel error: %s", e)

        # 10) Ollama last resort
        if not answer and orchestrator is not None:
            try:
                synth = orchestrator.synthesis
                if getattr(synth, "_ollama_ok", False):
                    loop = asyncio.get_event_loop()
                    answer = await loop.run_in_executor(
                        None, synth._call_ollama, query, context[:1500])
                    if answer:
                        used = f"ollama:{synth._model}"
            except Exception:
                pass

        if not answer:
            answer = "⚠️ Не удалось получить ответ от LLM. Проверь GROQ_API_KEY в `.env`."
            used = "no_llm"

        # 11) Footer с источниками (если LLM не упомянула)
        if sources and "Источник" not in answer and "источник" not in answer.lower():
            doc_sources = [s for s in sources if not s.startswith("http")]
            web_count = sum(1 for s in sources if s.startswith("http"))
            footer = "\n\n---\n"
            if doc_sources:
                footer += f"📄 **Документы:** {', '.join(doc_sources[:3])}\n"
            if web_count:
                footer += f"🌐 **Веб-источников:** {web_count}\n"
            answer += footer

        # Footer с MCP-источниками
        if mcp_tools_used and "🔧" not in answer:
            answer += "\n🔧 **MCP-инструменты:** " + ", ".join(mcp_tools_used)

        conf = round(rag_confidence * 100, 1)
        # mode определяется составом источников
        if mcp_tools_used and web_results:
            mode = "full_hybrid"
        elif mcp_tools_used and rag_chunks_good:
            mode = "rag_mcp"
        elif mcp_tools_used:
            mode = "mcp_only"
        elif web_results:
            mode = "hybrid"
        else:
            mode = "rag"

        result = {
            "answer":         answer,
            "found":          True,
            "sources":        sources,
            "source_details": source_details,
            "confidence":     conf,
            "mode":           mode,
            "flags":          flags + [used],
            "latency_ms":     int((time.time() - t0) * 1000),
            "rag_chunks":     len(rag_chunks_good),
            "web_used":       bool(web_results),
            "mcp_tools_used": mcp_tools_used,
            "mcp_results":    mcp_results,
        }

        if req.use_cache:
            await cache_set(ck, result)
        try:
            await db_save_chat(session_id, query, answer, sources, conf / 100, True)
        except Exception:
            pass

        return result

    # ─── Диагностика RAG ────────────────────────────────────────
    @router.get("/api/kb/chat/debug", tags=["kb"])
    async def kb_chat_debug(q: str, top_k: int = 10):
        """Показывает что нашёл RAG по запросу — для отладки качества."""
        results = kb.search(q, top_k=top_k)
        results = _hybrid_rerank(q, results)
        if len(results) > 5:
            try:
                results = await rerank_chunks(q, results, top_k=10, min_score=0.0)
            except Exception:
                pass
        return {
            "query": q,
            "results": [
                {
                    "doc_name":       r.get("doc_name") or r.get("source"),
                    "category":       r.get("category"),
                    "score_semantic": round(r.get("score", 0), 3),
                    "score_keyword":  round(r.get("score_keyword", 0), 3),
                    "score_hybrid":   round(r.get("score_hybrid", 0), 3),
                    "score_rerank":   round(r.get("rerank_score", 0), 3) if "rerank_score" in r else None,
                    "chunk_preview":  (r.get("chunk") or "")[:300],
                }
                for r in results[:top_k]
            ],
        }

    return router