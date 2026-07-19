"""Focused tests for the Lotto house bot."""

from __future__ import annotations

import asyncio
import random
import uuid
from decimal import Decimal
from unittest import TestCase, mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.lotto import house_bot, service
from app.models.lotto_game import (
    LottoReservation,
    LottoReservationRequest,
    LottoRound,
    LottoWinner,
)
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction


class LottoBotPickTargetTests(TestCase):
    def test_pick_target_within_range(self):
        targets = {
            house_bot._pick_target(25, 2, 8, random.Random(i)) for i in range(50)
        }
        self.assertTrue(all(2 <= n <= 8 for n in targets))
        self.assertGreater(len(targets), 1)

    def test_pick_target_respects_free_headroom(self):
        # usable = free - 2 → with 4 free, usable=2, clamped into [2,2]
        self.assertEqual(house_bot._pick_target(4, 2, 8, random.Random(1)), 2)
        self.assertEqual(house_bot._pick_target(2, 2, 8, random.Random(1)), 0)
        self.assertEqual(house_bot._pick_target(25, 5, 5, random.Random(1)), 5)


class LottoBotIntegrationTests(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                WalletTransaction.__table__,
                LottoRound.__table__,
                LottoReservation.__table__,
                LottoReservationRequest.__table__,
                LottoWinner.__table__,
            ],
        )
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.bot = User(
            telegram_id=-777000001,
            username="bright_bingo_bot",
            first_name="Bright Bot",
            referral_code="BINGOBOT",
            is_bot=True,
            balance=Decimal("20000.00"),
        )
        self.player = User(
            telegram_id=200,
            first_name="Real",
            referral_code="REALONE",
            balance=Decimal("5000.00"),
        )
        self.db.add_all([self.bot, self.player])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_disabled_bot_makes_no_claims(self):
        with mock.patch.object(
            house_bot,
            "_inspect_open_round",
            return_value={
                "status": "open",
                "round_id": str(uuid.uuid4()),
                "round_uuid": uuid.uuid4(),
                "open": True,
                "free": list(range(1, 26)),
                "bot_held": [],
                "real_holders": 0,
                "occupied": 0,
            },
        ), mock.patch.object(
            house_bot, "get_bot_enabled", new=mock.AsyncMock(return_value=(False, "env"))
        ), mock.patch.object(
            house_bot, "_acquire_tick_lock", new=mock.AsyncMock(return_value=True)
        ), mock.patch.object(
            house_bot, "_release_tick_lock", new=mock.AsyncMock()
        ), mock.patch(
            "app.bingo.house_bot.ensure_bot_user_async",
            new=mock.AsyncMock(return_value=str(self.bot.id)),
        ), mock.patch.object(
            house_bot, "clear_intent", new=mock.AsyncMock()
        ), mock.patch.object(
            house_bot, "_release_numbers_sync"
        ) as release, mock.patch.object(
            house_bot, "_claim_numbers_sync"
        ) as claim:
            asyncio.run(house_bot.tick_stake(Decimal("10.00"), now=1_000.0))
            release.assert_not_called()
            claim.assert_not_called()

    def test_claims_within_configured_range(self):
        round_id = uuid.uuid4()
        captured: dict = {}

        async def fake_start(stake_key, rid, free_count, reserve_min, reserve_max, now):
            target = house_bot._pick_target(
                free_count, reserve_min, reserve_max, random.Random(42)
            )
            intent = house_bot.BotIntent(
                round_key=rid,
                target=target,
                schedule=[[now - 1, target]],
                phase="claiming",
                seed=42,
            )
            captured["target"] = target
            return intent

        def fake_claim(*, stake, bot_user_id, numbers):
            captured["numbers"] = list(numbers)
            return {"id": str(round_id), "occupied": len(numbers)}

        async def run():
            with (
                mock.patch.object(
                    house_bot, "get_bot_enabled", new=mock.AsyncMock(return_value=(True, "redis"))
                ),
                mock.patch.object(
                    house_bot,
                    "get_bot_reserve_range",
                    new=mock.AsyncMock(return_value=(3, 7, "redis")),
                ),
                mock.patch.object(
                    house_bot, "_acquire_tick_lock", new=mock.AsyncMock(return_value=True)
                ),
                mock.patch.object(house_bot, "_release_tick_lock", new=mock.AsyncMock()),
                mock.patch(
                    "app.bingo.house_bot.ensure_bot_user_async",
                    new=mock.AsyncMock(return_value=str(self.bot.id)),
                ),
                mock.patch.object(
                    house_bot,
                    "_inspect_open_round",
                    return_value={
                        "status": "open",
                        "round_id": str(round_id),
                        "round_uuid": round_id,
                        "open": True,
                        "free": list(range(1, 26)),
                        "bot_held": [],
                        "real_holders": 0,
                        "occupied": 0,
                    },
                ),
                mock.patch.object(house_bot, "load_intent", new=mock.AsyncMock(return_value=None)),
                mock.patch.object(house_bot, "_start_round_plan", side_effect=fake_start),
                mock.patch.object(house_bot, "save_intent", new=mock.AsyncMock()),
                mock.patch(
                    "app.bingo.house_bot.ensure_bot_funds", new=mock.AsyncMock()
                ),
                mock.patch.object(
                    house_bot, "_claim_numbers_sync", side_effect=fake_claim
                ),
            ):
                await house_bot.tick_stake(Decimal("10.00"), now=5_000.0)

        asyncio.run(run())
        self.assertIn("target", captured)
        self.assertGreaterEqual(captured["target"], 3)
        self.assertLessEqual(captured["target"], 7)
        self.assertEqual(len(captured["numbers"]), captured["target"])

    def test_bot_does_not_overlap_real_reserves(self):
        service.ensure_rooms(self.db)
        round_ = service.current_round(self.db, Decimal("10.00"))
        service.reserve(
            self.db,
            user_id=self.player.id,
            raw_stake="10",
            raw_numbers=list(range(1, 11)),
            request_id=uuid.uuid4(),
        )
        result = service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=[11, 12, 13],
            request_id=uuid.uuid4(),
        )
        self.assertEqual(sorted(result["numbers"]), [11, 12, 13])
        with self.assertRaises(service.LottoError):
            service.reserve(
                self.db,
                user_id=self.bot.id,
                raw_stake="10",
                raw_numbers=[10],
                request_id=uuid.uuid4(),
            )
        released = service.release_bot_numbers(
            self.db, round_id=round_.id, bot_user_id=self.bot.id, numbers=[11, 12]
        )
        self.assertEqual(released["released"], [11, 12])
        self.assertEqual(Decimal(released["refunded"]), Decimal("20.00"))

    def test_public_serialize_masks_bot_name(self):
        service.ensure_rooms(self.db)
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=[1, 2],
            request_id=uuid.uuid4(),
        )
        round_ = service.current_round(self.db, Decimal("10.00"))
        snap = service.serialize_round(self.db, round_)
        bot_rows = [r for r in snap["reservations"] if r["user_id"] == str(self.bot.id)]
        self.assertEqual(len(bot_rows), 2)
        for row in bot_rows:
            self.assertNotEqual(row["display_name"], "Bright Bot")
            self.assertEqual(row["label5"], row["display_name"][:5])

    def test_bot_reservations_get_distinct_display_names(self):
        service.ensure_rooms(self.db)
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(1, 9)),
            request_id=uuid.uuid4(),
        )
        round_ = service.current_round(self.db, Decimal("10.00"))
        snap = service.serialize_round(self.db, round_)
        bot_rows = [r for r in snap["reservations"] if r["user_id"] == str(self.bot.id)]
        names = [r["display_name"] for r in bot_rows]
        self.assertEqual(len(names), 8)
        self.assertEqual(len(set(names)), 8)
        labels = [r["label5"] for r in bot_rows]
        self.assertTrue(all(1 <= len(label) <= 5 for label in labels))
        # Persisted on the reservation row for stable multi-client snapshots.
        stored = {
            row.number: row.display_name
            for row in self.db.query(LottoReservation)
            .filter(LottoReservation.round_id == round_.id)
            .all()
        }
        self.assertEqual(len(set(stored.values())), 8)
