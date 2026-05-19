"""
Sentinel AI — Authentication Module v2 (DB-backed)

Что нового:
  • Хранение пользователей и сессий в PostgreSQL (раньше было in-memory dict,
    который сбрасывался на каждый --reload uvicorn — поэтому невозможно было войти).
  • bcrypt вместо sha256+salt (с fallback на sha256 если bcrypt не установлен).
  • Async-методы, чтобы не блокировать event loop.

API:
  await register_user(username, password, email)  → {success, token, user}
  await login_user(username, password)            → {success, token, user}
  await verify_token(token)                       → {username, email, role, ...} | None
  await logout_user(token)                        → None
"""
import os, secrets, hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from database import (
    db_create_user, db_get_user, db_user_exists, db_update_last_login,
    db_save_session, db_get_session, db_delete_session,
)

SECRET_KEY = os.getenv("JWT_SECRET", "sentinel-ai-secret-2024-change-in-prod")
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "168"))   # 7 дней
PASS_SALT = os.getenv("PASS_SALT", "sentinel_salt_2024")

# ── bcrypt с fallback ─────────────────────────────────────────────────
try:
    import bcrypt
    _BCRYPT_OK = True
except ImportError:
    _BCRYPT_OK = False
    print("⚠️  bcrypt не установлен — используется sha256+salt. "
          "Установи: pip install bcrypt")


def _hash_password(password: str) -> str:
    if _BCRYPT_OK:
        return bcrypt.hashpw(password.encode("utf-8"),
                             bcrypt.gensalt(rounds=10)).decode("utf-8")
    return "sha256$" + hashlib.sha256(f"{password}{PASS_SALT}".encode()).hexdigest()


def _verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith("sha256$"):
        # Legacy / fallback
        expected = hashlib.sha256(f"{password}{PASS_SALT}".encode()).hexdigest()
        return hashed[7:] == expected
    if _BCRYPT_OK:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False
    return False


def _safe_user(row: Dict) -> Dict:
    """Удаляем password_hash перед отправкой клиенту."""
    return {
        "username":   row.get("username", ""),
        "email":      row.get("email", ""),
        "role":       row.get("role", "user"),
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else "",
    }


async def register_user(username: str, password: str, email: str = "") -> Dict:
    username = (username or "").strip()
    password = password or ""
    email = (email or "").strip()

    if not username or len(username) < 3:
        return {"success": False, "error": "Логин должен быть не менее 3 символов"}
    if len(password) < 6:
        return {"success": False, "error": "Пароль должен быть не менее 6 символов"}

    if await db_user_exists(username):
        return {"success": False, "error": "Пользователь уже существует"}

    try:
        row = await db_create_user(
            username=username, email=email,
            password_hash=_hash_password(password), role="user"
        )
    except Exception as e:
        return {"success": False, "error": f"Ошибка БД: {e}"}

    token = await _generate_token(username)
    return {"success": True, "token": token, "user": _safe_user(row)}


async def login_user(username: str, password: str) -> Dict:
    username = (username or "").strip()
    if not username or not password:
        return {"success": False, "error": "Введите логин и пароль"}

    row = await db_get_user(username)
    if not row:
        return {"success": False, "error": "Пользователь не найден"}

    if not _verify_password(password, row["password_hash"]):
        return {"success": False, "error": "Неверный пароль"}

    await db_update_last_login(username)
    token = await _generate_token(username)
    return {"success": True, "token": token, "user": _safe_user(row)}


async def verify_token(token: str) -> Optional[Dict]:
    if not token:
        return None
    row = await db_get_session(token)
    if not row:
        return None
    return {
        "username":   row["username"],
        "email":      row.get("email", ""),
        "role":       row.get("role", "user"),
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else "",
    }


async def logout_user(token: str) -> None:
    if token:
        await db_delete_session(token)


async def _generate_token(username: str) -> str:
    token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    await db_save_session(token, username, expires_at)
    return token


async def ensure_demo_users():
    """Создаёт демо-юзеров (demo/demo123 и admin/admin123) если их нет.
    Вызывается один раз на старте."""
    for u, p, e in [("demo", "demo123", "demo@sentinel.ai"),
                    ("admin", "admin123", "admin@sentinel.ai")]:
        if not await db_user_exists(u):
            try:
                await db_create_user(
                    username=u, email=e,
                    password_hash=_hash_password(p),
                    role="admin" if u == "admin" else "user",
                )
                print(f"✅ Демо-пользователь создан: {u} / {p}")
            except Exception as ex:
                print(f"⚠️  Не удалось создать демо-юзера {u}: {ex}")