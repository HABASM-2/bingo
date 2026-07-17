"""Lotto hub — local sockets plus Redis Pub/Sub cross-process fan-out."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable

from fastapi import WebSocket

from app.core.redis_fanout import (
    ORIGIN_FIELD,
    TARGET_FIELD,
    ChannelFanout,
)

CHANNEL = "lotto:events"
SEND_TIMEOUT_SECONDS = 2.0

Dispatcher = Callable[[dict], Awaitable[None]]


class LottoHub:
    def __init__(self) -> None:
        self._connections: dict[str, tuple[str, WebSocket]] = {}
        self._lock = asyncio.Lock()
        self.instance_id = uuid.uuid4().hex
        self._fanout: ChannelFanout | None = None
        self._dispatch: Dispatcher | None = None

    def bind_fanout(self, fanout: ChannelFanout) -> None:
        self._fanout = fanout

    def bind_dispatch(self, dispatch: Dispatcher) -> None:
        self._dispatch = dispatch

    async def connect(self, user_id: str, websocket: WebSocket) -> str:
        token = uuid.uuid4().hex
        async with self._lock:
            self._connections[token] = (user_id, websocket)
        return token

    async def disconnect(self, token: str) -> None:
        async with self._lock:
            self._connections.pop(token, None)

    async def _send_user_local(self, user_id: str, message: dict) -> None:
        payload = json.dumps(message)
        targets = [
            (token, websocket)
            for token, (uid, websocket) in list(self._connections.items())
            if uid == user_id
        ]
        if not targets:
            return
        results = await asyncio.gather(
            *(
                asyncio.wait_for(socket.send_text(payload), timeout=SEND_TIMEOUT_SECONDS)
                for _, socket in targets
            ),
            return_exceptions=True,
        )
        dead = [
            token
            for (token, _), result in zip(targets, results)
            if isinstance(result, Exception)
        ]
        if dead:
            async with self._lock:
                for token in dead:
                    self._connections.pop(token, None)

    async def send_user(self, user_id: str, message: dict) -> None:
        await self._send_user_local(user_id, message)
        if self._fanout is not None:
            await self._fanout.publish(
                {
                    **message,
                    ORIGIN_FIELD: self.instance_id,
                    TARGET_FIELD: user_id,
                }
            )

    async def deliver_local(self, message: dict) -> None:
        payload = json.dumps(message)
        targets = list(self._connections.items())
        if not targets:
            return
        results = await asyncio.gather(
            *(
                asyncio.wait_for(socket.send_text(payload), timeout=SEND_TIMEOUT_SECONDS)
                for _, (_, socket) in targets
            ),
            return_exceptions=True,
        )
        dead = [
            token
            for (token, _), result in zip(targets, results)
            if isinstance(result, Exception)
        ]
        if dead:
            async with self._lock:
                for token in dead:
                    self._connections.pop(token, None)

    async def broadcast(self, message: dict) -> None:
        if self._dispatch is not None:
            await self._dispatch(message)
        else:
            await self.deliver_local(message)

        if self._fanout is not None:
            await self._fanout.publish({**message, ORIGIN_FIELD: self.instance_id})


async def dispatch_fanout_event(message: dict) -> None:
    if message.pop(ORIGIN_FIELD, None) == hub.instance_id:
        return
    target = message.pop(TARGET_FIELD, None)
    if target:
        await hub._send_user_local(target, message)
        return
    await hub.deliver_local(message)


hub = LottoHub()
