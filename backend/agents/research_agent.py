"""
Sentinel AI — Research Agent
Отвечает за поиск по локальной базе знаний (RAG).
Возвращает структурированный результат для Synthesis Agent.
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("sentinel.research_agent")


@dataclass
class ResearchResult:
    found: bool
    chunks: List[Dict]
    confidence: float
    sources: List[str]
    latency_ms: float
    agent: str = "ResearchAgent"
    error: Optional[str] = None


class ResearchAgent:
    """
    Agent 1: Поиск по документам через RAG.
    Использует KnowledgeBase (sentence-transformers + cosine similarity).
    """

    def __init__(self, kb, top_k: int = 8, min_score: float = 0.30):
        self.kb = kb
        self.top_k = top_k
        self.min_score = min_score
        self.name = "ResearchAgent"
        logger.info(f"[{self.name}] initialized, top_k={top_k}, min_score={min_score}")

    def run(self, query: str) -> ResearchResult:
        """Запускает RAG-поиск по локальным документам."""
        t0 = time.time()
        logger.info(f"[{self.name}] Query: {query!r}")

        # Валидация входных данных
        query = self._sanitize(query)
        if not query:
            return ResearchResult(
                found=False, chunks=[], confidence=0.0, sources=[],
                latency_ms=0, error="Empty query after sanitization"
            )

        try:
            results = self.kb.search(query, top_k=self.top_k)
        except Exception as e:
            logger.error(f"[{self.name}] KB search error: {e}")
            return ResearchResult(
                found=False, chunks=[], confidence=0.0, sources=[],
                latency_ms=(time.time() - t0) * 1000, error=str(e)
            )

        latency = (time.time() - t0) * 1000

        if not results or results[0]["score"] < self.min_score:
            best_score = results[0]["score"] if results else 0.0
            logger.info(f"[{self.name}] No relevant results (best={best_score:.3f})")
            return ResearchResult(
                found=False, chunks=results, confidence=results[0]["score"] if results else 0.0,
                sources=[], latency_ms=latency
            )

        sources = list(dict.fromkeys(r["doc_name"] for r in results))
        best_conf = results[0]["score"]

        logger.info(f"[{self.name}] Found {len(results)} chunks, best={best_conf:.3f}, latency={latency:.0f}ms")

        return ResearchResult(
            found=True,
            chunks=results,
            confidence=best_conf,
            sources=sources,
            latency_ms=latency,
        )

    @staticmethod
    def _sanitize(text: str) -> str:
        """Базовая очистка запроса."""
        # Убираем управляющие символы и лишние пробелы
        text = "".join(c for c in text if ord(c) >= 32 or c in "\n\t")
        return text.strip()[:500]