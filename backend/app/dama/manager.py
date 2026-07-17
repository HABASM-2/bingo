"""Dama hub — local sockets plus Redis Pub/Sub cross-process fan-out."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.core.redis_fanout import (
    EXCLUDE_FIELD,
    ORIGIN_FIELD,
    TARGET_FIELD,
    ChannelFanout,
)

CHANNEL = "dama:events"
SEND_TIMEOUT_SECONDS = 2.0

Dispatcher = Callable[[dict], Awaitable[None]]


@dataclass
class ConnectionInfo:
    websocket: WebSocket
    user_id: str
    display_name: str
    token: str = ""
    last_seen: float = field(default_factory=time.time)


class DamaHub:
    def __init__(self) -> None:
        self._by_user: dict[str, ConnectionInfo] = {}
        self._lock = asyncio.Lock()
        self.instance_id = uuid.uuid4().hex
        self._fanout: ChannelFanout | None = None
        self._dispatch: Dispatcher | None = None

    def bind_fanout(self, fanout: ChannelFanout) -> None:
        self._fanout = fanout

    def bind_dispatch(self, dispatch: Dispatcher) -> None:
        self._dispatch = dispatch

    async def connect(
        self,
        user_id: str,
        display_name: str,
        websocket: WebSocket,
    ) -> str:
        stale: ConnectionInfo | None = None
        token = uuid.uuid4().hex

        async with self._lock:
            stale = self._by_user.get(user_id)
            self._by_user[user_id] = ConnectionInfo(
                websocket=websocket,
                user_id=user_id,
                display_name=display_name,
                token=token,
            )

        if stale is not None:
            try:
                await stale.websocket.close(code=4409, reason="Replaced by new connection")
            except Exception:
                pass

        return token

    async def disconnect(self, user_id: str, token: str | None = None) -> bool:
        async with self._lock:
            conn = self._by_user.get(user_id)
            if conn is None:
                return False
            if token is not None and conn.token != token:
                return False
            self._by_user.pop(user_id, None)
            return True

    def touch(self, user_id: str) -> None:
        conn = self._by_user.get(user_id)
        if conn is not None:
            conn.last_seen = time.time()

    def online_user_ids(self) -> list[str]:
        return list(self._by_user.keys())

    def is_connected(self, user_id: str) -> bool:
        return user_id in self._by_user

    async def _send_local(self, user_id: str, message: dict) -> bool:
        conn = self._by_user.get(user_id)
        if conn is None:
            return False
        try:
            await asyncio.wait_for(
                conn.websocket.send_text(json.dumps(message)),
                timeout=SEND_TIMEOUT_SECONDS,
            )
            return True
        except Exception:
            await self.disconnect(user_id, conn.token)
            return False

    async def send(self, user_id: str, message: dict) -> bool:
        """Deliver to ``user_id`` on this process and fan out for other workers.

        Returns True when the socket is local *or* the message was published
        for another worker (peer may not be on this process).
        """
        delivered = await self._send_local(user_id, message)
        if self._fanout is not None:
            await self._fanout.publish(
                {
                    **message,
                    ORIGIN_FIELD: self.instance_id,
                    TARGET_FIELD: user_id,
                }
            )
            return True
        return delivered

    async def deliver_local(self, message: dict, *, exclude: str | None = None) -> None:
        connections = [
            c for uid, c in self._by_user.items() if exclude is None or uid != exclude
        ]
        if not connections:
            return
        payload = json.dumps(message)
        results = await asyncio.gather(
            *(
                asyncio.wait_for(
                    c.websocket.send_text(payload),
                    timeout=SEND_TIMEOUT_SECONDS,
                )
                for c in connections
            ),
            return_exceptions=True,
        )
        dead = [
            c.user_id
            for c, result in zip(connections, results)
            if isinstance(result, Exception)
        ]
        for user_id in dead:
            await self.disconnect(user_id)

    async def broadcast(self, message: dict, *, exclude: str | None = None) -> None:
        if self._dispatch is not None:
            await self._dispatch({**message, EXCLUDE_FIELD: exclude} if exclude else message)
        else:
            await self.deliver_local(message, exclude=exclude)

        if self._fanout is not None:
            wire = {**message, ORIGIN_FIELD: self.instance_id}
            if exclude is not None:
                wire[EXCLUDE_FIELD] = exclude
            await self._fanout.publish(wire)


async def dispatch_fanout_event(message: dict) -> None:
    if message.pop(ORIGIN_FIELD, None) == hub.instance_id:
        return
    target = message.pop(TARGET_FIELD, None)
    exclude = message.pop(EXCLUDE_FIELD, None)
    if target:
        await hub._send_local(target, message)
        return
    await hub.deliver_local(message, exclude=exclude)


hub = DamaHub()
