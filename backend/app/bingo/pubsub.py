"""Redis Pub/Sub fanout so WebSocket broadcasts reach every backend instance,
not just the one that produced the event.

Local delivery to actual WebSocket connections is handled by
``app.bingo.manager.ConnectionManager`` - this module is purely the
cross-instance transport.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from app.bingo.redis_store import get_redis

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "bingo:room:"
CHANNEL_SUFFIX = ":events"

# Always subscribed for the lifetime of the listener so redis-py has an
# active pubsub connection before (and between) on-demand room subscriptions.
# Without at least one subscribe/psubscribe, get_message() raises:
#   RuntimeError: pubsub connection not set
_KEEPALIVE_CHANNEL = f"{CHANNEL_PREFIX}_keepalive{CHANNEL_SUFFIX}"

Dispatcher = Callable[[str, dict], Awaitable[None]]


def room_channel(room_id: str) -> str:
    return f"{CHANNEL_PREFIX}{room_id}{CHANNEL_SUFFIX}"


def room_id_from_channel(channel: str) -> str:
    return channel[len(CHANNEL_PREFIX):-len(CHANNEL_SUFFIX)]


async def publish_event(room_id: str, message: dict) -> None:
    redis = get_redis()
    await redis.publish(room_channel(room_id), json.dumps(message))


class PubSubListener:
    """Single process-wide listener. Subscribes to individual room channels
    on demand (as rooms get their first local connection) and fans incoming
    messages out via the provided dispatcher."""

    def __init__(self, dispatch: Dispatcher) -> None:
        self._dispatch = dispatch
        self._pubsub = None
        self._task: asyncio.Task | None = None
        self._subscribed_rooms: set[str] = set()

    async def start(self) -> None:
        redis = get_redis()
        self._pubsub = redis.pubsub()
        # Must subscribe before the listen loop: redis-py only opens the
        # pubsub connection on subscribe/psubscribe.
        await self._pubsub.subscribe(_KEEPALIVE_CHANNEL)
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

            try:
                await self._task
            except asyncio.CancelledError:
                pass

            self._task = None

        if self._pubsub is not None:
            await self._pubsub.close()
            self._pubsub = None

        self._subscribed_rooms.clear()

    async def subscribe(self, room_id: str) -> None:
        if self._pubsub is None or room_id in self._subscribed_rooms:
            return

        await self._pubsub.subscribe(room_channel(room_id))
        self._subscribed_rooms.add(room_id)

    async def unsubscribe(self, room_id: str) -> None:
        if self._pubsub is None or room_id not in self._subscribed_rooms:
            return

        await self._pubsub.unsubscribe(room_channel(room_id))
        self._subscribed_rooms.discard(room_id)

    async def _listen(self) -> None:
        assert self._pubsub is not None

        while True:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
            except asyncio.CancelledError:
                raise
            except RuntimeError as exc:
                # Connection dropped or never established — rebuild and
                # resubscribe so the loop stays healthy.
                if "pubsub connection not set" not in str(exc):
                    logger.exception("bingo pubsub listener error")
                    await asyncio.sleep(0.5)
                    continue

                logger.warning("bingo pubsub connection unset; resubscribing")
                await self._resubscribe()
                continue
            except Exception:
                logger.exception("bingo pubsub listener error")
                await asyncio.sleep(0.5)
                continue

            if message is None:
                continue

            channel = message.get("channel")
            data = message.get("data")

            if not channel or data is None or channel == _KEEPALIVE_CHANNEL:
                continue

            try:
                payload = json.loads(data)
            except (TypeError, ValueError):
                continue

            room_id = room_id_from_channel(channel)

            try:
                await self._dispatch(room_id, payload)
            except Exception:
                logger.exception("bingo pubsub dispatch error for room %s", room_id)

    async def _resubscribe(self) -> None:
        """Recreate the pubsub connection and restore keepalive + room subs."""
        try:
            if self._pubsub is not None:
                try:
                    await self._pubsub.close()
                except Exception:
                    pass

            redis = get_redis()
            self._pubsub = redis.pubsub()
            channels = [_KEEPALIVE_CHANNEL, *[room_channel(r) for r in self._subscribed_rooms]]
            await self._pubsub.subscribe(*channels)
        except Exception:
            logger.exception("bingo pubsub resubscribe failed")
            await asyncio.sleep(0.5)
