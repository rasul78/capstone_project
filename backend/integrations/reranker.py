"""
Sentinel AI — BGE Reranker

Зачем нужен:
  • Bi-encoder (SentenceTransformer) при поиске даёт top-K кандидатов очень быстро,
    но score — это просто косинусная близость. Часто релевантный чанк оказывается
    на 4-5 месте, а на 1-2 — мусор.
  • Cross-encoder reranker (BGE) перебирает (query, chunk) и даёт точный скоринг
    релевантности 0..1. Это сильно повышает качество ответа RAG.
  • Стратегия: kb.search(top_k=20) → reranker(top_k=5) → передаём в LLM.

Используется: BAAI/bge-reranker-v2-m3 (мультиязычный, 568MB, ~50ms на пару CPU).
Скачивается автоматически при первом вызове.

Использование:
    from integrations.reranker import rerank_chunks

    chunks = kb.search(query, top_k=20)
    chunks = await rerank_chunks(query, chunks, top_k=5)
"""
import os, asyncio, logging
from typing import List, Dict, Optional

logger = logging.getLogger("sentinel.reranker")

MODEL_NAME = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
ENABLED    = os.getenv("RERANKER_ENABLED", "true").lower() in ("1", "true", "yes")

_model = None
_load_failed = False
_lock = asyncio.Lock()


def _try_load_model():
    """Синхронная загрузка — вызывается через run_in_executor."""
    global _model, _load_failed
    if _model is not None or _load_failed:
        return
    try:
        from sentence_transformers import CrossEncoder
        logger.info("[reranker] Загружаю модель %s (первый раз ~30 сек)...", MODEL_NAME)
        _model = CrossEncoder(MODEL_NAME, max_length=512)
        logger.info("[reranker] ✅ Модель готова")
    except ImportError:
        _load_failed = True
        logger.warning("[reranker] sentence-transformers не установлен. "
                       "Установи: pip install sentence-transformers")
    except Exception as e:
        _load_failed = True
        logger.warning("[reranker] Не удалось загрузить модель: %s", e)


async def _ensure_loaded():
    global _model, _load_failed
    if _model is not None or _load_failed or not ENABLED:
        return
    async with _lock:
        if _model is None and not _load_failed:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _try_load_model)


async def rerank_chunks(query: str,
                        chunks: List[Dict],
                        top_k: int = 5,
                        min_score: float = 0.0) -> List[Dict]:
    """
    Пересортировывает чанки по cross-encoder скорингу.
    Каждому чанку добавляется поле `rerank_score` (0..1).

    Если модель недоступна — возвращает chunks[:top_k] без изменений.
    """
    if not ENABLED or not chunks:
        return chunks[:top_k]

    await _ensure_loaded()
    if _model is None:
        return chunks[:top_k]

    pairs = [(query, (c.get("chunk") or c.get("content") or "")[:1500])
             for c in chunks]

    try:
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None, lambda: _model.predict(pairs, batch_size=16, show_progress_bar=False)
        )
    except Exception as e:
        logger.warning("[reranker] predict error: %s — возвращаю без rerank", e)
        return chunks[:top_k]

    # Нормализуем в 0..1 через sigmoid (BGE возвращает logits)
    import math
    out = []
    for c, raw in zip(chunks, scores):
        s = 1.0 / (1.0 + math.exp(-float(raw)))
        c2 = dict(c)
        c2["rerank_score"] = round(s, 4)
        c2["score_original"] = c.get("score", 0)
        c2["score"] = s  # перезаписываем score новым (более точным)
        out.append(c2)

    out.sort(key=lambda x: -x["rerank_score"])
    out = [c for c in out if c["rerank_score"] >= min_score][:top_k]
    return out


def reranker_status() -> dict:
    return {
        "enabled":      ENABLED,
        "model":        MODEL_NAME,
        "loaded":       _model is not None,
        "load_failed":  _load_failed,
    }