from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

import redis.asyncio as redis
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError
from starlette.websockets import WebSocket, WebSocketState
from structlog import get_logger

from app.core.settings import Settings, get_settings

logger = get_logger(__name__)


class MerchantNotifier:
    """维护商户端 WebSocket 连接并支持跨实例广播订单事件。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._publisher: redis.Redis | None = None
        self._subscriber: redis.Redis | None = None
        self._pubsub: PubSub | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._startup_lock = asyncio.Lock()
        self._started = False

    async def startup(self) -> None:
        if self._started:
            return
        async with self._startup_lock:
            if self._started:
                return

            url = self._settings.resolved_ws_broadcast_url
            try:
                self._publisher = redis.from_url(url, decode_responses=False)
                self._subscriber = redis.from_url(url, decode_responses=False)
                await self._publisher.ping()
            except Exception:
                logger.exception("ws.broadcast.start_failed", url=url)
                await self._cleanup_redis()
            else:
                self._listener_task = asyncio.create_task(self._run_listener())
                logger.info(
                    "ws.broadcast.enabled",
                    channel=self._settings.ws_broadcast_channel,
                    url=url,
                )
            finally:
                self._started = True

    async def shutdown(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None

        if self._pubsub is not None:
            with suppress(Exception):
                await self._pubsub.aclose()
            self._pubsub = None

        await self._cleanup_redis()
        self._started = False

    async def register(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.add(websocket)

    async def unregister(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any], *, publish: bool = True) -> None:
        if not publish:
            await self._broadcast_local(message)
            return

        if self._publisher is None:
            await self._broadcast_local(message)
            return

        success = await self._publish(message)
        if not success:
            await self._broadcast_local(message)

    async def _publish(self, message: dict[str, Any]) -> bool:
        if self._publisher is None:
            return False
        try:
            payload = json.dumps(message, ensure_ascii=False)
            await self._publisher.publish(self._settings.ws_broadcast_channel, payload)
            return True
        except RedisError:
            logger.exception("ws.broadcast.publish_failed")
            return False

    async def _broadcast_local(self, message: dict[str, Any]) -> None:
        async with self._lock:
            if not self._connections:
                return

            stale: list[WebSocket] = []
            for connection in self._connections:
                if connection.application_state != WebSocketState.CONNECTED:
                    stale.append(connection)
                    continue
                try:
                    await connection.send_json(message)
                except Exception:
                    stale.append(connection)

            for connection in stale:
                self._connections.discard(connection)

    async def _run_listener(self) -> None:
        if self._subscriber is None:
            return

        pubsub = self._subscriber.pubsub(ignore_subscribe_messages=True)
        self._pubsub = pubsub

        try:
            await pubsub.subscribe(self._settings.ws_broadcast_channel)
            async for message in pubsub.listen():
                if not message or message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data_str = data.decode("utf-8")
                else:
                    data_str = data
                try:
                    payload = json.loads(data_str)
                except (TypeError, ValueError):
                    logger.warning("ws.broadcast.invalid_payload", payload=data_str)
                    continue
                await self.broadcast(payload, publish=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ws.broadcast.listener_error")
        finally:
            with suppress(Exception):
                await pubsub.aclose()
            self._pubsub = None

    async def _cleanup_redis(self) -> None:
        if self._subscriber is not None:
            with suppress(Exception):
                if hasattr(self._subscriber, "aclose"):
                    await self._subscriber.aclose()
                else:
                    await self._subscriber.close()
            self._subscriber = None
        if self._publisher is not None:
            with suppress(Exception):
                if hasattr(self._publisher, "aclose"):
                    await self._publisher.aclose()
                else:
                    await self._publisher.close()
            self._publisher = None


merchant_notifier = MerchantNotifier(get_settings())
