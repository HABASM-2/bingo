"""In-process WebSocket connection registry for Bingo rooms.

Delivery to *other* backend instances happens through Redis Pub/Sub
(``app.bingo.pubsub``); this manager only ever touches sockets that are
physically connected to this process.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.bingo import pubsub

# Tag every message this process publishes with its own id so that when the
# Redis Pub/Sub fanout echoes the message back to us we can recognise it as
# already-delivered-locally and skip re-delivering (see ``broadcast`` /
# ``app.bingo.service.dispatch_pubsub_event``).
ORIGIN_FIELD = "_origin"

Dispatcher = Callable[[str, dict], Awaitable[None]]


@dataclass
class ConnectionInfo:
    websocket: WebSocket
    user_id: str
    display_name: str
    # Unique per physical socket. When a user reopens the Mini App (new tab,
    # reconnect, React StrictMode double-mount) the newer socket replaces the
    # older one under the same user_id; the token lets us tell the two apart so
    # the *older* socket tearing down can never clobber the *newer* live one.
    token: str = ""
    last_seen: float = field(default_factory=time.time)


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, ConnectionInfo]] = {}
        self._lock = asyncio.Lock()
        self._pubsub_listener: pubsub.PubSubListener | None = None
        self._dispatch: Dispatcher | None = None
        self.instance_id = uuid.uuid4().hex

    def bind_pubsub(self, listener: pubsub.PubSubListener) -> None:
        self._pubsub_listener = listener

    def bind_dispatch(self, dispatch: Dispatcher) -> None:
        """Local delivery callback used by ``broadcast`` so events reach this
        instance's own sockets immediately, without depending on the Redis
        Pub/Sub round-trip (which can drop the very first event on a freshly
        subscribed room channel)."""

        self._dispatch = dispatch

    async def connect(
        self,
        room_id: str,
        user_id: str,
        display_name: str,
        websocket: WebSocket,
    ) -> str:
        """Register a socket and return its unique connection token. The token
        must be handed back to ``disconnect`` so a replaced/stale socket can
        never remove the newer live connection for the same user."""

        stale: ConnectionInfo | None = None
        token = uuid.uuid4().hex

        async with self._lock:
            room_connections = self._rooms.setdefault(room_id, {})
            stale = room_connections.get(user_id)

            room_connections[user_id] = ConnectionInfo(
                websocket=websocket,
                user_id=user_id,
                display_name=display_name,
                token=token,
            )

        if stale is not None:
            # A previous tab/session for this user was open - replace it.
            try:
                await stale.websocket.close(code=4409, reason="Replaced by new connection")
            except Exception:
                pass

        if self._pubsub_listener is not None:
            await self._pubsub_listener.subscribe(room_id)

        return token

    async def disconnect(
        self,
        room_id: str,
        user_id: str,
        token: str | None = None,
    ) -> bool:
        """Remove the *current* local connection for a user, but only if the
        supplied ``token`` matches the socket we currently hold (a stale socket
        being replaced passes a non-matching token and is ignored, so it can't
        tear down the live session).

        Returns True when the live connection was actually removed - the caller
        should then mark the player disconnected. Returns False for a no-op
        (stale socket, or user already gone)."""

        removed_current = False
        empty = False

        async with self._lock:
            room_connections = self._rooms.get(room_id)

            if not room_connections:
                return False

            conn = room_connections.get(user_id)

            if conn is not None and (token is None or conn.token == token):
                room_connections.pop(user_id, None)
                removed_current = True

            empty = len(room_connections) == 0

            if empty:
                self._rooms.pop(room_id, None)

        if empty and self._pubsub_listener is not None:
            await self._pubsub_listener.unsubscribe(room_id)

        return removed_current

    def touch(self, room_id: str, user_id: str) -> None:
        conn = self._rooms.get(room_id, {}).get(user_id)

        if conn is not None:
            conn.last_seen = time.time()

    def local_connection_count(self, room_id: str) -> int:
        return len(self._rooms.get(room_id, {}))

    def local_user_ids(self, room_id: str) -> list[str]:
        return list(self._rooms.get(room_id, {}).keys())

    async def send_personal(self, room_id: str, user_id: str, message: dict) -> None:
        conn = self._rooms.get(room_id, {}).get(user_id)

        if conn is None:
            return

        await self._safe_send(conn, message)

    async def deliver_local(self, room_id: str, message: dict) -> None:
        """Send a message to every connection this instance holds for the
        room. Called both for locally-produced events and for events fanned
        in from Redis Pub/Sub.

        Sends are dispatched concurrently (``asyncio.gather``) rather than in a
        serial ``await`` loop: with thousands of sockets in a lobby, a single
        slow/backpressured client must not delay ball/tick delivery to
        everyone else. Serialization is done once and reused across sockets."""

        connections = list(self._rooms.get(room_id, {}).values())

        if not connections:
            return

        payload = json.dumps(message)

        results = await asyncio.gather(
            *(
                asyncio.wait_for(conn.websocket.send_text(payload), timeout=2.0)
                for conn in connections
            ),
            return_exceptions=True,
        )

        dead_user_ids = [
            conn.user_id
            for conn, result in zip(connections, results)
            if isinstance(result, Exception)
        ]

        if dead_user_ids:
            async with self._lock:
                room_connections = self._rooms.get(room_id)

                if room_connections:
                    for user_id in dead_user_ids:
                        room_connections.pop(user_id, None)

    async def broadcast(self, room_id: str, message: dict) -> None:
        """Fan a message out to every connected client in the room.

        Delivery happens on two paths that never overlap:

        * **This instance** delivers to its own local sockets immediately via
          the bound dispatcher. Doing it inline (instead of waiting for the
          message to come back through Redis) guarantees no event is lost in
          the window right after a room channel is first subscribed, and keeps
          same-process latency to essentially zero.
        * **Other instances** get the message through Redis Pub/Sub. It is
          tagged with this process's ``instance_id`` so that when the fanout
          echoes it back here, ``dispatch_pubsub_event`` skips it (we already
          delivered locally) - preventing double sends while staying correct
          across a horizontally-scaled deployment.
        """

        if self._dispatch is not None:
            await self._dispatch(room_id, message)

        await pubsub.publish_event(room_id, {**message, ORIGIN_FIELD: self.instance_id})

    async def _safe_send(self, conn: ConnectionInfo, message: dict) -> None:
        try:
            await conn.websocket.send_text(json.dumps(message))
        except Exception:
            pass


manager = ConnectionManager()
