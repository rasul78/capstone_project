"""
Sentinel AI — Streaming Chat (SSE)

Отвечает Server-Sent Events потоком:
  GET /api/kb/chat/stream?q=...&session_id=...

  data: {"type": "status", "stage": "retrieve"}
  data: {"type": "status", "stage": "rerank"}
  data: {"type": "sources", "sources": ["doc1.pdf", ...]}
  data: {"type": "token", "text": "При"}
  data: {"type": "token", "text": "вет"}
  ...
  data: {"type": "done", "latency_ms": 1240, "confidence": 87.5}

Используется Groq streaming API. Если Groq нет — fallback на Ollama streaming.
"""
import os, json, time, logging, asyncio
from typing import AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse

from integrations.cache import cache_get, cache_set, cache_key
from integrations.reranker import rerank_chunks

logger = logging.getLogger("sentinel.stream_chat")

SYSTEM_PROMPT = """Ты — Sentinel AI, корпоративный AI-ассистент.

ПРАВИЛА:
1. Отвечай на русском языке, чётко и по делу.
2. Используй ТОЛЬКО факты из контекста. Если в контексте нет ответа — честно скажи: «В базе знаний нет информации по этому вопросу».
3. Структурируй: маркированные списки, нумерация, абзацы.
4. Пиши своими словами, не копируй дословно.
5. НЕ начинай со слов «Согласно контексту...», «На основе данных...» и т.п.
6. В конце укажи краткий вывод (1 предложение)."""


def _build_user_msg(query: str, context: str) -> str:
    return (
        "КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ:\n"
        f"{context}\n\n"
        "─────────────────────────\n"
        f"ВОПРОС: {query}\n\n"
        "Дай полный, структурированный ответ:"
    )


def _sse_pack(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


async def _stream_groq(query: str, context: str,
                       groq_key: str) -> AsyncGenerator[str, None]:
    """Streams Groq response token by token."""
    payload = {
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 1024,
        "temperature": 0.15,
        "stream": True,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": _build_user_msg(query, context)},
        ],
    }
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type":  "application/json",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        async with client.stream(
            "POST", "https://api.groq.com/openai/v1/chat/completions",
            json=payload, headers=headers,
        ) as r:
            if r.status_code != 200:
                err = await r.aread()
                logger.warning("[stream] Groq %s: %s", r.status_code, err[:200])
                return
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
                except Exception:
                    continue


def build_stream_router(kb, orchestrator=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/kb/chat/stream", tags=["kb"])
    async def kb_chat_stream(
        request: Request,
        q: str = Query(..., min_length=1, max_length=500),
        session_id: str = Query(default="default"),
        use_cache: bool = Query(default=True),
        rerank: bool = Query(default=True),
    ):
        query = q.strip()[:500]

        async def event_gen():
            t0 = time.time()

            # 1) Кэш
            ck = cache_key("kb_chat_stream", session_id, query)
            if use_cache:
                hit = await cache_get(ck)
                if hit:
                    yield _sse_pack({"type": "cached", "from": "redis"})
                    yield _sse_pack({"type": "sources", "sources": hit.get("sources", [])})
                    # Отдаём кусками, чтобы UI рендерил потоково
                    text = hit.get("answer", "")
                    for i in range(0, len(text), 50):
                        yield _sse_pack({"type": "token", "text": text[i:i+50]})
                        await asyncio.sleep(0.01)
                    yield _sse_pack({
                        "type": "done",
                        "latency_ms": int((time.time() - t0) * 1000),
                        "confidence": hit.get("confidence", 0),
                        "cached": True,
                    })
                    return

            # 2) RAG retrieve
            yield _sse_pack({"type": "status", "stage": "retrieve"})
            try:
                results = kb.search(query, top_k=20 if rerank else 5)
            except Exception as e:
                yield _sse_pack({"type": "error", "message": f"KB search error: {e}"})
                return

            if not results or results[0].get("score", 0) < 0.18:
                yield _sse_pack({
                    "type": "done",
                    "answer": f"По запросу «{query}» информация не найдена.",
                    "confidence": 0,
                    "found": False,
                })
                return

            # 3) Reranker
            if rerank and len(results) > 5:
                yield _sse_pack({"type": "status", "stage": "rerank"})
                results = await rerank_chunks(query, results, top_k=5, min_score=0.15)

            # 4) Build context
            sources, ctx_parts = [], []
            for r in results[:5]:
                name = r.get("doc_name") or r.get("source") or "Документ"
                ch   = (r.get("chunk") or "").strip()
                if not ch:
                    continue
                ctx_parts.append(f"[{name}]\n{ch[:1000]}")
                if name not in sources:
                    sources.append(name)
            context = "\n\n".join(ctx_parts)
            conf = round(results[0].get("score", 0) * 100, 1)

            yield _sse_pack({"type": "sources", "sources": sources[:5], "confidence": conf})

            # 5) Stream from Groq
            yield _sse_pack({"type": "status", "stage": "generate"})
            groq_key = os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")
            full_answer = []

            if groq_key:
                try:
                    async for chunk in _stream_groq(query, context, groq_key):
                        full_answer.append(chunk)
                        yield _sse_pack({"type": "token", "text": chunk})
                except Exception as e:
                    logger.warning("[stream] Groq stream failed: %s", e)

            answer = "".join(full_answer)

            # 6) Fallback на non-streaming если ничего не пришло
            if not answer.strip():
                yield _sse_pack({"type": "status", "stage": "fallback"})
                if orchestrator is not None:
                    try:
                        synth = orchestrator.synthesis
                        if synth._ollama_ok:
                            answer = synth._call_ollama(query, context[:1200])
                            if answer:
                                yield _sse_pack({"type": "token", "text": answer})
                    except Exception:
                        pass

            if not answer.strip():
                answer = "Не удалось получить ответ от LLM. Проверьте GROQ_API_KEY в .env."
                yield _sse_pack({"type": "token", "text": answer})

            # 7) Кэшируем результат
            full_result = {
                "answer":     answer,
                "sources":    sources,
                "confidence": conf,
                "found":      True,
            }
            if use_cache:
                await cache_set(ck, full_result)

            # 8) Сохраняем в БД (best effort)
            try:
                from database import db_save_chat
                await db_save_chat(session_id, query, answer, sources, conf / 100, True)
            except Exception:
                pass

            yield _sse_pack({
                "type": "done",
                "latency_ms": int((time.time() - t0) * 1000),
                "confidence": conf,
                "found": True,
                "cached": False,
            })

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    return router