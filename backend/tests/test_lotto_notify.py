"""Lotto pre-draw timing and Telegram / in-app notification filters."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import TestCase, mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.lotto import notifications, service
from app.models.lotto_game import (
    LottoReservation,
    LottoReservationRequest,
    LottoRound,
    LottoWinner,
)
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction


class _KeepAliveSession:
    """Wrap a test session so notifications code can call ``close()`` safely."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        return None


class LottoPreDrawNotifyTests(TestCase):
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
        self.user = User(
            telegram_id=201,
            first_name="Real",
            language_code="en",
            referral_code="LOTTO_REAL",
            balance=Decimal("10000.00"),
            is_bot=False,
        )
        self.other = User(
            telegram_id=202,
            first_name="Other",
            language_code="am",
            referral_code="LOTTO_OTHER",
            balance=Decimal("10000.00"),
            is_bot=False,
        )
        self.bot = User(
            telegram_id=203,
            first_name="HouseBot",
            referral_code="LOTTO_BOT",
            balance=Decimal("100000.00"),
            is_bot=True,
        )
        self.db.add_all([self.user, self.other, self.bot])
        self.db.commit()
        notifications.reset_local_claims()

    def tearDown(self):
        notifications.reset_local_claims()
        self.db.close()
        self.engine.dispose()

    def reserve(self, user, numbers, stake="10", request_id=None):
        return service.reserve(
            self.db,
            user_id=user.id,
            raw_stake=stake,
            raw_numbers=numbers,
            request_id=request_id or uuid.uuid4(),
        )

    def test_countdown_is_sixty_seconds_and_no_winners_before_deadline(self):
        self.assertEqual(service.COUNTDOWN_SECONDS, 60)
        result = self.reserve(self.user, list(range(1, 26)))
        room = result["round"]
        self.assertEqual(room["status"], "countdown")
        self.assertIsNotNone(room["draw_scheduled_at"])
        self.assertEqual(room["pre_draw_ends_at"], room["draw_scheduled_at"])
        self.assertEqual(room["winners"], [])

        round_id = uuid.UUID(room["id"])
        round_ = self.db.query(LottoRound).filter_by(id=round_id).one()
        started = service._aware(round_.countdown_started_at)
        scheduled = service._aware(round_.draw_scheduled_at)
        self.assertIsNotNone(started)
        self.assertIsNotNone(scheduled)
        delta = (scheduled - started).total_seconds()
        self.assertAlmostEqual(delta, 60.0, places=1)

        # Before deadline: settle must not create winners.
        self.assertFalse(service.settle_due_round(self.db, round_id))
        self.assertEqual(self.db.query(LottoWinner).count(), 0)
        self.db.refresh(round_)
        self.assertEqual(round_.status, "countdown")

    def test_real_stakers_exclude_bots(self):
        self.reserve(self.user, list(range(1, 11)))
        self.reserve(self.bot, list(range(11, 26)))
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        stakers = notifications.real_stakers_by_user(self.db, round_.id)
        self.assertEqual(set(stakers.keys()), {self.user.id})
        self.assertEqual(stakers[self.user.id][1], list(range(1, 11)))

    def test_claim_once_idempotent(self):
        async def run():
            key = "lotto:notify:test:idem"
            self.assertTrue(await notifications.claim_once(key))
            self.assertFalse(await notifications.claim_once(key))

        with mock.patch(
            "app.bingo.redis_store.get_redis",
            side_effect=RuntimeError("no redis"),
        ):
            asyncio.run(run())

    def test_pre_draw_skips_bots_and_lotto_connected_users(self):
        self.reserve(self.user, list(range(1, 11)))
        self.reserve(self.other, list(range(11, 21)))
        self.reserve(self.bot, list(range(21, 26)))
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_id = str(round_.id)

        sent_tg: list[dict] = []
        in_app: list[str] = []

        async def fake_tg(**kwargs):
            sent_tg.append(kwargs)
            return True

        async def fake_in_app(user_id, message):
            in_app.append(user_id)
            return True

        async def run():
            with (
                mock.patch.object(
                    notifications,
                    "SessionLocal",
                    return_value=_KeepAliveSession(self.db),
                ),
                mock.patch(
                    "app.lotto.notifications.lotto_hub.is_connected",
                    side_effect=lambda uid: uid == str(self.user.id),
                ),
                mock.patch(
                    "app.lotto.notifications.deliver_in_app_notice",
                    side_effect=fake_in_app,
                ),
                mock.patch(
                    "app.bot.notify.notify_lotto_pre_draw",
                    side_effect=fake_tg,
                ),
                mock.patch(
                    "app.bingo.redis_store.get_redis",
                    side_effect=RuntimeError("no redis"),
                ),
            ):
                await notifications.notify_pre_draw(round_id)
                # Second call must no-op (idempotent).
                await notifications.notify_pre_draw(round_id)

        asyncio.run(run())

        # user is on Lotto → skip; bot skipped; only other gets TG + in-app.
        self.assertEqual(len(sent_tg), 1)
        self.assertEqual(sent_tg[0]["telegram_id"], 202)
        self.assertEqual(sent_tg[0]["seconds"], 60)
        self.assertEqual(in_app, [str(self.other.id)])

    def test_results_notify_all_real_stakers_idempotent(self):
        self.reserve(self.user, list(range(1, 11)))
        self.reserve(self.other, list(range(11, 21)))
        self.reserve(self.bot, list(range(21, 26)))
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[1, 21, 11],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))

        winners = notifications.real_winners(self.db, round_.id)
        # Ranks 1 and 3 are real users; rank 2 is bot number 21.
        self.assertEqual([w.rank for w, _, _ in winners], [1, 3])
        self.assertEqual(
            {w.user_id for w, _, _ in winners},
            {self.user.id, self.other.id},
        )

        sent: list[dict] = []

        async def fake_results(**kwargs):
            sent.append(kwargs)
            return True

        async def fake_in_app(user_id, message):
            raise AssertionError("in-app winner toasts must not be sent")

        async def run():
            with (
                mock.patch.object(
                    notifications,
                    "SessionLocal",
                    return_value=_KeepAliveSession(self.db),
                ),
                mock.patch(
                    "app.lotto.notifications.lotto_hub.is_connected",
                    side_effect=lambda uid: uid == str(self.user.id),
                ),
                mock.patch(
                    "app.lotto.notifications.deliver_in_app_notice",
                    side_effect=fake_in_app,
                ),
                mock.patch(
                    "app.bot.notify.notify_lotto_results",
                    side_effect=fake_results,
                ),
                mock.patch(
                    "app.bingo.redis_store.get_redis",
                    side_effect=RuntimeError("no redis"),
                ),
            ):
                await notifications.notify_winners(str(round_.id))
                await notifications.notify_winners(str(round_.id))

        asyncio.run(run())
        # Both real stakers get Telegram; bot skipped. Idempotent → once each.
        # No in-app winner toasts (Telegram + in-game UI only).
        self.assertEqual(len(sent), 2)
        self.assertEqual({j["telegram_id"] for j in sent}, {201, 202})
        self.assertTrue(all(j["stake"] == "10.00" for j in sent))
        self.assertTrue(all("1st:" in j["summary"] for j in sent))
        self.assertTrue(all("2nd:" in j["summary"] for j in sent))
        self.assertTrue(all("3rd:" in j["summary"] for j in sent))


class LottoSystemGainFormulaTests(TestCase):
    """Unit fixtures: stake=10, pool=250 — system_gain = (real−prizes)−bot×0.04."""

    REAL = Decimal("30.00")
    BOT = Decimal("220.00")
    FIRST = Decimal("150.00")
    SECOND = Decimal("60.00")
    THIRD = Decimal("30.00")
    ALL_PRIZES = FIRST + SECOND + THIRD  # 240

    def test_gain_depends_on_real_prizes_and_bot_fee(self):
        cases = (
            (Decimal("0"), Decimal("21.20")),  # (30−0)−8.80
            (self.ALL_PRIZES, Decimal("-218.80")),  # (30−240)−8.80
            (self.FIRST, Decimal("-128.80")),  # (30−150)−8.80
            (self.THIRD, Decimal("-8.80")),  # (30−30)−8.80
            (self.FIRST + self.SECOND, Decimal("-188.80")),  # (30−210)−8.80
            (self.SECOND, Decimal("-38.80")),  # (30−60)−8.80
            (self.SECOND + self.THIRD, Decimal("-68.80")),  # (30−90)−8.80
        )
        for prizes, expected in cases:
            gain = service.compute_lotto_round_system_gain(
                self.REAL,
                prizes,
                bot_stake_total=self.BOT,
            )
            self.assertEqual(gain, expected)

    def test_user_example_bot_160_real_90_all_bot_win(self):
        # (90 − 0) − (160 × 0.04) = 90 − 6.40 = 83.60
        gain = service.compute_lotto_round_system_gain(
            Decimal("90.00"),
            Decimal("0"),
            bot_stake_total=Decimal("160.00"),
        )
        self.assertEqual(gain, Decimal("83.60"))

    def test_user_example_bot_170_real_80_real_prizes_60(self):
        # (80 − 60) − (170 × 0.04) = 20 − 6.80 = 13.20
        gain = service.compute_lotto_round_system_gain(
            Decimal("80.00"),
            Decimal("60.00"),
            bot_stake_total=Decimal("170.00"),
        )
        self.assertEqual(gain, Decimal("13.20"))

    def test_example_pool_250_bot_170_real_80_house_fee_separate(self):
        # system_gain with real_prizes=0: (80−0)−6.80 = 73.20
        # house_fee stays real×0.04 = 3.20 — not equal to system_gain
        gain = service.compute_lotto_round_system_gain(
            Decimal("80.00"),
            Decimal("0"),
            bot_stake_total=Decimal("170.00"),
        )
        self.assertEqual(gain, Decimal("73.20"))
        fee = service.compute_lotto_house_fee(
            pool=Decimal("250.00"),
            bot_stake_total=Decimal("170.00"),
            real_stake_total=Decimal("80.00"),
        )
        self.assertEqual(fee, Decimal("3.20"))
        self.assertNotEqual(fee, gain)

    def test_house_fee_bot_stakes_do_not_inflate(self):
        # real 130 + bot 120 → 130 × 0.04 = 5.20 (not 0.04×250=10).
        self.assertEqual(
            service.compute_lotto_house_fee(
                pool=Decimal("250.00"),
                prize_total=self.ALL_PRIZES,
                bot_stake_total=Decimal("120.00"),
                real_stake_total=Decimal("130.00"),
            ),
            Decimal("5.20"),
        )

    def test_house_fee_all_real_is_classic_four_percent_of_pool(self):
        self.assertEqual(
            service.compute_lotto_house_fee(
                pool=Decimal("250.00"),
                prize_total=self.ALL_PRIZES,
                bot_stake_total=Decimal("0"),
            ),
            Decimal("10.00"),
        )
        self.assertEqual(
            service.compute_lotto_house_fee(
                pool=Decimal("50.00"),
                prize_total=Decimal("48.00"),
                bot_stake_total=Decimal("0"),
            ),
            Decimal("2.00"),
        )

    def test_house_fee_partial_bot_fill(self):
        # real 30, bot 220 → 1.20
        self.assertEqual(
            service.compute_lotto_house_fee(
                pool=Decimal("250.00"),
                prize_total=self.ALL_PRIZES,
                bot_stake_total=self.BOT,
                real_stake_total=self.REAL,
            ),
            Decimal("1.20"),
        )
        # real 50, bot 200 → 2.00
        self.assertEqual(
            service.compute_lotto_house_fee(
                pool=Decimal("250.00"),
                prize_total=self.ALL_PRIZES,
                bot_stake_total=Decimal("200.00"),
                real_stake_total=Decimal("50.00"),
            ),
            Decimal("2.00"),
        )

    def test_all_bot_win_real_130_bot_120(self):
        # (130 − 0) − (120 × 0.04) = 130 − 4.80 = 125.20
        gain = service.compute_lotto_round_system_gain(
            Decimal("130.00"),
            Decimal("0"),
            bot_stake_total=Decimal("120.00"),
        )
        self.assertEqual(gain, Decimal("125.20"))

    def test_no_bot_room_gain_equals_classic_ggr(self):
        pool = Decimal("250.00")
        real_prizes = Decimal("240.00")  # 0.96 × pool
        fee = service.compute_lotto_house_fee(
            pool=pool,
            prize_total=real_prizes,
            bot_stake_total=Decimal("0"),
        )
        # No bots: system_gain = real_stakes − real_prizes (do not also − pool×0.04)
        gain = service.compute_lotto_round_system_gain(pool, real_prizes)
        self.assertEqual(fee, Decimal("10.00"))
        self.assertEqual(gain, Decimal("10.00"))
        same = service.compute_lotto_round_system_gain(
            pool,
            real_prizes,
            bot_stake_total=Decimal("0"),
            bot_prizes=Decimal("0"),
        )
        self.assertEqual(same, gain)

    def test_allows_negative_when_reals_win_big(self):
        # Small real stake, full ladder to reals, with bots filling the room.
        gain = service.compute_lotto_round_system_gain(
            Decimal("30.00"),
            Decimal("240.00"),
            bot_stake_total=Decimal("220.00"),
        )
        self.assertEqual(gain, Decimal("-218.80"))
        self.assertLess(gain, Decimal("0"))


class LottoSystemGainSettleTests(TestCase):
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
        self.user = User(
            telegram_id=301,
            first_name="Real",
            referral_code="GAIN_REAL",
            balance=Decimal("10000.00"),
            is_bot=False,
        )
        self.bot = User(
            telegram_id=302,
            first_name="Bright Bot",
            referral_code="GAIN_BOT",
            balance=Decimal("100000.00"),
            is_bot=True,
        )
        self.db.add_all([self.user, self.bot])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_exact_30_real_220_bot_all_bot_winners(self):
        """3 real + 22 bot: all bot win → gain = (30−0)−8.80 = 21.20."""
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 4)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(4, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[4, 5, 6],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertTrue(round_.bot_won)
        self.assertEqual(round_.real_stake_total, Decimal("30.00"))
        self.assertEqual(round_.bot_stake_total, Decimal("220.00"))
        self.assertEqual(round_.bot_prizes, Decimal("240.00"))
        self.assertEqual(round_.house_fee, Decimal("1.20"))
        self.assertEqual(round_.reserve_amount, Decimal("1.20"))
        self.assertEqual(round_.system_gain, Decimal("21.20"))

    def test_exact_30_real_all_three_real_winners(self):
        """3 real + 22 bot: all prizes to real → (30−240)−8.80 = −218.80."""
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 4)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(4, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[1, 2, 3],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertFalse(round_.bot_won)
        self.assertEqual(round_.real_stake_total, Decimal("30.00"))
        self.assertEqual(round_.bot_prizes, Decimal("0.00"))
        self.assertEqual(round_.system_gain, Decimal("-218.80"))
        self.assertEqual(round_.house_fee, Decimal("1.20"))

    def test_exact_30_real_only_first_real(self):
        """Only 1st real → (30−150)−8.80 = −128.80; prizes/wallets unchanged."""
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 4)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(4, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[1, 4, 5],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertEqual(round_.bot_prizes, Decimal("90.00"))
        self.assertEqual(round_.system_gain, Decimal("-128.80"))

    def test_exact_30_real_only_third_real(self):
        """Only 3rd real → (30−30)−8.80 = −8.80."""
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 4)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(4, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[4, 5, 1],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertEqual(round_.bot_prizes, Decimal("210.00"))
        self.assertEqual(round_.system_gain, Decimal("-8.80"))

    def test_exact_30_real_first_and_second_real(self):
        """1st+2nd real, 3rd bot → (30−210)−8.80 = −188.80."""
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 4)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(4, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[1, 2, 4],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertEqual(round_.bot_prizes, Decimal("30.00"))
        self.assertEqual(round_.system_gain, Decimal("-188.80"))

    def test_bot_only_prizes_persist_real_stakes_gain(self):
        """5 real (50) + 20 bot (200): bot wins all → (50−0)−8.00 = 42.00."""
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 6)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(6, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        bot_before = self.bot.balance
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[6, 7, 8],  # all bot numbers
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.db.refresh(self.bot)
        self.assertTrue(round_.bot_won)
        self.assertEqual(round_.real_stake_total, Decimal("50.00"))
        self.assertEqual(round_.bot_stake_total, Decimal("200.00"))
        self.assertEqual(round_.bot_prizes, Decimal("240.00"))
        self.assertEqual(round_.house_fee, Decimal("2.00"))
        self.assertEqual(round_.reserve_amount, Decimal("2.00"))
        self.assertEqual(round_.system_gain, Decimal("42.00"))
        # Bot still receives prize ladder credits (150+60+30) — gameplay unchanged.
        self.assertEqual(self.bot.balance, bot_before + Decimal("240.00"))
        gain_txs = (
            self.db.query(WalletTransaction)
            .filter(WalletTransaction.transaction_type == "LOTTO_BOT_SYSTEM_GAIN")
            .count()
        )
        self.assertEqual(gain_txs, 0)

    def test_real_first_bot_second_third(self):
        """5 real + 20 bot: real 1st → (50−150)−8.00 = −108.00; prizes still paid."""
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 6)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(6, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[1, 6, 7],  # real 1st + two bots
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertFalse(round_.bot_won)
        self.assertEqual(round_.real_stake_total, Decimal("50.00"))
        self.assertEqual(round_.bot_prizes, Decimal("90.00"))
        self.assertEqual(round_.house_fee, Decimal("2.00"))
        self.assertEqual(round_.reserve_amount, Decimal("2.00"))
        self.assertEqual(round_.system_gain, Decimal("-108.00"))

    def test_bot_first_real_second(self):
        """5 real + 20 bot: bot 1st + real 2nd + bot 3rd → (50−60)−8.00 = −18.00."""
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 6)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(6, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[6, 1, 7],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertFalse(round_.bot_won)
        self.assertEqual(round_.bot_prizes, Decimal("180.00"))
        self.assertEqual(round_.house_fee, Decimal("2.00"))
        self.assertEqual(round_.reserve_amount, Decimal("2.00"))
        self.assertEqual(round_.system_gain, Decimal("-18.00"))

    def test_no_bot_round_gain_equals_classic_reserve(self):
        filler = User(
            telegram_id=305,
            first_name="AllReal",
            referral_code="GAIN_ALLR",
            balance=Decimal("10000.00"),
            is_bot=False,
        )
        self.db.add(filler)
        self.db.commit()
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 13)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=filler.id,
            raw_stake="10",
            raw_numbers=list(range(13, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[1, 2, 3],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertFalse(round_.bot_won)
        self.assertEqual(round_.real_stake_total, Decimal("250.00"))
        self.assertEqual(round_.bot_stake_total, Decimal("0.00"))
        self.assertEqual(round_.bot_prizes, Decimal("0.00"))
        self.assertEqual(round_.house_fee, Decimal("10.00"))
        self.assertEqual(round_.reserve_amount, Decimal("10.00"))
        # No bots: (250−240)−0 = 10 ≡ residual; do not also subtract pool×0.04
        self.assertEqual(round_.system_gain, Decimal("10.00"))
        self.assertEqual(round_.system_gain, round_.reserve_amount)

    def test_real_130_bot_120_house_fee_five_twenty(self):
        """13 real + 12 bot: house_fee=5.20; all-bot win → gain=125.20."""
        filler = User(
            telegram_id=306,
            first_name="Real130",
            referral_code="GAIN_R130",
            balance=Decimal("10000.00"),
            is_bot=False,
        )
        self.db.add(filler)
        self.db.commit()
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 8)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=filler.id,
            raw_stake="10",
            raw_numbers=list(range(8, 14)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(14, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[14, 15, 16],  # all bot
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertTrue(round_.bot_won)
        self.assertEqual(round_.real_stake_total, Decimal("130.00"))
        self.assertEqual(round_.bot_stake_total, Decimal("120.00"))
        self.assertEqual(round_.house_fee, Decimal("5.20"))
        self.assertEqual(round_.reserve_amount, Decimal("5.20"))
        # (130 − 0) − (120 × 0.04) = 125.20
        self.assertEqual(round_.system_gain, Decimal("125.20"))

    def test_mixed_fill_room_bot_only_win(self):
        """15 real + 10 bot: bot-only win → (150−0)−4.00 = 146.00."""
        filler = User(
            telegram_id=304,
            first_name="Filler",
            referral_code="GAIN_FILL2",
            balance=Decimal("10000.00"),
            is_bot=False,
        )
        self.db.add(filler)
        self.db.commit()
        service.reserve(
            self.db,
            user_id=self.user.id,
            raw_stake="10",
            raw_numbers=list(range(1, 6)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=self.bot.id,
            raw_stake="10",
            raw_numbers=list(range(6, 16)),
            request_id=uuid.uuid4(),
        )
        service.reserve(
            self.db,
            user_id=filler.id,
            raw_stake="10",
            raw_numbers=list(range(16, 26)),
            request_id=uuid.uuid4(),
        )
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.draw_winning_numbers",
            return_value=[6, 7, 8],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        self.db.refresh(round_)
        self.assertTrue(round_.bot_won)
        self.assertEqual(round_.real_stake_total, Decimal("150.00"))
        self.assertEqual(round_.bot_stake_total, Decimal("100.00"))
        self.assertEqual(round_.bot_prizes, Decimal("240.00"))
        # house_fee stays real×0.04 = 6.00; system_gain is separate
        self.assertEqual(round_.house_fee, Decimal("6.00"))
        self.assertEqual(round_.reserve_amount, Decimal("6.00"))
        self.assertEqual(round_.system_gain, Decimal("146.00"))
