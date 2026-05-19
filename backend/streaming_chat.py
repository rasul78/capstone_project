"""
Sentinel AI — Streaming Chat Endpoint
Добавить в main.py: from streaming_chat import add_streaming_routes
"""

import asyncio
import json
import logging
import urllib.request

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("sentinel.streaming")

router = APIRouter()


class StreamRequest(BaseModel):
    question:   str
    session_id: str = "default"


def add_streaming_routes(app, get_orchestrator):
    """Регистрирует streaming роуты в FastAPI приложении."""

    @app.post("/api/agent/chat/stream", tags=["agents"])
    async def agent_chat_stream(req: StreamRequest):
        """
        Streaming чат через Ollama.
        Токены приходят по одному — текст появляется постепенно как в ChatGPT.
        """
        orchestrator = get_orchestrator()
        query        = req.question.strip()[:500]
        session_id   = req.session_id or "default"

        async def generate():
            # Helper — отправить SSE событие
            def sse(data: dict) -> str:
                return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"

            try:
                # ── Шаг 1: RAG поиск ─────────────────────────────────────
                yield sse({"type": "status", "text": "🔍 Ищу в базе знаний..."})
                await asyncio.sleep(0)

                rag = orchestrator._research.run(query)

                # ── Шаг 2: Веб-поиск если RAG слабый ─────────────────────
                web_result = None
                if not rag.found or rag.confidence < 0.28:
                    yield sse({"type": "status", "text": "🌐 Подключаю веб-поиск..."})
                    await asyncio.sleep(0)
                    try:
                        web_result = await orchestrator._web.run(query)
                    except Exception:
                        pass

                # ── Определяем режим ──────────────────────────────────────
                rag_ok = rag.found and rag.confidence >= 0.28
                web_ok = web_result is not None and web_result.found
                if rag_ok and web_ok:   mode = "hybrid"
                elif rag_ok:            mode = "rag"
                elif web_ok:            mode = "web"
                else:                   mode = "none"

                synth   = orchestrator.synthesis
                context = synth._build_context(mode, rag, web_result)
                sources = list(dict.fromkeys(rag.sources or []))[:3]
                conf    = round((rag.confidence if rag_ok else 0.65) * 100, 1)

                # ── Режим "ничего не найдено" ─────────────────────────────
                if mode == "none":
                    answer = synth._not_found(query)
                    yield sse({"type": "token", "text": answer})
                    yield sse({"type": "done", "sources": [], "confidence": 0,
                               "found": False, "mode": "none", "flags": ["not_found"]})
                    return

                # ── Шаг 3: Streaming через Ollama ─────────────────────────
                if synth._ollama_ok and synth._model:
                    model_name = synth._model
                    yield sse({"type": "status", "text": "🤖 " + model_name + " пишет ответ..."})
                    await asyncio.sleep(0)

                    prompt = (
                        synth.SYSTEM_PROMPT
                        + "\n\n--- КОНТЕКСТ ---\n"
                        + context[:1500]
                        + "\n--- КОНЕЦ ---\n\n"
                        + "Вопрос: " + query + "\n\n"
                        + "Ответ (своими словами, по-русски):"
                    )

                    payload = json.dumps({
                        "model":  model_name,
                        "prompt": prompt,
                        "stream": True,
                        "options": {
                            "num_predict":    600,
                            "temperature":    0.2,
                            "top_k":          20,
                            "repeat_penalty": 1.1,
                            "num_ctx":        2048,
                            "num_thread":     4,
                            "stop":           ["---", "Вопрос:", "[Источник"],
                        }
                    }).encode("utf-8")

                    req_obj = urllib.request.Request(
                        synth.OLLAMA_URL, data=payload,
                        headers={"Content-Type": "application/json"}, method="POST"
                    )

                    full_answer = ""

                    # Читаем streaming ответ в executor (не блокируем event loop)
                    loop = asyncio.get_event_loop()

                    def open_connection():
                        return urllib.request.urlopen(req_obj, timeout=120)

                    try:
                        resp = await loop.run_in_executor(None, open_connection)

                        def read_next_line():
                            return resp.readline()

                        while True:
                            line = await loop.run_in_executor(None, read_next_line)
                            if not line:
                                break
                            try:
                                chunk = json.loads(line.decode("utf-8"))
                                token = chunk.get("response", "")
                                done  = chunk.get("done", False)
                                if token:
                                    full_answer += token
                                    yield sse({"type": "token", "text": token})
                                    await asyncio.sleep(0)
                                if done:
                                    break
                            except Exception:
                                continue

                    except Exception as e:
                        logger.warning("[Stream] Ollama stream error: %s — fallback", e)
                        # Fallback: обычный (не streaming) вызов
                        full_answer = synth._call_ollama(query, context)
                        if not full_answer:
                            full_answer = synth._smart_fallback(query, mode, rag, web_result)
                        yield sse({"type": "token", "text": full_answer})

                    # Источники
                    if sources:
                        src_line = "\n\n📄 Источник: " + ", ".join(sources)
                        yield sse({"type": "token", "text": src_line})
                        full_answer += src_line

                    flags = ["streaming", "ollama:" + model_name]

                else:
                    # ── Fallback без Ollama ───────────────────────────────
                    yield sse({"type": "status", "text": "⚡ Формирую ответ..."})
                    result = await orchestrator.process(query, session_id)
                    full_answer = result.get("answer", "")
                    sources     = result.get("sources", [])
                    conf        = result.get("confidence", 0)
                    mode        = result.get("mode", "none")
                    flags       = result.get("flags", [])
                    yield sse({"type": "token", "text": full_answer})

                # ── Финал ────────────────────────────────────────────────
                yield sse({
                    "type":       "done",
                    "sources":    sources,
                    "confidence": conf,
                    "found":      True,
                    "mode":       mode,
                    "flags":      flags,
                })

                # Сохраняем в историю
                try:
                    from database import db_save_chat
                    await db_save_chat(session_id, query, full_answer, sources, conf / 100, True)
                except Exception:
                    pass

            except Exception as e:
                logger.error("[Stream] Fatal error: %s", e, exc_info=True)
                yield "data: " + json.dumps({"type": "error", "text": str(e)}) + "\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control":               "no-cache",
                "X-Accel-Buffering":           "no",
                "Access-Control-Allow-Origin": "*",
            }
        )