"""Reusable Redis Pub/Sub fan-out for cross-process WebSocket delivery.

Bingo keeps its own room-scoped listener; Aviator / Dama / Lotto use this
module for a single shared channel per game. Pattern:

1. Originating process delivers to its local sockets immediately.
2. It publishes the same payload tagged with ``_origin`` (and optionally
   ``_target`` / ``_exclude``).
3. Other processes receive the message and deliver locally; the origin
   drops the Redis echo so clients never see duplicates.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from app.bingo.redis_store import get_redis

logger = logging.getLogger(__name__)

ORIGIN_FIELD = "_origin"
TARGET_FIELD = "_target"
EXCLUDE_FIELD = "_exclude"

Dispatcher = Callable[[dict], Awaitable[None]]


class ChannelFanout:
    """Process-wide listener for one Redis Pub/Sub channel."""

    def __init__(self, channel: str, dispatch: Dispatcher) -> None:
        self.channel = channel
        self._dispatch = dispatch
        self._pubsub = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        redis = get_redis()
        self._pubsub = redis.pubsub()
        await self._pubsub.subscribe(self.channel)
        self._task = asyncio.create_task(self._listen(), name=f"fanout:{self.channel}")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(self.channel)
            except Exception:
                pass
            try:
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

    async def publish(self, message: dict) -> None:
        redis = get_redis()
        await redis.publish(self.channel, json.dumps(message))

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
                if "pubsub connection not set" not in str(exc):
                    logger.exception("%s fanout listener error", self.channel)
                    await asyncio.sleep(0.5)
                    continue
                logger.warning("%s fanout connection unset; resubscribing", self.channel)
                await self._resubscribe()
                continue
            except Exception:
                logger.exception("%s fanout listener error", self.channel)
                await asyncio.sleep(0.5)
                continue

            if message is None:
                continue

            data = message.get("data")
            if data is None:
                continue

            try:
                payload = json.loads(data)
            except (TypeError, ValueError):
                continue

            if not isinstance(payload, dict):
                continue

            try:
                await self._dispatch(payload)
            except Exception:
                logger.exception("%s fanout dispatch error", self.channel)

    async def _resubscribe(self) -> None:
        try:
            if self._pubsub is not None:
                try:
                    await self._pubsub.close()
                except Exception:
                    pass
            redis = get_redis()
            self._pubsub = redis.pubsub()
            await self._pubsub.subscribe(self.channel)
        except Exception:
            logger.exception("%s fanout resubscribe failed", self.channel)
            await asyncio.sleep(0.5)
