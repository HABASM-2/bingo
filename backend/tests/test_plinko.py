from decimal import Decimal, ROUND_HALF_UP
from unittest import TestCase, mock
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.plinko_game import PlinkoPlay
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction
from app.plinko import service
from app.plinko.config import (
    ALLOWED_RISKS,
    ALLOWED_ROWS,
    MULTIPLIER_TABLES,
    expected_rtp,
)


class PlinkoRuleTests(TestCase):
    def test_tables_are_symmetric_correct_length_and_target_rtp(self):
        for risk in ALLOWED_RISKS:
            for rows in ALLOWED_ROWS:
                table = MULTIPLIER_TABLES[risk][rows]
                self.assertEqual(len(table), rows + 1)
                self.assertEqual(table, tuple(reversed(table)))
                rtp = expected_rtp(rows, risk)
                self.assertGreaterEqual(rtp, Decimal("0.9700"))
                self.assertLessEqual(rtp, Decimal("0.9950"))

    def test_medium_16_has_clean_player_facing_bins(self):
        table = MULTIPLIER_TABLES["medium"][16]
        self.assertEqual(table[8], Decimal("0.40"))
        self.assertEqual(table[6], Decimal("1.00"))
        self.assertEqual(table[10], Decimal("1.00"))

    def test_validation_and_structural_binomial_slot(self):
        with self.assertRaises(ValueError):
            service.validate_board("extreme", 16)
        with self.assertRaises(ValueError):
            service.validate_board("low", 9)
        with mock.patch("app.plinko.service.secrets.randbits", side_effect=[0, 1] * 4):
            self.assertEqual(service.choose_slot(8), 4)

    def test_payout_math_has_no_fee(self):
        cases = (
            (Decimal("50"), Decimal("0.4"), Decimal("20.00"), Decimal("-30.00")),
            (Decimal("50"), Decimal("1.0"), Decimal("50.00"), Decimal("0.00")),
            (Decimal("10"), Decimal("1.5"), Decimal("15.00"), Decimal("5.00")),
            (Decimal("10.00"), Decimal("1.15"), Decimal("11.50"), Decimal("1.50")),
        )
        for stake, multiplier, payout, net in cases:
            got = service.compute_payout(stake, multiplier)
            self.assertEqual(got, payout)
            self.assertEqual(got - stake, net)
            # Explicit: never stake * (mult - fee) or payout - fee.
            self.assertEqual(
                got,
                (stake * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )


class PlinkoDatabaseTests(TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(
            engine,
            tables=[
                User.__table__,
                WalletTransaction.__table__,
                PlinkoPlay.__table__,
            ],
        )
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()
        self.user = User(
            telegram_id=1,
            first_name="One",
            referral_code="ONE",
            balance=Decimal("100.00"),
        )
        self.other = User(
            telegram_id=2,
            first_name="Two",
            referral_code="TWO",
            balance=Decimal("100.00"),
        )
        self.db.add_all([self.user, self.other])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_demo_persists_without_wallet_change_or_ledger(self):
        with mock.patch("app.plinko.service.choose_slot", return_value=4):
            result = service.play(
                self.db,
                user_id=self.user.id,
                play_id=uuid.uuid4(),
                raw_stake=0,
                risk="low",
                rows=8,
            )
        self.assertTrue(result["is_demo"])
        self.assertEqual(self.user.balance, Decimal("100.00"))
        self.assertEqual(Decimal(result["payout"]), Decimal("0.00"))
        self.assertEqual(Decimal(result["net"]), Decimal("0.00"))
        self.assertEqual(self.db.query(WalletTransaction).count(), 0)
        self.assertEqual(self.db.query(PlinkoPlay).count(), 1)

    def test_paid_play_settles_stake_times_multiplier_without_fee(self):
        slot = 8  # medium/16 center = 0.40
        with mock.patch("app.plinko.service.choose_slot", return_value=slot):
            result = service.play(
                self.db,
                user_id=self.user.id,
                play_id=uuid.uuid4(),
                raw_stake="50",
                risk="medium",
                rows=16,
            )
        multiplier = MULTIPLIER_TABLES["medium"][16][slot]
        self.assertEqual(multiplier, Decimal("0.40"))
        self.assertEqual(Decimal(result["multiplier"]), Decimal("0.40"))
        self.assertEqual(Decimal(result["payout"]), Decimal("20.00"))
        self.assertEqual(Decimal(result["net"]), Decimal("-30.00"))
        self.assertEqual(self.user.balance, Decimal("70.00"))
        self.assertNotIn("fee", result)
        self.assertNotIn("system_fee", result)
        txs = self.db.query(WalletTransaction).order_by(WalletTransaction.amount).all()
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].amount, Decimal("-50.00"))
        self.assertEqual(txs[1].amount, Decimal("20.00"))

    def test_break_even_one_x_returns_full_stake(self):
        slot = 6  # medium/16 = 1.00
        with mock.patch("app.plinko.service.choose_slot", return_value=slot):
            result = service.play(
                self.db,
                user_id=self.user.id,
                play_id=uuid.uuid4(),
                raw_stake="50",
                risk="medium",
                rows=16,
            )
        self.assertEqual(Decimal(result["multiplier"]), Decimal("1.00"))
        self.assertEqual(Decimal(result["payout"]), Decimal("50.00"))
        self.assertEqual(Decimal(result["net"]), Decimal("0.00"))
        self.assertEqual(self.user.balance, Decimal("100.00"))

    def test_winning_multiplier_credits_exact_payout(self):
        # Force a 1.5x-style outcome via medium/16 slot with multiplier 1.58 ≈ bump
        # Use compute path with mocked multiplier table lookup via slot that pays > stake.
        slot = 5  # medium/16 = 1.58
        with mock.patch("app.plinko.service.choose_slot", return_value=slot):
            result = service.play(
                self.db,
                user_id=self.user.id,
                play_id=uuid.uuid4(),
                raw_stake="10",
                risk="medium",
                rows=16,
            )
        multiplier = MULTIPLIER_TABLES["medium"][16][slot]
        expected_payout = service.compute_payout(Decimal("10"), multiplier)
        self.assertEqual(Decimal(result["payout"]), expected_payout)
        self.assertEqual(Decimal(result["net"]), expected_payout - Decimal("10"))
        self.assertEqual(self.user.balance, Decimal("100.00") - Decimal("10") + expected_payout)

    def test_exact_one_point_five_via_compute_and_history(self):
        patched = {
            **MULTIPLIER_TABLES,
            "medium": {**MULTIPLIER_TABLES["medium"], 8: (Decimal("1.5"),) * 9},
        }
        with mock.patch("app.plinko.service.MULTIPLIER_TABLES", patched):
            with mock.patch("app.plinko.service.choose_slot", return_value=0):
                result = service.play(
                    self.db,
                    user_id=self.user.id,
                    play_id=uuid.uuid4(),
                    raw_stake="10",
                    risk="medium",
                    rows=8,
                )
        self.assertEqual(Decimal(result["payout"]), Decimal("15.00"))
        self.assertEqual(Decimal(result["net"]), Decimal("5.00"))
        page = service.history(self.db, self.user.id, 10, 0)
        item = page["items"][0]
        self.assertEqual(Decimal(item["stake"]), Decimal("10.00"))
        self.assertEqual(Decimal(item["payout"]), Decimal("15.00"))
        self.assertEqual(Decimal(item["net"]), Decimal("5.00"))
        self.assertEqual(Decimal(item["multiplier"]), Decimal("1.50"))

    def test_history_is_user_scoped_and_matches_settlement(self):
        slot = 4
        with mock.patch("app.plinko.service.choose_slot", return_value=slot):
            result = service.play(
                self.db,
                user_id=self.user.id,
                play_id=uuid.uuid4(),
                raw_stake="10",
                risk="medium",
                rows=8,
            )
        expected = service.compute_payout(
            Decimal("10"), MULTIPLIER_TABLES["medium"][8][slot]
        )
        self.assertEqual(Decimal(result["payout"]), expected)
        self.assertEqual(self.db.query(WalletTransaction).count(), 2)
        page = service.history(self.db, self.user.id, 10, 0)
        other_page = service.history(self.db, self.other.id, 10, 0)
        self.assertEqual(page["total"], 1)
        self.assertEqual(other_page["total"], 0)
        item = page["items"][0]
        self.assertEqual(item["payout"], result["payout"])
        self.assertEqual(item["net"], result["net"])
        self.assertEqual(item["multiplier"], result["multiplier"])

    def test_insufficient_balance_checks_full_stake(self):
        self.user.balance = Decimal("9.99")
        self.db.commit()
        with mock.patch("app.plinko.service.choose_slot", return_value=0):
            with self.assertRaises(ValueError) as ctx:
                service.play(
                    self.db,
                    user_id=self.user.id,
                    play_id=uuid.uuid4(),
                    raw_stake="10",
                    risk="low",
                    rows=8,
                )
        self.assertEqual(str(ctx.exception), "Insufficient balance")
        self.assertEqual(self.user.balance, Decimal("9.99"))
        self.assertEqual(self.db.query(WalletTransaction).count(), 0)
        self.assertEqual(self.db.query(PlinkoPlay).count(), 0)

    def test_idempotent_replay_does_not_double_debit(self):
        play_id = uuid.uuid4()
        with mock.patch("app.plinko.service.choose_slot", return_value=0):
            first = service.play(
                self.db,
                user_id=self.user.id,
                play_id=play_id,
                raw_stake="10",
                risk="low",
                rows=8,
            )
            balance_after = self.user.balance
            second = service.play(
                self.db,
                user_id=self.user.id,
                play_id=play_id,
                raw_stake="10",
                risk="low",
                rows=8,
            )
        self.assertEqual(first["play_id"], second["play_id"])
        self.assertEqual(self.user.balance, balance_after)
        self.assertEqual(self.db.query(PlinkoPlay).count(), 1)
        self.assertEqual(self.db.query(WalletTransaction).count(), 2)
