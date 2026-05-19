"""
Sentinel AI — Telegram Notifier

Отправляет уведомления администратору о ключевых событиях:
  • Новая регистрация пользователя
  • Загружен большой документ (>1MB)
  • Закончилась тренировка модели
  • Ошибка в LLM (Groq/Gemini/Anthropic недоступны)

Настройка в .env:
    TELEGRAM_BOT_TOKEN=123456:ABC-...           # получить у @BotFather
    TELEGRAM_CHAT_ID=123456789                  # свой ID, получить у @userinfobot
    TELEGRAM_ENABLED=true                       # вкл/выкл

Использование:
    from integrations.telegram_notify import notify

    await notify("🆕 Зарегистрировался: @alice")
    await notify("❌ Ошибка обучения", level="error")
"""
import os, asyncio, logging
from typing import Optional

import httpx

logger = logging.getLogger("sentinel.telegram")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ENABLED   = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("1", "true", "yes")

_LEVEL_ICONS = {
    "info":    "ℹ️",
    "success": "✅",
    "warning": "⚠️",
    "error":   "❌",
}


def is_configured() -> bool:
    return bool(BOT_TOKEN and CHAT_ID and ENABLED)


async def notify(text: str, level: str = "info",
                 parse_mode: str = "HTML",
                 silent: bool = False) -> bool:
    """
    Отправляет сообщение в Telegram. Возвращает True при успехе.
    Никогда не бросает исключения — работает в background.
    """
    if not is_configured():
        return False

    icon = _LEVEL_ICONS.get(level, "")
    full = f"{icon} {text}" if icon else text

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":              CHAT_ID,
        "text":                 full[:4000],
        "parse_mode":           parse_mode,
        "disable_notification": silent,
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(url, json=payload)
            if r.status_code == 200:
                return True
            logger.warning("[telegram] HTTP %s: %s", r.status_code, r.text[:200])
            return False
    except Exception as e:
        logger.warning("[telegram] error: %s", e)
        return False


def notify_bg(text: str, level: str = "info") -> None:
    """Fire-and-forget из не-async кода или там где не хочется await."""
    if not is_configured():
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(notify(text, level))
        else:
            loop.run_until_complete(notify(text, level))
    except Exception:
        pass