"""Focused tests for the Bingo house bot autofill controller."""

from __future__ import annotations

import random
import time
import unittest
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest import TestCase, mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin import service as admin_service
from app.bingo import house_bot, service as bingo_service, wallet
from app.bingo.dummy_names import DUMMY_FIRST_NAMES, pick_dummy_name
from app.bingo.house_bot import (
    BotIntent,
    build_claim_schedule,
    count_real_selectors,
)
from app.bingo.service import (
    apply_system_fee,
    compute_bingo_round_system_gain,
    system_fee_rate,
)
from app.bingo.redis_store import CardState, PlayerState, ReserveResult, RoomState
from app.db.database import Base
from app.models import BingoGame, BingoGameResult, User, WalletTransaction


class SystemGainFormulaTests(TestCase):
    """Fee tiers: ≤4 → 0%, 5–10 → 10%, 11+ → 20%."""

    def test_fee_tiers(self):
        self.assertEqual(system_fee_rate(4), Decimal("0"))
        self.assertEqual(system_fee_rate(5), Decimal("0.10"))
        self.assertEqual(system_fee_rate(10), Decimal("0.10"))
        self.assertEqual(system_fee_rate(11), Decimal("0.20"))
        self.assertEqual(system_fee_rate(15), Decimal("0.20"))

    def test_bot_win_gain_is_real_stakes_only(self):
        # 5 real + 10 bot × 10 ETB → gain 50 (no % cut).
        gain = compute_bingo_round_system_gain(5, 10, Decimal("10"), bot_won=True)
        self.assertEqual(gain, Decimal("50.00"))

    def test_bot_loss_gain_is_fee_minus_bot_stakes(self):
        # Pool 150, 20% fee → S=30; bot stakes 100 → gain −70.
        gain = compute_bingo_round_system_gain(5, 10, Decimal("10"), bot_won=False)
        self.assertEqual(gain, Decimal("-70.00"))
        prize, fee = apply_system_fee(Decimal("150"), 15)
        self.assertEqual(fee, Decimal("30.00"))
        self.assertEqual(prize, Decimal("120.00"))

    def test_no_bot_round_unchanged(self):
        # 6 boards → 10% of 60 = 6.
        gain = compute_bingo_round_system_gain(6, 0, Decimal("10"), bot_won=False)
        self.assertEqual(gain, Decimal("6.00"))
        _prize, fee = apply_system_fee(Decimal("60"), 6)
        self.assertEqual(gain, fee)


class BotWinSettleAccountingTests(unittest.IsolatedAsyncioTestCase):
    """Bot-only win: no BINGO_WIN; credit BINGO_BOT_SYSTEM_GAIN = real stakes."""

    async def test_bot_win_skips_prize_and_reports_real_stake_gain(self):
        bot_id = str(uuid.uuid4())
        human_id = str(uuid.uuid4())
        game_id = "MBGAIN01"
        room_id = "default"
        winning_grid = [
            [1, 2, 3, 4, 5],
            [16, 17, 18, 19, 20],
            [31, 32, None, 33, 34],
            [46, 47, 48, 49, 50],
            [61, 62, 63, 64, 65],
        ]
        # 1 human board + 2 bot boards, stake 10 → derash 30; bot wins.
        room = RoomState(
            room_id=room_id,
            name="Lobby",
            status="in_progress",
            board_price="10",
            max_boards=3,
            game_id=game_id,
            derash="30",
            round_players=3,
            drawn=[1, 2, 3, 4, 5],
        )
        room.players[bot_id] = PlayerState(
            user_id=bot_id, display_name="Bright Bot", connected=True
        )
        room.players[human_id] = PlayerState(
            user_id=human_id, display_name="Human", connected=True
        )
        room.cards["1"] = CardState(
            card_id="1", user_id=human_id,
            numbers=[
                [6, 7, 8, 9, 10],
                [16, 17, 18, 19, 20],
                [31, 32, None, 33, 34],
                [46, 47, 48, 49, 50],
                [61, 62, 63, 64, 65],
            ],
        )
        room.cards["7"] = CardState(
            card_id="7", user_id=bot_id, numbers=winning_grid
        )
        room.cards["8"] = CardState(
            card_id="8", user_id=bot_id,
            numbers=[
                [11, 12, 13, 14, 15],
                [21, 22, 23, 24, 25],
                [31, 32, None, 33, 34],
                [46, 47, 48, 49, 50],
                [61, 62, 63, 64, 65],
            ],
        )

        award_mock = mock.Mock()
        gain_mock = mock.Mock(return_value="110.00")
        finish_calls: list = []
        broadcasts: list[dict] = []

        @asynccontextmanager
        async def fake_lock(_room_id):
            yield

        def capture_finish(*args, **kwargs):
            finish_calls.append((args, kwargs))

        async def capture_broadcast(_r, msg):
            broadcasts.append(msg)

        with (
            mock.patch("app.bingo.service.room_lock", fake_lock),
            mock.patch("app.bingo.service.get_room", new=mock.AsyncMock(return_value=room)),
            mock.patch("app.bingo.service.save_room", new=mock.AsyncMock()),
            mock.patch("app.bingo.service.wallet.award_prizes", award_mock),
            mock.patch(
                "app.bingo.service.wallet.credit_bot_system_gain",
                gain_mock,
            ),
            mock.patch(
                "app.bingo.service.wallet.record_round_finish",
                side_effect=capture_finish,
            ),
            mock.patch(
                "app.bingo.service.manager.broadcast",
                new=mock.AsyncMock(side_effect=capture_broadcast),
            ),
            mock.patch(
                "app.bingo.service.broadcast_room_sync",
                new=mock.AsyncMock(),
            ),
            mock.patch(
                "app.bingo.house_bot.cached_bot_user_id",
                return_value=bot_id,
            ),
        ):
            settled, won = await bingo_service.auto_detect_winners(room_id)

        self.assertTrue(won)
        self.assertIsNotNone(settled)
        # No wallet prize when bot wins alone; system gain credited instead.
        award_mock.assert_not_called()
        gain_mock.assert_called_once_with(bot_id, Decimal("10"), game_id)
        self.assertTrue(finish_calls)
        args, _kwargs = finish_calls[0]
        # record_round_finish(game_id, plan, pattern, winner_count, system_fee,
        #                     public_names, system_gain, bot_won, real_stake, bot_stake)
        self.assertEqual(args[0], game_id)
        self.assertEqual(args[1], {})  # empty prize plan
        self.assertEqual(args[4], Decimal("30"))  # system_fee = full derash
        self.assertEqual(args[6], Decimal("10.00"))  # system_gain = 1 × 10
        self.assertTrue(args[7])  # bot_won
        self.assertEqual(args[8], Decimal("10"))
        self.assertEqual(args[9], Decimal("20"))

        game_over = next(m for m in broadcasts if m.get("type") == "game_over")
        self.assertEqual(game_over["system_gain"], "10.00")
        self.assertEqual(game_over["prize_pool"], "0")
        self.assertTrue(game_over["bot_won"])

    async def test_real_win_excludes_bot_from_prize_plan(self):
        bot_id = str(uuid.uuid4())
        human_id = str(uuid.uuid4())
        game_id = "MBREAL01"
        room_id = "default"
        winning_grid = [
            [1, 2, 3, 4, 5],
            [16, 17, 18, 19, 20],
            [31, 32, None, 33, 34],
            [46, 47, 48, 49, 50],
            [61, 62, 63, 64, 65],
        ]
        # 1 human + 2 bot, stake 10 → pool 30, 10% fee → prize 27; human wins.
        room = RoomState(
            room_id=room_id,
            name="Lobby",
            status="in_progress",
            board_price="10",
            max_boards=3,
            game_id=game_id,
            derash="30",
            round_players=3,
            drawn=[1, 2, 3, 4, 5],
        )
        room.players[bot_id] = PlayerState(
            user_id=bot_id, display_name="Bright Bot", connected=True
        )
        room.players[human_id] = PlayerState(
            user_id=human_id, display_name="Human", connected=True
        )
        room.cards["1"] = CardState(
            card_id="1", user_id=human_id, numbers=winning_grid
        )
        room.cards["7"] = CardState(
            card_id="7", user_id=bot_id,
            numbers=[
                [6, 7, 8, 9, 10],
                [16, 17, 18, 19, 20],
                [31, 32, None, 33, 34],
                [46, 47, 48, 49, 50],
                [61, 62, 63, 64, 65],
            ],
        )
        room.cards["8"] = CardState(
            card_id="8", user_id=bot_id,
            numbers=[
                [11, 12, 13, 14, 15],
                [21, 22, 23, 24, 25],
                [31, 32, None, 33, 34],
                [46, 47, 48, 49, 50],
                [61, 62, 63, 64, 65],
            ],
        )

        award_mock = mock.Mock(return_value={human_id: "130.00"})
        gain_mock = mock.Mock()
        finish_calls: list = []

        @asynccontextmanager
        async def fake_lock(_room_id):
            yield

        def capture_finish(*args, **kwargs):
            finish_calls.append((args, kwargs))

        with (
            mock.patch("app.bingo.service.room_lock", fake_lock),
            mock.patch("app.bingo.service.get_room", new=mock.AsyncMock(return_value=room)),
            mock.patch("app.bingo.service.save_room", new=mock.AsyncMock()),
            mock.patch("app.bingo.service.wallet.award_prizes", award_mock),
            mock.patch(
                "app.bingo.service.wallet.credit_bot_system_gain",
                gain_mock,
            ),
            mock.patch(
                "app.bingo.service.wallet.record_round_finish",
                side_effect=capture_finish,
            ),
            mock.patch(
                "app.bingo.service.manager.broadcast",
                new=mock.AsyncMock(),
            ),
            mock.patch(
                "app.bingo.service.broadcast_room_sync",
                new=mock.AsyncMock(),
            ),
            mock.patch(
                "app.bingo.house_bot.cached_bot_user_id",
                return_value=bot_id,
            ),
        ):
            settled, won = await bingo_service.auto_detect_winners(room_id)

        self.assertTrue(won)
        self.assertIsNotNone(settled)
        gain_mock.assert_not_called()
        award_mock.assert_called_once()
        plan = award_mock.call_args[0][0]
        self.assertEqual(set(plan.keys()), {human_id})
        self.assertNotIn(bot_id, plan)
        # 3 boards → 0% fee; full derash 30 to human.
        self.assertEqual(plan[human_id], Decimal("30.00"))
        args, _kwargs = finish_calls[0]
        self.assertFalse(args[7])  # bot_won
        # system_gain = fee 0 − bot stakes 20 = −20
        self.assertEqual(args[6], Decimal("-20.00"))
        self.assertEqual(args[8], Decimal("10"))
        self.assertEqual(args[9], Decimal("20"))


class DummyWinnerNameTests(TestCase):
    def test_pick_is_from_list_and_stable_for_round(self):
        bot_id = "bot-abc"
        round_a = "GAME001"
        round_b = "GAME002"
        name_a1 = pick_dummy_name(round_a, bot_id)
        name_a2 = pick_dummy_name(round_a, bot_id)
        name_b = pick_dummy_name(round_b, bot_id)
        self.assertIn(name_a1, DUMMY_FIRST_NAMES)
        self.assertEqual(name_a1, name_a2)
        # Different rounds may differ; if they collide, still valid — only
        # require stability within a round (asserted above).
        self.assertIn(name_b, DUMMY_FIRST_NAMES)
        self.assertEqual(len(DUMMY_FIRST_NAMES), 100)

    def test_different_bots_can_differ(self):
        round_id = "GAME999"
        a = pick_dummy_name(round_id, "bot-1")
        b = pick_dummy_name(round_id, "bot-2")
        self.assertIn(a, DUMMY_FIRST_NAMES)
        self.assertIn(b, DUMMY_FIRST_NAMES)


class BotConfigDefaultsTests(TestCase):
    def test_default_reservation_range_is_15_to_30(self):
        from app.core.config import Settings

        fields = Settings.model_fields
        self.assertEqual(fields["BINGO_BOT_MIN_BOARDS"].default, 15)
        self.assertEqual(fields["BINGO_BOT_MAX_BOARDS"].default, 30)
        self.assertLessEqual(
            fields["BINGO_BOT_MIN_BOARDS"].default,
            fields["BINGO_BOT_MAX_BOARDS"].default,
        )

    def test_pick_target_uses_random_range(self):
        rng = random.Random(0)
        targets = {house_bot._pick_target(400, 2, 10, rng) for _ in range(40)}
        self.assertTrue(targets)
        self.assertTrue(all(2 <= n <= 10 for n in targets))
        self.assertGreater(len(targets), 1)

        self.assertEqual(house_bot._pick_target(10, 20, 30, random.Random(1)), 10)
        self.assertEqual(house_bot._pick_target(400, 0, 0, random.Random(1)), 0)
        self.assertEqual(house_bot._pick_target(0, 2, 10, random.Random(1)), 0)
        self.assertEqual(house_bot._pick_target(400, 7, 7, random.Random(1)), 7)

    def test_default_reserve_range_is_15_to_30(self):
        with mock.patch.object(house_bot.settings, "BINGO_BOT_MIN_BOARDS", 15), mock.patch.object(
            house_bot.settings, "BINGO_BOT_MAX_BOARDS", 30
        ):
            self.assertEqual(house_bot.default_reserve_range(), (15, 30))

    def test_default_reserve_count_is_20(self):
        with mock.patch.object(house_bot.settings, "BINGO_BOT_MIN_BOARDS", 15), mock.patch.object(
            house_bot.settings, "BINGO_BOT_MAX_BOARDS", 30
        ):
            self.assertEqual(house_bot.default_reserve_count(), 20)

    def test_parse_enabled_flag(self):
        self.assertTrue(house_bot._parse_enabled_flag("1"))
        self.assertFalse(house_bot._parse_enabled_flag("0"))
        self.assertTrue(house_bot._parse_enabled_flag(b"true"))
        self.assertIsNone(house_bot._parse_enabled_flag(None))
        self.assertIsNone(house_bot._parse_enabled_flag("maybe"))

    def test_get_bot_enabled_falls_back_to_env(self):
        import asyncio

        async def run():
            redis = mock.AsyncMock()
            redis.get = mock.AsyncMock(return_value=None)
            with (
                mock.patch("app.bingo.house_bot.redis_store.get_redis", return_value=redis),
                mock.patch.object(house_bot.settings, "BINGO_BOT_ENABLED", False),
            ):
                enabled, source = await house_bot.get_bot_enabled()
            self.assertFalse(enabled)
            self.assertEqual(source, "env")

            redis.get = mock.AsyncMock(return_value="1")
            with mock.patch("app.bingo.house_bot.redis_store.get_redis", return_value=redis):
                enabled, source = await house_bot.get_bot_enabled()
            self.assertTrue(enabled)
            self.assertEqual(source, "redis")

        asyncio.run(run())

    def test_get_bot_reserve_range_falls_back_to_default(self):
        import asyncio

        async def run():
            redis = mock.AsyncMock()
            redis.get = mock.AsyncMock(return_value=None)
            with mock.patch("app.bingo.house_bot.redis_store.get_redis", return_value=redis):
                lo, hi, source = await house_bot.get_bot_reserve_range()
            self.assertEqual((lo, hi), house_bot.default_reserve_range())
            self.assertEqual(source, "default")

            async def fake_get(key):
                mapping = {
                    house_bot.BOT_RESERVE_MIN_KEY: "3",
                    house_bot.BOT_RESERVE_MAX_KEY: "9",
                }
                return mapping.get(key)

            redis.get = mock.AsyncMock(side_effect=fake_get)
            with mock.patch("app.bingo.house_bot.redis_store.get_redis", return_value=redis):
                lo, hi, source = await house_bot.get_bot_reserve_range()
            self.assertEqual((lo, hi), (3, 9))
            self.assertEqual(source, "redis")

            async def legacy_get(key):
                if key == house_bot.BOT_RESERVE_COUNT_KEY:
                    return "27"
                return None

            redis.get = mock.AsyncMock(side_effect=legacy_get)
            with mock.patch("app.bingo.house_bot.redis_store.get_redis", return_value=redis):
                lo, hi, source = await house_bot.get_bot_reserve_range()
            self.assertEqual((lo, hi), (27, 27))
            self.assertEqual(source, "legacy")

        asyncio.run(run())


class BotPublicWinnerSettleTests(unittest.IsolatedAsyncioTestCase):
    """Player-facing game_over uses a dummy name; user_id stays the bot."""

    async def test_bot_winner_public_name_is_dummy_stable(self):
        bot_id = str(uuid.uuid4())
        human_id = str(uuid.uuid4())
        game_id = "MBDUMMY1"
        room_id = "default"

        # Row 0 wins when 1..5 are drawn (center free unused).
        winning_grid = [
            [1, 2, 3, 4, 5],
            [16, 17, 18, 19, 20],
            [31, 32, None, 33, 34],
            [46, 47, 48, 49, 50],
            [61, 62, 63, 64, 65],
        ]
        room = RoomState(
            room_id=room_id,
            name="Lobby",
            status="in_progress",
            board_price="10",
            max_boards=2,
            game_id=game_id,
            derash="50",
            round_players=2,
            drawn=[1, 2, 3, 4, 5],
        )
        room.players[bot_id] = PlayerState(
            user_id=bot_id, display_name="Bright Bot", connected=True
        )
        room.players[human_id] = PlayerState(
            user_id=human_id, display_name="Human", connected=True
        )
        room.cards["7"] = CardState(
            card_id="7", user_id=bot_id, numbers=winning_grid
        )

        expected = pick_dummy_name(game_id, bot_id)
        broadcasts: list[dict] = []

        @asynccontextmanager
        async def fake_lock(_room_id):
            yield

        async def capture_broadcast(_r, msg):
            broadcasts.append(msg)

        with (
            mock.patch("app.bingo.service.room_lock", fake_lock),
            mock.patch("app.bingo.service.get_room", new=mock.AsyncMock(return_value=room)),
            mock.patch("app.bingo.service.save_room", new=mock.AsyncMock()),
            mock.patch(
                "app.bingo.service.wallet.award_prizes",
                return_value={bot_id: "100.00"},
            ),
            mock.patch(
                "app.bingo.service.wallet.credit_bot_system_gain",
                return_value="100.00",
            ),
            mock.patch("app.bingo.service.wallet.record_round_finish"),
            mock.patch(
                "app.bingo.service.manager.broadcast",
                new=mock.AsyncMock(side_effect=capture_broadcast),
            ),
            mock.patch(
                "app.bingo.service.broadcast_room_sync",
                new=mock.AsyncMock(),
            ),
            mock.patch(
                "app.bingo.house_bot.cached_bot_user_id",
                return_value=bot_id,
            ),
        ):
            settled, won = await bingo_service.auto_detect_winners(room_id)

        self.assertTrue(won)
        self.assertIsNotNone(settled)
        assert settled is not None
        self.assertEqual(settled.winner_id, bot_id)
        self.assertEqual(settled.winner_name, expected)
        self.assertNotEqual(settled.winner_name, "Bright Bot")
        self.assertIn(settled.winner_name, DUMMY_FIRST_NAMES)
        self.assertEqual(settled.winners[0]["user_id"], bot_id)
        self.assertEqual(settled.winners[0]["name"], expected)

        game_over = next(m for m in broadcasts if m.get("type") == "game_over")
        self.assertEqual(game_over["winner"], bot_id)
        self.assertEqual(game_over["winner_name"], expected)
        self.assertEqual(game_over["winners"][0]["user_id"], bot_id)
        self.assertEqual(game_over["winners"][0]["name"], expected)

        # Same round again → same public name.
        self.assertEqual(pick_dummy_name(game_id, bot_id), expected)


class ClaimScheduleTests(TestCase):
    def test_schedule_within_window_and_sums_to_target(self):
        rng = random.Random(42)
        lobby_started = 1_000_000.0
        target = 15
        schedule = build_claim_schedule(
            lobby_started,
            target,
            window_start=1.0,
            window_end=35.0,
            rng=rng,
        )
        self.assertTrue(schedule)
        total = sum(count for _at, count in schedule)
        self.assertEqual(total, target)
        for at, count in schedule:
            self.assertGreaterEqual(at, lobby_started + 1.0)
            self.assertLessEqual(at, lobby_started + 35.0)
            self.assertGreaterEqual(count, 1)
            self.assertLessEqual(count, 3)
        times = [at for at, _ in schedule]
        self.assertEqual(times, sorted(times))

    def test_zero_target_yields_empty_schedule(self):
        schedule = build_claim_schedule(
            0.0, 0, window_start=1.0, window_end=35.0, rng=random.Random(1)
        )
        self.assertEqual(schedule, [])


class RealSelectorSemanticsTests(TestCase):
    def test_threshold_counts_distinct_non_bot_board_holders(self):
        bot = "bot-1"
        board_map = {
            1: "u1",
            2: "u1",
            3: "u2",
            4: bot,
            5: bot,
        }
        self.assertEqual(count_real_selectors(board_map, bot), 2)
        self.assertEqual(count_real_selectors(board_map, None), 3)


class HouseBotIsolatedTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot_id = str(uuid.uuid4())
        self.room_id = "default"
        self.room = RoomState(
            room_id=self.room_id,
            name="Lobby",
            status="lobby",
            board_price="10",
            max_boards=2,
            lobby_ends_at=time.time() + 40,
        )
        self.room.players["human"] = PlayerState(
            user_id="human", display_name="Human", connected=True
        )

    async def _tick_with_mocks(self, **extra):
        board_map = extra.pop("board_map", {})
        intent = extra.pop("intent", None)
        reserve_count = extra.pop("reserve_count", 20)
        reserve_min = extra.pop("reserve_min", reserve_count)
        reserve_max = extra.pop("reserve_max", reserve_count)
        enabled = extra.pop("enabled", True)

        claimed: list[int] = []
        released: list[int] = []

        async def fake_claim(room_id, bot_user_id, board_id):
            claimed.append(board_id)
            board_map[board_id] = bot_user_id
            return ReserveResult.CLAIMED

        async def fake_release_all(room_id, bot_user_id):
            held = [b for b, u in list(board_map.items()) if u == bot_user_id]
            for b in held:
                del board_map[b]
            released.extend(held)
            return held

        with (
            mock.patch.object(house_bot, "settings") as settings,
            mock.patch(
                "app.bingo.house_bot.redis_store.get_room",
                new=mock.AsyncMock(return_value=self.room),
            ),
            mock.patch(
                "app.bingo.house_bot.redis_store.get_board_map",
                new=mock.AsyncMock(side_effect=lambda *_a, **_k: dict(board_map)),
            ),
            mock.patch.object(
                house_bot, "ensure_bot_user_async", new=mock.AsyncMock(return_value=self.bot_id)
            ),
            mock.patch.object(house_bot, "ensure_bot_funds", new=mock.AsyncMock()),
            mock.patch.object(house_bot, "_ensure_bot_in_room", new=mock.AsyncMock()),
            mock.patch.object(
                house_bot, "_acquire_tick_lock", new=mock.AsyncMock(return_value=True)
            ),
            mock.patch.object(house_bot, "_release_tick_lock", new=mock.AsyncMock()),
            mock.patch.object(
                house_bot,
                "get_bot_enabled",
                new=mock.AsyncMock(return_value=(enabled, "env")),
            ),
            mock.patch.object(
                house_bot,
                "get_bot_reserve_range",
                new=mock.AsyncMock(return_value=(reserve_min, reserve_max, "default")),
            ),
            mock.patch.object(
                house_bot, "load_intent", new=mock.AsyncMock(return_value=intent)
            ),
            mock.patch.object(house_bot, "save_intent", new=mock.AsyncMock()),
            mock.patch.object(house_bot, "clear_intent", new=mock.AsyncMock()),
            mock.patch.object(house_bot, "bot_claim_board", side_effect=fake_claim),
            mock.patch.object(house_bot, "bot_release_all", side_effect=fake_release_all),
            mock.patch.object(
                house_bot, "bot_release_board", new=mock.AsyncMock(return_value=True)
            ),
            mock.patch.object(house_bot, "_leave_if_present", new=mock.AsyncMock()),
            mock.patch.object(house_bot, "cached_bot_user_id", return_value=self.bot_id),
        ):
            settings.BINGO_BOT_ENABLED = True
            settings.BINGO_BOT_ROOM_ID = "default"
            settings.BINGO_BOT_MIN_BOARDS = 15
            settings.BINGO_BOT_MAX_BOARDS = 30
            settings.BINGO_BOT_REAL_PLAYER_THRESHOLD = 20
            settings.BINGO_BOT_CLAIM_WINDOW_START_SEC = 1.0
            settings.BINGO_BOT_CLAIM_WINDOW_END_SEC = 35.0
            settings.BINGO_LOBBY_SECONDS = 40
            settings.BINGO_BOARD_POOL_MAX = 400
            settings.BINGO_BOT_DISPLAY_NAME = "Bright Bot"

            now = extra.get("now")
            if now is None:
                ends = self.room.lobby_ends_at
                now = (ends - 20) if ends is not None else time.time()
            await house_bot.tick_room(self.room_id, now=now)

        return claimed, released, board_map

    async def test_claims_due_bursts_within_target(self):
        lobby_ends = self.room.lobby_ends_at
        lobby_started = lobby_ends - 40
        intent = BotIntent(
            round_key=str(lobby_ends),
            target=12,
            schedule=[
                [lobby_started + 2, 3],
                [lobby_started + 5, 3],
                [lobby_started + 8, 3],
                [lobby_started + 50, 3],
            ],
            phase="claiming",
            seed=1,
        )

        claimed, _released, board_map = await self._tick_with_mocks(
            intent=intent,
            board_map={},
            now=lobby_started + 10,
        )
        self.assertEqual(len(claimed), 9)
        self.assertEqual(len(board_map), 9)
        self.assertTrue(all(uid == self.bot_id for uid in board_map.values()))

    async def test_releases_when_real_selectors_exceed_threshold(self):
        lobby_ends = self.room.lobby_ends_at
        board_map = {i: f"u{i}" for i in range(1, 22)}
        board_map[100] = self.bot_id
        board_map[101] = self.bot_id
        intent = BotIntent(
            round_key=str(lobby_ends),
            target=15,
            schedule=[[lobby_ends - 30, 3]],
            phase="claiming",
            seed=1,
        )

        _claimed, released, board_map_after = await self._tick_with_mocks(
            intent=intent,
            board_map=board_map,
            # Near lock → flush all bot boards in one tick.
            now=lobby_ends - 3,
        )
        self.assertEqual(sorted(released), [100, 101])
        self.assertNotIn(100, board_map_after)
        self.assertNotIn(101, board_map_after)

    async def test_disabled_stops_claims_and_releases_lobby_boards(self):
        lobby_ends = self.room.lobby_ends_at
        board_map = {10: self.bot_id, 11: self.bot_id}
        self.room.players[self.bot_id] = PlayerState(
            user_id=self.bot_id, display_name="Bot", connected=True
        )
        intent = BotIntent(
            round_key=str(lobby_ends),
            target=15,
            schedule=[[lobby_ends - 30, 5]],
            phase="claiming",
            seed=1,
        )

        claimed, released, board_map_after = await self._tick_with_mocks(
            intent=intent,
            board_map=board_map,
            enabled=False,
            now=lobby_ends - 20,
        )
        self.assertEqual(claimed, [])
        self.assertEqual(sorted(released), [10, 11])
        self.assertEqual(board_map_after, {})

    async def test_disabled_leaves_in_progress_boards_alone(self):
        self.room.status = "in_progress"
        self.room.lobby_ends_at = None
        board_map = {10: self.bot_id, 11: self.bot_id}
        self.room.players[self.bot_id] = PlayerState(
            user_id=self.bot_id, display_name="Bot", connected=True
        )
        now = time.time()

        claimed, released, board_map_after = await self._tick_with_mocks(
            board_map=board_map,
            enabled=False,
            now=now,
        )
        self.assertEqual(claimed, [])
        self.assertEqual(released, [])
        self.assertEqual(sorted(board_map_after.keys()), [10, 11])

    async def test_enabled_allows_claims_under_existing_rules(self):
        lobby_ends = self.room.lobby_ends_at
        lobby_started = lobby_ends - 40
        intent = BotIntent(
            round_key=str(lobby_ends),
            target=6,
            schedule=[[lobby_started + 2, 3], [lobby_started + 4, 3]],
            phase="claiming",
            seed=1,
        )

        claimed, _released, board_map = await self._tick_with_mocks(
            intent=intent,
            board_map={},
            enabled=True,
            now=lobby_started + 10,
        )
        self.assertEqual(len(claimed), 6)
        self.assertEqual(len(board_map), 6)

    async def test_cannot_claim_taken_boards(self):
        taken = {7: "human"}
        with (
            mock.patch(
                "app.bingo.house_bot.redis_store.get_room",
                new=mock.AsyncMock(return_value=self.room),
            ),
            mock.patch(
                "app.bingo.house_bot.redis_store.get_board_map",
                new=mock.AsyncMock(return_value=taken),
            ),
            mock.patch(
                "app.bingo.house_bot.redis_store.reserve_board",
                new=mock.AsyncMock(return_value=ReserveResult.TAKEN),
            ) as reserve,
            mock.patch(
                "app.bingo.house_bot.asyncio.to_thread",
                new=mock.AsyncMock(return_value="1000"),
            ),
            mock.patch.object(house_bot, "ensure_bot_funds", new=mock.AsyncMock()),
            mock.patch(
                "app.bingo.house_bot.service.broadcast_board_delta",
                new=mock.AsyncMock(),
            ) as broadcast,
            mock.patch.object(house_bot, "settings") as settings,
        ):
            settings.BINGO_BOT_MAX_BOARDS = 30
            settings.BINGO_BOARD_POOL_MAX = 400
            self.room.players[self.bot_id] = PlayerState(
                user_id=self.bot_id, display_name="Bot", connected=True
            )
            code = await house_bot.bot_claim_board(self.room_id, self.bot_id, 7)
            self.assertEqual(code, ReserveResult.TAKEN)
            reserve.assert_awaited()
            broadcast.assert_not_awaited()

    async def test_claim_idempotent_already_mine(self):
        with (
            mock.patch(
                "app.bingo.house_bot.redis_store.get_room",
                new=mock.AsyncMock(return_value=self.room),
            ),
            mock.patch(
                "app.bingo.house_bot.redis_store.get_board_map",
                new=mock.AsyncMock(return_value={9: self.bot_id}),
            ),
            mock.patch(
                "app.bingo.house_bot.redis_store.reserve_board",
                new=mock.AsyncMock(return_value=ReserveResult.ALREADY_MINE),
            ),
            mock.patch(
                "app.bingo.house_bot.service.broadcast_board_delta",
                new=mock.AsyncMock(),
            ) as broadcast,
            mock.patch.object(house_bot, "settings") as settings,
        ):
            settings.BINGO_BOT_MAX_BOARDS = 30
            settings.BINGO_BOARD_POOL_MAX = 400
            self.room.players[self.bot_id] = PlayerState(
                user_id=self.bot_id, display_name="Bot", connected=True
            )
            code = await house_bot.bot_claim_board(self.room_id, self.bot_id, 9)
            self.assertEqual(code, ReserveResult.ALREADY_MINE)
            broadcast.assert_not_awaited()


class BotWalletAndAdminTests(TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        self.db = self.Session()
        self.bot = User(
            telegram_id=-777000001,
            username="bright_bingo_bot",
            first_name="Bright Bot",
            referral_code="BINGOBOT",
            balance=Decimal("10.00"),
            is_bot=True,
        )
        self.human = User(
            telegram_id=2,
            username="player",
            first_name="Player",
            referral_code="PLAYER",
            balance=Decimal("100.00"),
            is_bot=False,
        )
        self.db.add_all([self.bot, self.human])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _patch_session(self):
        def factory():
            session = self.Session()
            session.close = lambda: None  # type: ignore[method-assign]
            return session

        return mock.patch("app.bingo.wallet.SessionLocal", side_effect=factory)

    def test_ensure_bot_balance_topup_ledger(self):
        with self._patch_session():
            balance = wallet.ensure_bot_balance(str(self.bot.id))
        bot = self.Session().query(User).filter(User.id == self.bot.id).one()
        self.assertEqual(balance, str(bot.balance))
        self.assertGreaterEqual(bot.balance, Decimal("5000"))
        txs = (
            self.Session()
            .query(WalletTransaction)
            .filter(
                WalletTransaction.user_id == self.bot.id,
                WalletTransaction.transaction_type == wallet.BOT_TOPUP_TX_TYPE,
            )
            .all()
        )
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].reference_type, "BINGO_BOT")

    def test_admin_serialization_includes_is_bot(self):
        page = admin_service.list_users(self.db, None, "bot", 20, 0, "joined_desc")
        self.assertEqual(page["total"], 1)
        self.assertTrue(page["items"][0]["is_bot"])
        self.assertEqual(page["items"][0]["username"], "bright_bingo_bot")

        detail = admin_service.user_detail(self.db, self.bot.id)
        self.assertTrue(detail["profile"]["is_bot"])

        active = admin_service.list_users(self.db, None, "active", 20, 0, "joined_desc")
        self.assertTrue(all(not item["is_bot"] for item in active["items"]))

    def test_charge_stakes_and_award_prizes_for_bot(self):
        game_id = "MBTEST1"
        with self._patch_session():
            wallet.ensure_bot_balance(str(self.bot.id))
            paid = wallet.charge_stakes(
                {str(self.bot.id): Decimal("100.00")},
                game_id,
            )
            self.assertIn(str(self.bot.id), paid)
            prizes = wallet.award_prizes(
                {str(self.bot.id): Decimal("80.00")},
                game_id,
            )
            self.assertIn(str(self.bot.id), prizes)

        db = self.Session()
        stakes = db.query(WalletTransaction).filter(
            WalletTransaction.transaction_type == wallet.STAKE_TX_TYPE,
        ).count()
        wins = db.query(WalletTransaction).filter(
            WalletTransaction.transaction_type == wallet.WIN_TX_TYPE,
        ).count()
        self.assertEqual(stakes, 1)
        self.assertEqual(wins, 1)

    def test_bot_win_credits_real_stake_system_gain(self):
        """Bot win: balance rises by real_stake_total via BINGO_BOT_SYSTEM_GAIN."""
        game_id = "MBGAIN2"
        real_stakes = Decimal("50.00")
        bot_stakes = Decimal("100.00")
        with self._patch_session():
            wallet.ensure_bot_balance(str(self.bot.id))
            before = Decimal(
                self.Session().query(User).filter(User.id == self.bot.id).one().balance
            )
            wallet.charge_stakes(
                {
                    str(self.bot.id): bot_stakes,
                    str(self.human.id): real_stakes,
                },
                game_id,
            )
            after_stake = Decimal(
                self.Session().query(User).filter(User.id == self.bot.id).one().balance
            )
            self.assertEqual(after_stake, before - bot_stakes)

            # No BINGO_WIN on bot-win path — only system-gain credit.
            new_bal = wallet.credit_bot_system_gain(
                str(self.bot.id), real_stakes, game_id
            )
            self.assertEqual(Decimal(new_bal), after_stake + real_stakes)

        db = self.Session()
        gains = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.user_id == self.bot.id,
                WalletTransaction.transaction_type
                == wallet.BOT_SYSTEM_GAIN_TX_TYPE,
            )
            .all()
        )
        self.assertEqual(len(gains), 1)
        self.assertEqual(gains[0].amount, real_stakes)
        self.assertEqual(gains[0].reference_type, "BINGO_BOT")
        wins = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.user_id == self.bot.id,
                WalletTransaction.transaction_type == wallet.WIN_TX_TYPE,
            )
            .count()
        )
        self.assertEqual(wins, 0)
        human = db.query(User).filter(User.id == self.human.id).one()
        self.assertEqual(human.balance, Decimal("50.00"))  # 100 − 50 stake

    def test_real_win_bot_stakes_remain_spent_no_bot_win_credit(self):
        """Real win: bot keeps stake debit; no BINGO_WIN / system-gain to bot."""
        game_id = "MBLOSS1"
        bot_stakes = Decimal("100.00")
        with self._patch_session():
            wallet.ensure_bot_balance(str(self.bot.id))
            before = Decimal(
                self.Session().query(User).filter(User.id == self.bot.id).one().balance
            )
            wallet.charge_stakes({str(self.bot.id): bot_stakes}, game_id)
            # Human wins — prize goes to human only.
            wallet.award_prizes(
                {str(self.human.id): Decimal("80.00")},
                game_id,
            )

        db = self.Session()
        bot = db.query(User).filter(User.id == self.bot.id).one()
        self.assertEqual(bot.balance, before - bot_stakes)
        bot_wins = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.user_id == self.bot.id,
                WalletTransaction.transaction_type == wallet.WIN_TX_TYPE,
            )
            .count()
        )
        bot_gains = (
            db.query(WalletTransaction)
            .filter(
                WalletTransaction.user_id == self.bot.id,
                WalletTransaction.transaction_type
                == wallet.BOT_SYSTEM_GAIN_TX_TYPE,
            )
            .count()
        )
        self.assertEqual(bot_wins, 0)
        self.assertEqual(bot_gains, 0)

    def test_game_players_labels_bot(self):
        game = BingoGame(
            game_code="MBBOT01",
            room_id="default",
            status="finished",
            board_price=Decimal("10"),
            total_boards=5,
            total_players=1,
            derash=Decimal("50"),
        )
        self.db.add(game)
        self.db.flush()
        self.db.add(
            BingoGameResult(
                game_id=game.id,
                user_id=self.bot.id,
                boards_count=5,
                stake_amount=Decimal("50"),
                is_winner=True,
                amount_won=Decimal("40"),
                public_winner_name="Selam",
            )
        )
        self.db.commit()

        page = admin_service.game_players(self.db, "bingo", None, None, 20, 0)
        self.assertEqual(page["total"], 1)
        self.assertTrue(page["items"][0]["is_bot"])
        self.assertEqual(page["items"][0]["first_name"], "Bright Bot")
        self.assertEqual(page["items"][0]["turnover"], "50.00")

        summary = admin_service.game_summary(self.db, None, None)
        bingo = next(g for g in summary["games"] if g["game"] == "bingo")
        self.assertEqual(bingo["bot_turnover"], "50.00")
        self.assertEqual(bingo["bot_payouts"], "40.00")
        self.assertEqual(bingo["bot_pnl"], "-10.00")

    def test_player_history_uses_public_dummy_not_bright_bot(self):
        game = BingoGame(
            game_code="MBDUMMY2",
            room_id="default",
            status="finished",
            board_price=Decimal("10"),
            total_boards=2,
            total_players=2,
            derash=Decimal("20"),
            winner_count=1,
        )
        self.db.add(game)
        self.db.flush()
        dummy = pick_dummy_name("MBDUMMY2", str(self.bot.id))
        self.db.add_all(
            [
                BingoGameResult(
                    game_id=game.id,
                    user_id=self.bot.id,
                    boards_count=1,
                    stake_amount=Decimal("10"),
                    is_winner=True,
                    amount_won=Decimal("16"),
                    public_winner_name=dummy,
                ),
                BingoGameResult(
                    game_id=game.id,
                    user_id=self.human.id,
                    boards_count=1,
                    stake_amount=Decimal("10"),
                    is_winner=False,
                    amount_won=Decimal("0"),
                ),
            ]
        )
        self.db.commit()

        with self._patch_session():
            history = wallet.get_user_history(str(self.human.id), limit=5, offset=0)

        self.assertEqual(history["total"], 1)
        self.assertEqual(history["games"][0]["winner_names"], [dummy])
        self.assertNotIn("Bright Bot", history["games"][0]["winner_names"])

    def test_record_round_finish_persists_public_winner_name(self):
        game = BingoGame(
            game_code="MBPERSIST",
            room_id="default",
            status="in_progress",
            board_price=Decimal("10"),
            total_boards=1,
            total_players=1,
            derash=Decimal("10"),
        )
        self.db.add(game)
        self.db.flush()
        self.db.add(
            BingoGameResult(
                game_id=game.id,
                user_id=self.bot.id,
                boards_count=1,
                stake_amount=Decimal("10"),
            )
        )
        self.db.commit()

        dummy = pick_dummy_name("MBPERSIST", str(self.bot.id))
        with self._patch_session():
            wallet.record_round_finish(
                "MBPERSIST",
                {str(self.bot.id): Decimal("8.00")},
                "line",
                1,
                Decimal("2.00"),
                {str(self.bot.id): dummy},
            )

        row = (
            self.Session()
            .query(BingoGameResult)
            .filter(BingoGameResult.user_id == self.bot.id)
            .one()
        )
        self.assertTrue(row.is_winner)
        self.assertEqual(row.public_winner_name, dummy)
        self.assertNotEqual(row.public_winner_name, "Bright Bot")
