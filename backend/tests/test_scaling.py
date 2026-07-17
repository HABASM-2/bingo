"""Scaling / broadcast shape tests for Aviator, Bingo, and Lotto."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from app.aviator import store
from app.aviator.service import place_bet
from app.bingo.redis_store import PlayerState, RoomState, ROOM_TTL_SECONDS
from app.bingo import service as bingo_service
from app.core.redis_fanout import ORIGIN_FIELD
from app.lotto import game_loop as lotto_loop


class AviatorDeltaBroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def test_place_bet_broadcasts_delta_without_full_bets_array(self):
        rnd = store.LiveRound(
            round_id="r1",
            round_code="ABC123",
            phase="betting",
            betting_ends_at=9_999_999_999.0,
        )
        broadcasts: list[dict] = []

        async def fake_broadcast(msg, **_kwargs):
            broadcasts.append(msg)

        with (
            mock.patch("app.aviator.service.store.get_current_round", new=mock.AsyncMock(return_value=rnd)),
            mock.patch("app.aviator.service.store.save_round", new=mock.AsyncMock()),
            mock.patch("app.aviator.service._round_mutation_lock") as lock_ctx,
            mock.patch(
                "app.aviator.service.aviator_wallet.charge_bet",
                return_value="90.00",
            ),
            mock.patch("app.aviator.service.asyncio.to_thread", new=mock.AsyncMock(return_value="90.00")),
            mock.patch("app.aviator.service.hub.broadcast", side_effect=fake_broadcast),
        ):
            lock_ctx.return_value.__aenter__ = mock.AsyncMock(return_value=None)
            lock_ctx.return_value.__aexit__ = mock.AsyncMock(return_value=None)

            result = await place_bet("user-1", "Alice", "10", slot=0)

        self.assertEqual(result["type"], "bet_placed")
        self.assertIn("bet", result)
        self.assertNotIn("round", result)
        self.assertNotIn("bets", result)
        self.assertEqual(result["round_id"], "r1")
        self.assertEqual(len(broadcasts), 1)
        payload = broadcasts[0]
        self.assertEqual(payload["type"], "bet_placed")
        self.assertIn("bet", payload)
        self.assertNotIn("round", payload)
        self.assertNotIn("bets", payload)
        self.assertEqual(payload["bet"]["user_id"], "user-1")


class BingoLeavePruneTests(unittest.IsolatedAsyncioTestCase):
    async def test_lobby_leave_removes_player_and_releases_boards(self):
        room = RoomState(room_id="lobby1", name="Lobby")
        room.players["u1"] = PlayerState(user_id="u1", display_name="One")
        room.players["u2"] = PlayerState(user_id="u2", display_name="Two")
        room.status = "lobby"

        broadcasts: list[tuple[str, dict]] = []

        async def fake_broadcast(room_id, message):
            broadcasts.append((room_id, message))

        with (
            mock.patch("app.bingo.service.room_lock") as lock_ctx,
            mock.patch("app.bingo.service.get_room", new=mock.AsyncMock(side_effect=[room, room])),
            mock.patch("app.bingo.service.save_room", new=mock.AsyncMock()) as save,
            mock.patch(
                "app.bingo.service.redis_store.get_board_map",
                new=mock.AsyncMock(return_value={7: "u1", 8: "u2"}),
            ),
            mock.patch(
                "app.bingo.service.redis_store.release_all_boards",
                new=mock.AsyncMock(return_value=1),
            ) as release_all,
            mock.patch("app.bingo.service.manager.broadcast", side_effect=fake_broadcast),
            mock.patch(
                "app.bingo.service._board_economics",
                new=mock.AsyncMock(
                    return_value={
                        "selected_boards_count": 1,
                        "players_in_round": 1,
                        "projected_derash": "10",
                        "derash": "10",
                        "taken_boards": [8],
                    }
                ),
            ),
        ):
            lock_ctx.return_value.__aenter__ = mock.AsyncMock(return_value=None)
            lock_ctx.return_value.__aexit__ = mock.AsyncMock(return_value=None)

            result = await bingo_service.leave_room("lobby1", "u1")

        self.assertIsNotNone(result)
        self.assertNotIn("u1", result.players)
        self.assertIn("u2", result.players)
        release_all.assert_awaited()
        save.assert_awaited()
        types = [msg["type"] for _, msg in broadcasts]
        self.assertIn("player_left", types)
        self.assertIn("board_delta", types)
        self.assertEqual(ROOM_TTL_SECONDS, 24 * 60 * 60)

    async def test_reset_to_lobby_prunes_disconnected_players(self):
        room = RoomState(room_id="r2", name="Lobby")
        room.status = "finished"
        room.players["online"] = PlayerState(
            user_id="online", display_name="On", connected=True
        )
        room.players["gone"] = PlayerState(
            user_id="gone", display_name="Off", connected=False
        )

        with (
            mock.patch("app.bingo.service.redis_store.clear_boards", new=mock.AsyncMock()),
            mock.patch("app.bingo.service.room_lock") as lock_ctx,
            mock.patch("app.bingo.service.get_room", new=mock.AsyncMock(return_value=room)),
            mock.patch("app.bingo.service.save_room", new=mock.AsyncMock()),
            mock.patch("app.bingo.service.broadcast_room_sync", new=mock.AsyncMock()),
        ):
            lock_ctx.return_value.__aenter__ = mock.AsyncMock(return_value=None)
            lock_ctx.return_value.__aexit__ = mock.AsyncMock(return_value=None)

            result = await bingo_service.reset_to_lobby("r2")

        self.assertIsNotNone(result)
        self.assertIn("online", result.players)
        self.assertNotIn("gone", result.players)


class LottoLeaderLockTests(unittest.TestCase):
    def test_follower_does_not_run_process_when_lock_held(self):
        """Follower path sleeps and retries; _process is only called as leader."""
        calls = {"process": 0, "acquire": 0}

        async def acquire():
            calls["acquire"] += 1
            return calls["acquire"] > 2  # fail twice, then succeed once briefly

        async def renew():
            return False  # immediately lose leadership after acquire

        def process():
            calls["process"] += 1
            return [], {}, 0.01

        async def run_briefly():
            with (
                mock.patch.object(lotto_loop, "_try_acquire_leader", side_effect=acquire),
                mock.patch.object(lotto_loop, "_renew_leader", side_effect=renew),
                mock.patch.object(lotto_loop, "_release_leader", new=mock.AsyncMock()),
                mock.patch.object(lotto_loop, "_process", side_effect=process),
                mock.patch.object(lotto_loop, "FOLLOWER_POLL_SECONDS", 0.01),
            ):
                task = asyncio.create_task(lotto_loop._run())
                await asyncio.sleep(0.08)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.run(run_briefly())
        # Acquires happen while following; _process runs only inside leader body,
        # and renew fails immediately so process may be 0 or 1 depending on timing.
        self.assertGreaterEqual(calls["acquire"], 2)
        self.assertLessEqual(calls["process"], 1)


class FanoutOriginSmokeTests(unittest.TestCase):
    def test_origin_field_constant_matches_wire_tag(self):
        self.assertEqual(ORIGIN_FIELD, "_origin")


if __name__ == "__main__":
    unittest.main()
