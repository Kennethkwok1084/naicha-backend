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

_QUEUE_STOP = object()
_BACKPRESSURE_CLOSE_CODE = 1013


class MerchantNotifier:
    """维护商户端 WebSocket 连接并支持跨实例广播订单事件。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._connection_queues: dict[WebSocket, asyncio.Queue[dict[str, Any]]] = {}
        self._sender_tasks: dict[WebSocket, asyncio.Task[None]] = {}
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
        async with self._lock:
            draining = list(self._connections)
        for connection in draining:
            await self.unregister(connection)

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
            queue = asyncio.Queue(maxsize=max(self._settings.merchant_ws_buffer_size, 1))
            self._connection_queues[websocket] = queue
            self._sender_tasks[websocket] = asyncio.create_task(self._drain_queue(websocket, queue))

    async def unregister(self, websocket: WebSocket) -> None:
        task: asyncio.Task[None] | None = None
        queue: asyncio.Queue[dict[str, Any]] | None = None
        async with self._lock:
            self._connections.discard(websocket)
            queue = self._connection_queues.pop(websocket, None)
            task = self._sender_tasks.pop(websocket, None)

        if queue is not None:
            self._signal_queue_stop(queue)

        current_task = asyncio.current_task()
        if task is not None and task is not current_task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

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
        stale: list[WebSocket] = []
        async with self._lock:
            if not self._connections:
                return

            for connection in self._connections:
                if connection.application_state != WebSocketState.CONNECTED:
                    stale.append(connection)
                    continue
                queue = self._connection_queues.get(connection)
                if queue is None:
                    stale.append(connection)
                    continue
                if queue.full():
                    with suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    stale.append(connection)

        for connection in stale:
            await self._disconnect_connection(connection, reason="buffer_overflow")

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

    async def _drain_queue(
        self,
        websocket: WebSocket,
        queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        timeout = max(float(self._settings.merchant_ws_send_timeout_seconds), 0.1)
        try:
            while True:
                message = await queue.get()
                if message is _QUEUE_STOP:
                    break
                try:
                    await asyncio.wait_for(websocket.send_json(message), timeout=timeout)
                except TimeoutError:
                    logger.warning("ws.broadcast.send_timeout", admin_conn=id(websocket))
                    await self._disconnect_connection(websocket, reason="send_timeout")
                    break
                except Exception:
                    logger.exception("ws.broadcast.send_failed")
                    await self._disconnect_connection(websocket, reason="send_failed")
                    break
        except asyncio.CancelledError:
            raise

    def _signal_queue_stop(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        while True:
            try:
                queue.put_nowait(_QUEUE_STOP)  # type: ignore[arg-type]
                break
            except asyncio.QueueFull:
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                continue

    async def _disconnect_connection(self, websocket: WebSocket, reason: str) -> None:
        with suppress(Exception):
            await websocket.close(code=_BACKPRESSURE_CLOSE_CODE, reason=reason)
        await self.unregister(websocket)

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
