from datetime import timedelta
from decimal import Decimal
from unittest import TestCase, mock
import uuid

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.lotto import service
from app.models.lotto_game import (
    LottoReservation,
    LottoReservationRequest,
    LottoRound,
    LottoWinner,
)
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction


class LottoTests(TestCase):
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
            telegram_id=101,
            first_name="One",
            referral_code="LOTTO_ONE",
            balance=Decimal("10000.00"),
        )
        self.other = User(
            telegram_id=102,
            first_name="Two",
            referral_code="LOTTO_TWO",
            balance=Decimal("1000.00"),
        )
        self.db.add_all([self.user, self.other])
        self.db.commit()

    def tearDown(self):
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

    def test_number_validation_and_duplicates(self):
        for values in ([], [0], [26], [1, 1], list(range(1, 27))):
            with self.assertRaises(service.LottoError):
                service.validate_numbers(values)
        self.assertEqual(service.validate_numbers(list(range(1, 26))), list(range(1, 26)))

    def test_one_player_can_reserve_all_twenty_five_and_room_fills_once(self):
        request_id = uuid.uuid4()
        result = self.reserve(self.user, list(range(1, 26)), request_id=request_id)
        self.assertEqual(result["round"]["status"], "countdown")
        self.assertEqual(result["round"]["occupied"], 25)
        self.assertEqual(result["round"]["capacity"], 25)
        self.assertEqual(self.user.balance, Decimal("9750.00"))
        replay = self.reserve(
            self.user, list(range(1, 26)), request_id=request_id
        )
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.db.query(WalletTransaction).count(), 1)

    def test_any_occupied_number_causes_atomic_failure_and_no_charge(self):
        self.reserve(self.user, [1])
        before = self.other.balance
        with self.assertRaises(service.LottoError):
            self.reserve(self.other, [1, 2])
        self.db.refresh(self.other)
        self.assertEqual(self.other.balance, before)
        self.assertIsNone(
            self.db.query(LottoReservation).filter_by(number=2).first()
        )

    def test_database_unique_constraint_is_final_race_protection(self):
        first = self.reserve(self.user, [7])
        round_id = uuid.UUID(first["round"]["id"])
        self.db.add(
            LottoReservation(
                round_id=round_id,
                user_id=self.other.id,
                request_id=uuid.uuid4(),
                number=7,
                stake=Decimal("10"),
            )
        )
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(
            self.db.query(LottoReservation).filter_by(number=7).count(), 1
        )

    def test_insufficient_balance_creates_no_rows_or_ledger(self):
        self.other.balance = Decimal("5.00")
        self.db.commit()
        with self.assertRaises(service.LottoError):
            self.reserve(self.other, [1])
        self.assertEqual(self.db.query(LottoReservation).count(), 0)
        self.assertEqual(self.db.query(WalletTransaction).count(), 0)

    def test_exact_math_for_every_stake(self):
        # pool = stake * 25; 60% / 24% / 12% / 4% with residual to system
        expected = {
            10: ("250.00", "150.00", "60.00", "30.00", "10.00"),
            25: ("625.00", "375.00", "150.00", "75.00", "25.00"),
            50: ("1250.00", "750.00", "300.00", "150.00", "50.00"),
            100: ("2500.00", "1500.00", "600.00", "300.00", "100.00"),
        }
        for stake, values in expected.items():
            pool, first, second, third, system = service.prize_math(Decimal(stake))
            self.assertEqual(
                tuple(str(value) for value in (pool, first, second, third, system)),
                values,
            )
            self.assertEqual(first + second + third + system, pool)

    def test_unique_winners_same_owner_payout_and_retry_safety(self):
        result = self.reserve(self.user, list(range(1, 26)))
        round_id = uuid.UUID(result["round"]["id"])
        round_ = self.db.query(LottoRound).filter_by(id=round_id).one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.secrets.SystemRandom.sample",
            return_value=[1, 2, 3],
        ) as sample_mock:
            self.assertTrue(service.settle_due_round(self.db, round_id))
            sample_mock.assert_called_once()
            args = sample_mock.call_args.args
            population = args[0] if isinstance(args[0], (list, tuple, set)) else args[1]
            self.assertEqual(set(population), set(range(1, 26)))
        self.db.refresh(self.user)
        self.assertEqual(self.db.query(LottoWinner).count(), 3)
        self.assertEqual(
            {winner.rank for winner in self.db.query(LottoWinner).all()},
            {1, 2, 3},
        )
        self.assertEqual(
            {winner.number for winner in self.db.query(LottoWinner).all()},
            {1, 2, 3},
        )
        # 10000 - 250 + 150 + 60 + 30 = 9990
        self.assertEqual(self.user.balance, Decimal("9990.00"))
        winners = {w.rank: w for w in self.db.query(LottoWinner).all()}
        self.assertEqual(winners[1].prize, Decimal("150.00"))
        self.assertEqual(winners[2].prize, Decimal("60.00"))
        self.assertEqual(winners[3].prize, Decimal("30.00"))
        tx_count = self.db.query(WalletTransaction).count()
        self.assertFalse(service.settle_due_round(self.db, round_id))
        self.db.refresh(self.user)
        self.assertEqual(self.user.balance, Decimal("9990.00"))
        self.assertEqual(self.db.query(WalletTransaction).count(), tx_count)

    def test_history_is_user_isolated_and_paginated(self):
        result = self.reserve(self.user, list(range(1, 26)))
        round_id = uuid.UUID(result["round"]["id"])
        round_ = self.db.query(LottoRound).filter_by(id=round_id).one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.secrets.SystemRandom.sample",
            return_value=[1, 2, 3],
        ):
            service.settle_due_round(self.db, round_id)
        round_ = self.db.query(LottoRound).filter_by(id=round_id).one()
        round_.drawing_started_at = service.utcnow() - timedelta(
            seconds=service.DRAW_COMPLETE_SECONDS + 1
        )
        self.db.commit()
        self.assertTrue(service.complete_due_round(self.db, round_id))
        page = service.history(self.db, self.user.id, 10, 0)
        other_page = service.history(self.db, self.other.id, 10, 0)
        self.assertEqual(page["total"], 1)
        item = page["items"][0]
        self.assertEqual(item["numbers"], list(range(1, 26)))
        self.assertEqual(len(item["winners"]), 3)
        self.assertEqual(item["total_paid"], "250.00")
        self.assertEqual(item["total_prize"], "240.00")
        self.assertEqual(item["net"], "-10.00")
        self.assertEqual(
            [(w["rank"], w["prize"]) for w in item["winners"]],
            [(1, "150.00"), (2, "60.00"), (3, "30.00")],
        )
        self.assertEqual(other_page["total"], 0)
        self.assertEqual(service.history(self.db, self.user.id, 10, 1)["items"], [])

    def test_snapshot_has_public_owners_but_no_balance(self):
        self.reserve(self.user, [4])
        payload = service.snapshot(self.db)
        self.assertNotIn("balance", str(payload).lower())
        room = next(item for item in payload["rooms"] if item["stake"] == "10.00")
        self.assertEqual(room["capacity"], 25)
        self.assertEqual(room["total_pool"], "250.00")
        self.assertEqual(room["first_prize"], "150.00")
        self.assertEqual(room["second_prize"], "60.00")
        self.assertEqual(room["third_prize"], "30.00")
        self.assertEqual(room["reserve_amount"], "10.00")
        self.assertEqual(room["reservations"][0]["display_name"], "One")

    def test_winners_drawn_from_reserved_numbers_only(self):
        self.reserve(self.user, list(range(1, 26)))
        round_ = self.db.query(LottoRound).filter_by(status="countdown").one()
        round_.draw_scheduled_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with mock.patch(
            "app.lotto.service.secrets.SystemRandom.sample",
            side_effect=lambda *args: sorted(args[-2])[: args[-1]],
        ):
            self.assertTrue(service.settle_due_round(self.db, round_.id))
        numbers = {w.number for w in self.db.query(LottoWinner).all()}
        self.assertEqual(numbers, {1, 2, 3})
