"""Profile history pagination and payment isolation tests."""

from __future__ import annotations

from decimal import Decimal
from unittest import TestCase, mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import profile_service
from app.bingo import wallet as bingo_wallet
from app.db.database import Base
from app.models import BingoGame, BingoGameResult, Deposit, User, WithdrawRequest


class ProfileServiceTests(TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        self.db = self.Session()
        self.user = User(
            telegram_id=10,
            username="me",
            first_name="Me",
            referral_code="MEUSER",
            balance=Decimal("200.00"),
        )
        self.other = User(
            telegram_id=11,
            username="other",
            first_name="Other",
            referral_code="OTHER",
            balance=Decimal("50.00"),
        )
        self.db.add_all([self.user, self.other])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _patch_bingo_session(self):
        def factory():
            session = self.Session()
            session.close = lambda: None  # type: ignore[method-assign]
            return session

        return mock.patch("app.bingo.wallet.SessionLocal", side_effect=factory)

    def _seed_bingo(self, count: int) -> None:
        for i in range(count):
            game = BingoGame(
                game_code=f"MBLIM{i:02d}",
                room_id="default",
                status="finished",
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
                    user_id=self.user.id,
                    boards_count=1,
                    stake_amount=Decimal("10"),
                )
            )
        self.db.commit()

    def test_payments_are_user_isolated_and_masked(self):
        self.db.add_all(
            [
                Deposit(
                    user_id=self.user.id,
                    amount=Decimal("40.00"),
                    method="telebirr",
                    sms_transaction_id="SMSME1",
                ),
                Deposit(
                    user_id=self.other.id,
                    amount=Decimal("99.00"),
                    method="telebirr",
                    sms_transaction_id="SMSOTHER1",
                ),
                WithdrawRequest(
                    user_id=self.user.id,
                    method="telebirr",
                    account_name="Me",
                    account_number="0912345678",
                    amount=Decimal("25.00"),
                    fee=Decimal("0"),
                    status="PENDING",
                ),
                WithdrawRequest(
                    user_id=self.other.id,
                    method="cbe",
                    account_name="Other",
                    account_number="1000000000",
                    amount=Decimal("10.00"),
                    fee=Decimal("0"),
                    status="PENDING",
                ),
            ]
        )
        self.db.commit()

        deposits = profile_service.list_deposits(self.db, self.user.id, limit=5)
        withdrawals = profile_service.list_withdrawals(self.db, self.user.id, limit=5)

        self.assertEqual(deposits["total"], 1)
        self.assertEqual(len(deposits["items"]), 1)
        self.assertEqual(deposits["items"][0]["amount"], "40.00")
        self.assertEqual(deposits["limit"], 5)
        self.assertEqual(deposits["offset"], 0)
        self.assertEqual(withdrawals["total"], 1)
        self.assertEqual(withdrawals["items"][0]["account_masked"], "******5678")
        self.assertNotIn("0912345678", str(withdrawals["items"]))

    def test_payments_pagination_offset(self):
        for i in range(7):
            self.db.add(
                Deposit(
                    user_id=self.user.id,
                    amount=Decimal(f"{10 + i}.00"),
                    method="telebirr",
                    sms_transaction_id=f"SMSDEP{i}",
                )
            )
        self.db.commit()

        page0 = profile_service.list_deposits(self.db, self.user.id, limit=5, offset=0)
        page1 = profile_service.list_deposits(self.db, self.user.id, limit=5, offset=5)

        self.assertEqual(page0["total"], 7)
        self.assertEqual(len(page0["items"]), 5)
        self.assertEqual(page0["offset"], 0)
        self.assertEqual(page1["total"], 7)
        self.assertEqual(len(page1["items"]), 2)
        self.assertEqual(page1["offset"], 5)
        self.assertEqual(page1["limit"], 5)

    def test_payments_limit_capped_at_20(self):
        page = profile_service.list_deposits(self.db, self.user.id, limit=50, offset=0)
        self.assertEqual(page["limit"], 20)

    def test_game_history_bingo_pagination(self):
        self._seed_bingo(7)

        with self._patch_bingo_session():
            page0 = profile_service.game_history(
                self.db, self.user.id, game="bingo", limit=5, offset=0
            )
            page1 = profile_service.game_history(
                self.db, self.user.id, game="bingo", limit=5, offset=5
            )

        self.assertEqual(page0["total"], 7)
        self.assertEqual(len(page0["items"]), 5)
        self.assertEqual(page0["limit"], 5)
        self.assertEqual(page0["offset"], 0)
        self.assertEqual(page1["total"], 7)
        self.assertEqual(len(page1["items"]), 2)
        self.assertEqual(page1["offset"], 5)

        with self._patch_bingo_session():
            raw = bingo_wallet.get_user_history(str(self.user.id), limit=5, offset=0)
        self.assertEqual(len(raw["games"]), 5)
        self.assertEqual(raw["total"], 7)

    def test_game_history_invalid_game(self):
        with self.assertRaises(ValueError):
            profile_service.game_history(self.db, self.user.id, game="poker")

    def test_profile_summary_is_light(self):
        self._seed_bingo(3)
        summary = profile_service.profile_summary(self.db, self.user.id, limit=5)
        self.assertEqual(summary["limit"], 5)
        self.assertIn("bingo", summary["games"])
        self.assertNotIn("deposits", summary)
        self.assertNotIn("withdrawals", summary)
        self.assertEqual(set(summary.keys()), {"limit", "games"})
