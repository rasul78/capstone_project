"""
Sentinel AI — Synthesis Agent v4
Генерирует умные ответы через Ollama (llama3/mistral/gemma).

Интеграция с llama3:
  1. Ollama должна быть запущена (запускается автоматически при установке)
  2. Модель уже скачана: ollama pull llama3
  3. Проверить: http://localhost:11434  (должна открываться)
"""

import os, re, time, json, logging, socket
import urllib.request, urllib.error
from typing import List, Optional
from dataclasses import dataclass, field

from agents.research_agent import ResearchResult
from agents.web_agent import WebResult

logger = logging.getLogger("sentinel.synthesis_agent")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
OLLAMA_URL  = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/generate"
OLLAMA_TAGS = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags"

PREFERRED_MODELS = ["llama3", "llama3:8b", "mistral", "mistral:7b",
                    "gemma3", "gemma:7b", "qwen2", "phi3", "llama2"]


def _ollama_available() -> bool:
    """Быстрая проверка — порт открыт?"""
    try:
        s = socket.create_connection((OLLAMA_HOST, OLLAMA_PORT), timeout=2)
        s.close()
        return True
    except Exception:
        return False


def _get_installed_models() -> List[str]:
    """Возвращает список установленных моделей."""
    try:
        resp = urllib.request.urlopen(OLLAMA_TAGS, timeout=3)
        data = json.loads(resp.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _pick_model(models: List[str]) -> Optional[str]:
    """Выбирает лучшую доступную модель."""
    for pref in PREFERRED_MODELS:
        base = pref.split(":")[0]
        match = next((m for m in models if m.startswith(base)), None)
        if match:
            return match
    return models[0] if models else None


@dataclass
class SynthesisResult:
    answer:     str
    sources:    List[str]
    confidence: float
    found:      bool
    mode:       str
    latency_ms: float
    agent:      str = "SynthesisAgent"
    flags:      List[str] = field(default_factory=list)
    rag_used:   bool = False
    web_used:   bool = False


class SynthesisAgent:

    RAG_THRESHOLD    = 0.25
    HYBRID_THRESHOLD = 0.15
    MAX_TOKENS       = 300   # минимум токенов = максимум скорости

    # Системный промпт — инструктирует модель давать качественные ответы
    SYSTEM_PROMPT = """Ассистент Sentinel AI. Отвечай кратко и чётко на русском.
Используй только информацию из контекста.
Пиши своими словами — не копируй текст дословно.
Максимум 150 слов. Без вводных фраз."""

    def __init__(self):
        self.name         = "SynthesisAgent"
        self.api_key      = os.getenv("ANTHROPIC_API_KEY", "")
        self.groq_key     = os.getenv("GROQ_API_KEY", "")
        self.gemini_key   = os.getenv("GEMINI_API_KEY", "")
        self._model       = None
        self._ollama_ok   = False
        self._last_check  = 0.0
        self._init_ollama()
        
        # Логируем доступные API
        apis = []
        if self.groq_key:   apis.append("Groq ✅ (бесплатно, очень быстро)")
        if self.api_key:    apis.append("Anthropic ✅")
        if self.gemini_key: apis.append("Gemini ✅ (бесплатно)")
        if self._ollama_ok: apis.append(f"Ollama ✅ ({self._model})")
        if not apis:        apis.append("Fallback (текстовый)")
        logger.info("[%s] Доступные LLM: %s", self.name, " | ".join(apis))

    def _init_ollama(self):
        """Определяет доступность Ollama и выбирает модель."""
        if not _ollama_available():
            logger.warning(
                "[%s] Ollama недоступна на %s:%d. "
                "Убедись что Ollama запущена. Fallback на текстовый режим.",
                self.name, OLLAMA_HOST, OLLAMA_PORT
            )
            return

        models = _get_installed_models()
        if not models:
            logger.warning(
                "[%s] Ollama запущена, но нет моделей. "
                "Выполни: ollama pull llama3",
                self.name
            )
            return

        self._model     = _pick_model(models)
        self._ollama_ok = True
        logger.info("[%s] ✅ Ollama готова. Модель: %s. Все модели: %s",
                    self.name, self._model, models)

    def _retry_ollama_check(self) -> bool:
        """Повторная проверка Ollama (раз в 30 сек)."""
        now = time.time()
        if now - self._last_check < 30:
            return self._ollama_ok
        self._last_check = now
        if not self._ollama_ok and _ollama_available():
            models = _get_installed_models()
            if models:
                self._model     = _pick_model(models)
                self._ollama_ok = True
                logger.info("[%s] Ollama появилась: %s", self.name, self._model)
        return self._ollama_ok

    # ── Генерация через Ollama ─────────────────────────────────────────────

    def _call_ollama(self, query: str, context: str) -> str:
        if not self._retry_ollama_check():
            return ""

        full_prompt = (
            self.SYSTEM_PROMPT
            + "\n\n--- КОНТЕКСТ ---\n"
            + context[:800]    # очень короткий контекст = быстро
            + "\n--- КОНЕЦ КОНТЕКСТА ---\n\n"
            + "Вопрос пользователя: " + query + "\n\n"
            + "Твой ответ (своими словами, понятно, по-русски):"
        )

        payload = json.dumps({
            "model":  self._model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "num_predict":    self.MAX_TOKENS,
                "temperature":    0.1,    # минимальная вариативность
                "top_p":          0.8,
                "top_k":          10,     # минимум = максимум скорость
                "repeat_penalty": 1.1,
                "num_ctx":        1024,   # минимальный контекст
                "num_thread":     8,      # максимум потоков CPU
                "num_batch":      512,    # большой батч = быстрее
                "stop": ["---", "Вопрос:", "Question:"],
            }
        }).encode("utf-8")

        try:
            req  = urllib.request.Request(
                OLLAMA_URL, data=payload,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read().decode("utf-8"))
            answer = data.get("response", "").strip()

            # Очищаем от артефактов
            answer = re.sub(r"---.*", "", answer, flags=re.DOTALL).strip()
            answer = re.sub(r"═+.*", "", answer, flags=re.DOTALL).strip()
            answer = re.sub(r"\n{3,}", "\n\n", answer)

            # Убираем служебные фразы которые llama иногда добавляет
            bad_starts = [
                "Согласно контексту", "На основе контекста",
                "На основе предоставленных данных", "Из контекста следует",
                "В соответствии с контекстом", "Контекст указывает",
                "Исходя из контекста", "Согласно предоставленной информации",
            ]
            for bad in bad_starts:
                if answer.startswith(bad):
                    # Найти первую запятую или точку и начать с того что после
                    idx = answer.find(",", len(bad))
                    if idx == -1: idx = answer.find(".", len(bad))
                    if idx != -1:
                        answer = answer[idx+1:].strip()
                        answer = answer[0].upper() + answer[1:] if answer else answer

            # Обрезаем если слишком длинный
            if len(answer) > 2500:
                # Обрезаем по последнему полному предложению
                cut = answer[:2500]
                last_dot = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
                if last_dot > 1500:
                    answer = cut[:last_dot+1]

            if answer:
                logger.info("[%s] Ollama (%s): %d символов", self.name, self._model, len(answer))
                return answer
            return ""

        except urllib.error.URLError:
            logger.warning("[%s] Ollama URLError — возможно упала", self.name)
            self._ollama_ok = False
            return ""
        except Exception as e:
            logger.error("[%s] Ollama error: %s", self.name, e)
            self._ollama_ok = False
            return ""

    # ── Fallback через Anthropic API ───────────────────────────────────────

    def _call_anthropic(self, query: str, context: str) -> str:
        if not self.api_key:
            return ""
        try:
            payload = json.dumps({
                "model": "claude-haiku-4-5-20251001",  # самая быстрая модель ~1 сек
                "max_tokens": 600,
                "system": self.SYSTEM_PROMPT,
                "messages": [{
                    "role": "user",
                    "content": "КОНТЕКСТ:\n" + context[:2000] + "\n\nВОПРОС: " + query
                }]
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=payload,
                headers={
                    "x-api-key":         self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type":      "application/json",
                }, method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            answer = data["content"][0]["text"].strip()
            logger.info("[%s] Claude Haiku: %d символов", self.name, len(answer))
            return answer
        except Exception as e:
            logger.warning("[%s] Anthropic error: %s", self.name, e)
            return ""

    # ── Контекст-билдер ────────────────────────────────────────────────────

    def _build_context(self, mode: str, rag: ResearchResult,
                       web: Optional[WebResult]) -> str:
        parts = []

        if mode in ("rag", "hybrid") and rag.chunks:
            seen = set()
            for i, chunk in enumerate(rag.chunks[:5], 1):
                text = chunk.get("chunk", "").strip()
                src  = chunk.get("source", "")
                if not text or text in seen:
                    continue
                seen.add(text)
                score = chunk.get("score", 0)
                # Показываем источник и текст чисто без лишних символов
                parts.append(f"[{src}]\n{text[:400]}")

        if mode in ("web", "hybrid") and web and web.results:
            parts.append("\n[Веб-поиск]")
            for r in web.results[:2]:
                title   = r.get("title", "")
                snippet = r.get("snippet", "")
                if snippet:
                    parts.append(f"{title}: {snippet[:350]}")

        return "\n\n".join(parts) if parts else "Контекст не найден."

    def _call_groq(self, query: str, context: str) -> str:
        """Groq API — бесплатно, 300-800 токен/сек, быстрее ChatGPT."""
        if not self.groq_key:
            return ""
        try:
            payload = json.dumps({
                "model": "llama-3.3-70b-versatile",  # лучшая бесплатная модель
                "max_tokens": 600,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",   "content": "КОНТЕКСТ:\n" + context[:2000] + "\n\nВОПРОС: " + query}
                ]
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=payload,
                headers={
                    "Authorization": "Bearer " + self.groq_key,
                    "Content-Type":  "application/json",
                }, method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"].strip()
            logger.info("[%s] Groq Llama-70B: %d символов", self.name, len(answer))
            return answer
        except Exception as e:
            logger.warning("[%s] Groq error: %s", self.name, e)
            return ""

    def _call_gemini(self, query: str, context: str) -> str:
        """Google Gemini API — бесплатно, 1500 req/день."""
        if not self.gemini_key:
            return ""
        try:
            payload = json.dumps({
                "contents": [{
                    "parts": [{
                        "text": self.SYSTEM_PROMPT + "\n\nКОНТЕКСТ:\n" + context[:2000] + "\n\nВОПРОС: " + query
                    }]
                }],
                "generationConfig": {"maxOutputTokens": 600, "temperature": 0.2}
            }).encode("utf-8")
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + self.gemini_key
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            logger.info("[%s] Gemini Flash: %d символов", self.name, len(answer))
            return answer
        except Exception as e:
            logger.warning("[%s] Gemini error: %s", self.name, e)
            return ""

    # ── Умный text fallback (если LLM недоступна) ─────────────────────────

    def _smart_fallback(self, query: str, mode: str,
                        rag: ResearchResult,
                        web: Optional[WebResult]) -> str:
        """
        Улучшенная склейка без LLM:
        - Выбирает самые релевантные предложения
        - Убирает дубликаты
        - Сортирует по смысловой близости к запросу
        """
        q_words = set(re.findall(r"\b\w{3,}\b", query.lower()))
        scored  = []

        if mode in ("rag", "hybrid") and rag.chunks:
            for chunk in rag.chunks[:5]:
                text  = chunk.get("chunk", "")
                score = chunk.get("score", 0)
                for sent in re.split(r"(?<=[.!?])\s+", text):
                    sent = sent.strip()
                    if len(sent) < 25:
                        continue
                    s_words  = set(re.findall(r"\b\w{3,}\b", sent.lower()))
                    overlap  = len(q_words & s_words) / max(len(q_words), 1)
                    scored.append((score * 0.5 + overlap * 0.5, sent))

        scored.sort(key=lambda x: -x[0])
        seen, lines = set(), []
        for _, sent in scored:
            if sent not in seen and len(lines) < 6:
                seen.add(sent)
                lines.append(sent)

        if not lines and mode in ("web", "hybrid") and web and web.results:
            for r in web.results[:2]:
                if r.get("snippet"):
                    lines.append(r["snippet"][:400])

        if lines:
            return " ".join(lines)

        return (
            f'По запросу «{query}» информация найдена в базе знаний, '
            f'но не удалось сформировать ответ. '
            f'Попробуйте переформулировать вопрос.'
        )

    # ── Главный метод ──────────────────────────────────────────────────────

    def run(self, query: str, rag_result: ResearchResult,
            web_result: Optional[WebResult] = None) -> SynthesisResult:

        t0    = time.time()
        flags = []

        # Режим
        rag_ok   = rag_result.found and rag_result.confidence >= self.RAG_THRESHOLD
        rag_part = (not rag_ok) and rag_result.confidence >= self.HYBRID_THRESHOLD
        web_ok   = web_result is not None and web_result.found

        if rag_ok and web_ok:   mode = "hybrid"
        elif rag_ok:            mode = "rag"
        elif web_ok:            mode = "web"
        elif rag_part:          mode, flags = "rag", ["low_confidence"]
        else:                   mode = "none"

        logger.info("[%s] mode=%s, rag=%.2f, ollama=%s(%s)",
                    self.name, mode, rag_result.confidence,
                    self._ollama_ok, self._model)

        if mode == "none":
            return SynthesisResult(
                answer=(
                    f'По запросу «{query}» ничего не найдено в базе знаний.\n\n'
                    f'Попробуйте:\n'
                    f'• Переформулировать вопрос\n'
                    f'• Загрузить документы по этой теме\n'
                    f'• Уточнить ключевые слова'
                ),
                sources=[], confidence=0.0, found=False, mode="none",
                latency_ms=(time.time()-t0)*1000, flags=["not_found"],
            )

        context = self._build_context(mode, rag_result, web_result)
        sources = self._get_sources(mode, rag_result, web_result)
        conf    = self._get_conf(mode, rag_result)

        # 1. Groq (бесплатно + самый быстрый — 300-800 токен/сек)
        if self.groq_key:
            answer = self._call_groq(query, context)
            if answer:
                flags.append("groq:llama-3.3-70b")

        # 2. Google Gemini (бесплатно — 1500 req/день)
        if not answer and self.gemini_key:
            answer = self._call_gemini(query, context)
            if answer:
                flags.append("gemini:flash")

        # 3. Anthropic API
        if not answer and self.api_key:
            answer = self._call_anthropic(query, context)
            if answer:
                flags.append("anthropic")

        # 4. Ollama (локально, медленнее)
        if not answer and self._ollama_ok:
            answer = self._call_ollama(query, context)
            if answer:
                flags.append(f"ollama:{self._model}")

        # 5. Smart text fallback
        if not answer:
            answer = self._smart_fallback(query, mode, rag_result, web_result)
            flags.append("text_fallback")

        # Источники
        doc_sources = [s for s in sources if not s.startswith("http")]
        if doc_sources:
            answer += f"\n\n📄 Источник: {', '.join(doc_sources[:3])}"

        if mode in ("web", "hybrid"):
            flags.append("web_used")

        return SynthesisResult(
            answer=answer, sources=sources,
            confidence=round(conf * 100, 1), found=True,
            mode=mode, latency_ms=(time.time()-t0)*1000,
            flags=flags, rag_used=mode in ("rag","hybrid"),
            web_used=mode in ("web","hybrid"),
        )

    def _get_sources(self, mode, rag, web):
        out = []
        if mode in ("rag", "hybrid"):
            out.extend(rag.sources or [])
        if mode in ("web", "hybrid") and web:
            out.extend(r["url"] for r in (web.results or [])[:3] if r.get("url"))
        return list(dict.fromkeys(out))

    def _get_conf(self, mode, rag):
        if mode == "rag":    return rag.confidence
        if mode == "web":    return 0.65
        if mode == "hybrid": return max(rag.confidence, 0.65)
        return 0.0