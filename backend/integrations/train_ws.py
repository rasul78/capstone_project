"""
Sentinel AI — WebSocket Manager для прогресса обучения

Зачем:
  • SSE (Server-Sent Events) на /api/train/stream работает, но односторонний.
  • WebSocket /ws/train позволяет:
        — клиенту подписаться и получать live-обновления
        — слать команды (pause/resume/stop) обратно
        — несколько подключений могут смотреть один и тот же train run

Использование на frontend:
    const ws = new WebSocket('ws://localhost:8000/ws/train');
    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        // {type: 'progress', epoch: 3, loss: 0.42, acc: 0.81}
        // {type: 'finished', best_acc: 0.91}
        // {type: 'log', text: '...'}
    };
"""
import asyncio, json, logging
from typing import Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("sentinel.ws")


class TrainWSManager:
    def __init__(self):
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        logger.info("[ws/train] client connected (total=%d)", len(self._clients))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._clients.discard(ws)
        logger.info("[ws/train] client disconnected (total=%d)", len(self._clients))

    async def broadcast(self, message: dict):
        """Шлём сообщение всем подписчикам. Упавшие соединения чистим."""
        if not self._clients:
            return
        payload = json.dumps(message, ensure_ascii=False, default=str)
        dead = []
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    def broadcast_nowait(self, message: dict):
        """Sync-обёртка для вызова из train_thread (без await)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        except Exception:
            pass

    def count(self) -> int:
        return len(self._clients)


# Глобальный singleton
train_ws = TrainWSManager()


async def train_ws_endpoint(websocket: WebSocket):
    """
    Регистрируется в main.py:
        app.add_api_websocket_route("/ws/train", train_ws_endpoint)
    """
    await train_ws.connect(websocket)
    try:
        # Сразу шлём приветствие
        await websocket.send_json({
            "type": "hello",
            "message": "Connected to train progress stream",
            "subscribers": train_ws.count(),
        })

        while True:
            # Ждём команды от клиента (или просто keep-alive)
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
            except Exception:
                cmd = {"type": "raw", "data": data}

            # Простой echo + поддержка ping/pong
            if cmd.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "ack", "received": cmd})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("[ws/train] error: %s", e)
    finally:
        await train_ws.disconnect(websocket)