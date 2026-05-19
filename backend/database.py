"""
Sentinel AI — PostgreSQL Database Layer (v4.1)

Что нового:
  • Таблица users + методы db_create_user/db_get_user/db_user_exists/db_update_last_login
  • Таблица sessions для JWT-токенов (refresh через БД)
  • Все методы документов/чатов/тренировок без изменений
"""
import os, json
from typing import Optional, List, Dict
import asyncpg
from asyncpg.pool import Pool

_pool: Optional[Pool] = None
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sentinel:sentinel123@localhost:5432/sentinel_ai"
)

async def get_pool() -> Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=2, max_size=10, command_timeout=60
        )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Общее',
    content TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0, chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY, doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL, content TEXT NOT NULL, vector TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);

CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY, session_id TEXT NOT NULL DEFAULT 'default',
    question TEXT NOT NULL, answer TEXT NOT NULL, sources TEXT,
    confidence FLOAT NOT NULL DEFAULT 0, found BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id);

CREATE TABLE IF NOT EXISTS training_runs (
    id SERIAL PRIMARY KEY, dataset TEXT NOT NULL, epochs INTEGER NOT NULL,
    lr FLOAT NOT NULL, batch_size INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'running',
    best_acc FLOAT, history TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), finished_at TIMESTAMPTZ
);

-- ── НОВОЕ: users ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- ── НОВОЕ: sessions (JWT-токены) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(username);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
"""


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    print("✅ PostgreSQL schema initialized (v4.1 with users)")


# ══════════════════════════════════════════════════════════════════════
# DOCUMENTS / CHUNKS
# ══════════════════════════════════════════════════════════════════════

async def db_create_document(name: str, content: str, category: str) -> Dict:
    pool = await get_pool()
    content = content.replace('\x00', '')
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO documents (name,content,category,size) VALUES ($1,$2,$3,$4) RETURNING *",
            name, content, category, len(content))
    return dict(row)


async def db_update_chunk_count(doc_id: int, count: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE documents SET chunk_count=$1 WHERE id=$2", count, doc_id)


async def db_save_chunks(doc_id: int, chunks: List[str], vectors: List[List[float]]):
    pool = await get_pool()
    rows = [(doc_id, i, ch, json.dumps(vec)) for i, (ch, vec) in enumerate(zip(chunks, vectors))]
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO chunks (doc_id,chunk_index,content,vector) VALUES ($1,$2,$3,$4)", rows)


async def db_get_all_chunks() -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT c.id,c.doc_id,c.chunk_index,c.content,c.vector,d.name as doc_name,d.category "
            "FROM chunks c JOIN documents d ON d.id=c.doc_id ORDER BY c.doc_id,c.chunk_index")
    return [dict(r) for r in rows]


async def db_list_documents() -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id,name,category,size,chunk_count,created_at FROM documents ORDER BY created_at DESC")
    return [dict(r) for r in rows]


async def db_delete_document(doc_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM documents WHERE id=$1", doc_id)


async def db_count_documents() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM documents")


async def db_count_chunks() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM chunks")


# ══════════════════════════════════════════════════════════════════════
# CHAT HISTORY
# ══════════════════════════════════════════════════════════════════════

async def db_save_chat(session_id: str, question: str, answer: str,
                       sources: List[str], confidence: float, found: bool) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO chat_history (session_id,question,answer,sources,confidence,found) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            session_id, question, answer, json.dumps(sources), confidence, found)
    return row["id"]


async def db_get_chat_history(session_id: str = "default", limit: int = 50) -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id,question,answer,sources,confidence,found,created_at FROM chat_history "
            "WHERE session_id=$1 ORDER BY created_at ASC LIMIT $2", session_id, limit)
    result = []
    for r in rows:
        d = dict(r)
        d["sources"] = json.loads(d["sources"]) if d["sources"] else []
        result.append(d)
    return result


# ══════════════════════════════════════════════════════════════════════
# TRAINING RUNS
# ══════════════════════════════════════════════════════════════════════

async def db_create_training_run(dataset: str, epochs: int, lr: float, batch_size: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO training_runs (dataset,epochs,lr,batch_size) VALUES ($1,$2,$3,$4) RETURNING id",
            dataset, epochs, lr, batch_size)
    return row["id"]


async def db_finish_training_run(run_id: int, best_acc: float, history: Dict):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE training_runs SET status='finished',best_acc=$1,history=$2,finished_at=NOW() WHERE id=$3",
            best_acc, json.dumps(history), run_id)


async def db_get_training_runs(limit: int = 10) -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id,dataset,epochs,lr,batch_size,status,best_acc,started_at,finished_at "
            "FROM training_runs ORDER BY started_at DESC LIMIT $1", limit)
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════
# ── НОВОЕ: USERS & SESSIONS ──────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

async def db_create_user(username: str, email: str, password_hash: str,
                         role: str = "user") -> Dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO users (username,email,password_hash,role) "
            "VALUES ($1,$2,$3,$4) RETURNING id,username,email,role,created_at",
            username, email, password_hash, role
        )
    return dict(row)


async def db_get_user(username: str) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id,username,email,password_hash,role,created_at,last_login_at "
            "FROM users WHERE username=$1", username
        )
    return dict(row) if row else None


async def db_user_exists(username: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return bool(await conn.fetchval(
            "SELECT 1 FROM users WHERE username=$1 LIMIT 1", username
        ))


async def db_update_last_login(username: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_login_at=NOW() WHERE username=$1", username
        )


async def db_save_session(token: str, username: str, expires_at) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (token,username,expires_at) VALUES ($1,$2,$3) "
            "ON CONFLICT (token) DO NOTHING",
            token, username, expires_at
        )


async def db_get_session(token: str) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT s.token,s.username,s.expires_at,u.email,u.role,u.created_at "
            "FROM sessions s JOIN users u ON u.username=s.username "
            "WHERE s.token=$1 AND s.expires_at > NOW()", token
        )
    return dict(row) if row else None


async def db_delete_session(token: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE token=$1", token)


async def db_cleanup_expired_sessions() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "WITH d AS (DELETE FROM sessions WHERE expires_at < NOW() RETURNING 1) "
            "SELECT COUNT(*) FROM d"
        )
    return int(result or 0)


async def db_count_users() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")