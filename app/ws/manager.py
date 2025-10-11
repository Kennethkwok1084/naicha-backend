from __future__ import annotations

import asyncio
from typing import Any

from starlette.websockets import WebSocket, WebSocketState


class MerchantNotifier:
    """维护商户端 WebSocket 连接并支持广播订单事件。"""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def register(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.add(websocket)

    async def unregister(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            if not self._connections:
                return
            serialized = message
            stale: list[WebSocket] = []
            for connection in self._connections:
                if connection.application_state != WebSocketState.CONNECTED:
                    stale.append(connection)
                    continue
                try:
                    await connection.send_json(serialized)
                except Exception:
                    stale.append(connection)
            for connection in stale:
                self._connections.discard(connection)


merchant_notifier = MerchantNotifier()
