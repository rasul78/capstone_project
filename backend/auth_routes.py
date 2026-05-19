"""
Sentinel AI — Auth Routes (FastAPI Router)

Подключение в main.py:
    from auth_routes import build_auth_router
    app.include_router(build_auth_router())

Endpoints:
    POST   /api/auth/register        — регистрация
    POST   /api/auth/login           — вход (выдаёт token)
    GET    /api/auth/me              — текущий пользователь по токену
    POST   /api/auth/logout          — выход (удаляет токен)
    POST   /api/auth/send-code       — отправка кода подтверждения (демо)
"""
import logging, secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field

from auth.auth import (
    register_user, login_user, verify_token, logout_user,
)

logger = logging.getLogger("sentinel.auth_routes")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    email:    str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class SendCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    code:  Optional[str] = Field(default=None, max_length=10)


def _bearer(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def build_auth_router() -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    # Опциональная зависимость от Telegram (если установлен/настроен)
    try:
        from integrations.telegram_notify import notify, is_configured as tg_on
    except Exception:
        async def notify(*_a, **_kw): return False
        def tg_on(): return False

    @router.post("/register")
    async def register(req: RegisterRequest):
        result = await register_user(req.username, req.password, req.email)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Ошибка регистрации"))

        # Уведомление в Telegram (fire-and-forget)
        if tg_on():
            try:
                await notify(
                    f"🆕 Новый пользователь: <b>{req.username}</b>"
                    + (f" ({req.email})" if req.email else ""),
                    level="success",
                )
            except Exception:
                pass

        return {
            "success": True,
            "token":   result["token"],
            "user":    result["user"],
        }

    @router.post("/login")
    async def login(req: LoginRequest):
        result = await login_user(req.username, req.password)
        if not result.get("success"):
            raise HTTPException(status_code=401, detail=result.get("error", "Ошибка входа"))
        return {
            "success": True,
            "token":   result["token"],
            "user":    result["user"],
        }

    @router.get("/me")
    async def me(authorization: Optional[str] = Header(default=None)):
        token = _bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="Нет токена")
        user = await verify_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Невалидный или истёкший токен")
        return {"success": True, "user": user}

    @router.post("/logout")
    async def logout(authorization: Optional[str] = Header(default=None)):
        token = _bearer(authorization)
        if token:
            await logout_user(token)
        return {"success": True}

    @router.post("/send-code")
    async def send_code(req: SendCodeRequest):
        """
        Демо-эндпоинт: код генерируется на фронте и просто логируется.
        В проде сюда нужно подключить почтовый сервис (SMTP / SendGrid / Resend).
        """
        # Генерируем код если не передан
        code = req.code or str(secrets.randbelow(900000) + 100000)
        logger.info("[send-code] email=%s code=%s (DEMO MODE)", req.email, code)

        if tg_on():
            try:
                await notify(f"📩 Код подтверждения для {req.email}: <code>{code}</code>",
                             level="info", silent=True)
            except Exception:
                pass

        return {
            "success": True,
            "message": "Код отправлен (демо-режим — смотри в логах backend)",
            "demo_code": code,   # В проде убрать!
        }

    return router