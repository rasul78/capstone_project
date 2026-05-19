"""
Sentinel AI — Cache Layer (Redis с fallback на in-memory LRU)

Зачем:
  • Повторный одинаковый вопрос возвращается мгновенно (без вызова LLM).
  • TTL по умолчанию — 1 час (можно настроить через CACHE_TTL_SEC).
  • Если Redis недоступен — автоматический фолбэк на in-memory LRU
    (работает в одном процессе, теряется при reload, но всё равно ускоряет).

Использование:
    from integrations.cache import cache_get, cache_set, cache_key

    key = cache_key("kb_chat", session_id, question)
    if (hit := await cache_get(key)) is not None:
        return hit                          # моментальный ответ
    answer = await expensive_llm_call(...)
    await cache_set(key, answer)            # сохраняем
"""
import os, json, hashlib, time, logging
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger("sentinel.cache")

REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL    = int(os.getenv("CACHE_TTL_SEC", "3600"))   # 1 час
CACHE_PREFIX = os.getenv("CACHE_PREFIX", "sentinel:v1:")
MAX_MEM_ITEMS = int(os.getenv("CACHE_MEM_ITEMS", "500"))

_redis = None
_redis_ok = False
_mem: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()


async def init_cache():
    """Один раз на старте — попробовать подключиться к Redis."""
    global _redis, _redis_ok
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True,
                                   socket_connect_timeout=2.0)
        await _redis.ping()
        _redis_ok = True
        logger.info("[cache] ✅ Redis подключён: %s (TTL=%ds)", REDIS_URL, CACHE_TTL)
    except ImportError:
        logger.warning("[cache] redis не установлен — fallback на in-memory LRU. "
                       "Установи: pip install redis")
    except Exception as e:
        logger.warning("[cache] Redis недоступен (%s) — fallback на in-memory LRU", e)
        _redis = None
        _redis_ok = False


async def close_cache():
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None


def cache_key(namespace: str, *parts: str) -> str:
    """Сборка ключа: sentinel:v1:<ns>:<sha256(parts)>"""
    raw = "||".join(str(p) for p in parts).encode("utf-8")
    h = hashlib.sha256(raw).hexdigest()[:32]
    return f"{CACHE_PREFIX}{namespace}:{h}"


async def cache_get(key: str) -> Optional[Any]:
    # 1) Redis
    if _redis_ok and _redis is not None:
        try:
            raw = await _redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("[cache] redis get error: %s", e)

    # 2) In-memory
    item = _mem.get(key)
    if item is None:
        return None
    expires_at, value = item
    if expires_at < time.time():
        _mem.pop(key, None)
        return None
    _mem.move_to_end(key)
    return value


async def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    ttl = ttl if ttl is not None else CACHE_TTL

    # 1) Redis
    if _redis_ok and _redis is not None:
        try:
            await _redis.set(key, json.dumps(value, ensure_ascii=False, default=str),
                             ex=ttl)
            return
        except Exception as e:
            logger.warning("[cache] redis set error: %s", e)

    # 2) In-memory с LRU-эвикцией
    _mem[key] = (time.time() + ttl, value)
    _mem.move_to_end(key)
    while len(_mem) > MAX_MEM_ITEMS:
        _mem.popitem(last=False)


async def cache_delete(pattern: str) -> int:
    """Удалить ключи по pattern (только для Redis; в памяти — точное совпадение)."""
    deleted = 0
    if _redis_ok and _redis is not None:
        try:
            async for k in _redis.scan_iter(match=pattern, count=200):
                await _redis.delete(k)
                deleted += 1
        except Exception as e:
            logger.warning("[cache] redis delete error: %s", e)
    if pattern in _mem:
        _mem.pop(pattern, None)
        deleted += 1
    return deleted


def cache_stats() -> dict:
    return {
        "backend":   "redis" if _redis_ok else "memory",
        "redis_ok":  _redis_ok,
        "mem_size":  len(_mem),
        "ttl_sec":   CACHE_TTL,
    }