"""Security and accounting tests for the admin subsystem."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from unittest import TestCase, mock

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin import service
from app.admin.helpers import is_admin, require_admin, sanitize
from app.admin.router import _queue_withdrawal_notify
from app.bot.i18n import t
from app.bot.notify import abbreviate_id, notify_withdrawal_decision
from app.db.database import Base
from app.models import (
    AdminAuditLog, BingoGame, BingoGameResult, Deposit, PlinkoPlay, User,
    WalletTransaction, WithdrawRequest,
)


class AdminDatabaseTests(TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()
        self.admin = User(
            telegram_id=1, username="@HaS365", first_name="Admin",
            referral_code="ADMIN", balance=Decimal("500.00"),
        )
        self.user = User(
            telegram_id=2, username="player", first_name="Player",
            referral_code="PLAYER", balance=Decimal("100.00"),
            language_code="en",
        )
        self.db.add_all([self.admin, self.user])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _add_deposit(self, amount: str = "50.00", method: str = "telebirr", ref: str = "TX1"):
        row = Deposit(
            user_id=self.user.id,
            amount=Decimal(amount),
            method=method,
            sms_transaction_id=ref,
        )
        self.db.add(row)
        self.db.commit()
        return row

    @mock.patch("app.admin.helpers.settings.ADMIN_TELEGRAM_USERNAMES", "has365")
    def test_allowlist_is_case_insensitive_and_strips_at(self):
        self.assertTrue(is_admin(self.admin))
        self.assertFalse(is_admin(self.user))
        self.assertEqual(require_admin(self.admin), self.admin)
        with self.assertRaises(HTTPException) as denied:
            require_admin(self.user)
        self.assertEqual(denied.exception.status_code, 403)

    def test_balance_adjustment_creates_ledger_and_audit_and_is_idempotent(self):
        request_id = uuid.uuid4()
        first = service.adjust_balance(
            self.db, self.admin, self.user.id, Decimal("25"), "manual correction", request_id
        )
        second = service.adjust_balance(
            self.db, self.admin, self.user.id, Decimal("25"), "manual correction", request_id
        )
        self.db.refresh(self.user)
        self.assertEqual(first["balance"], "125.00")
        self.assertTrue(second["idempotent"])
        self.assertEqual(self.user.balance, Decimal("125.00"))
        self.assertEqual(self.db.query(WalletTransaction).count(), 1)
        self.assertEqual(self.db.query(AdminAuditLog).count(), 1)

        with self.assertRaises(HTTPException) as reused:
            service.adjust_balance(
                self.db, self.admin, self.admin.id, Decimal("1"),
                "different operation", request_id,
            )
        self.assertEqual(reused.exception.status_code, 403)

    def test_adjustment_prevents_negative_and_self_adjustment(self):
        with self.assertRaises(HTTPException) as negative:
            service.adjust_balance(
                self.db, self.admin, self.user.id, Decimal("-101"), "invalid debit", uuid.uuid4()
            )
        self.assertEqual(negative.exception.status_code, 409)
        with self.assertRaises(HTTPException) as self_adjust:
            service.adjust_balance(
                self.db, self.admin, self.admin.id, Decimal("1"), "self", uuid.uuid4()
            )
        self.assertEqual(self_adjust.exception.status_code, 403)
        self.assertEqual(self.db.query(WalletTransaction).count(), 0)

    def test_deposit_list_returns_completed_ledger_for_all_and_completed(self):
        self._add_deposit("75.50", "telebirr", "SMSABC123XYZ")
        for status in ("all", "completed", "approved", None):
            page = service.list_deposits(self.db, status, 20, 0)
            self.assertEqual(page["total"], 1, status)
            item = page["items"][0]
            self.assertEqual(item["amount"], "75.50")
            self.assertEqual(item["status"], "COMPLETED")
            self.assertEqual(item["method"], "telebirr")
            self.assertEqual(item["username"], "player")
            self.assertIn("…", item["reference"])
            self.assertNotEqual(item["reference"], "SMSABC123XYZ")
            self.assertFalse(page["pending_supported"])
            self.assertIn("workflow", page)

        pending = service.list_deposits(self.db, "pending", 20, 0)
        self.assertEqual(pending["total"], 0)
        self.assertEqual(pending["items"], [])
        self.assertFalse(pending["pending_supported"])

        dash = service.dashboard(self.db, None, None)
        self.assertEqual(dash["deposits"]["approved_count"], 1)
        self.assertEqual(dash["deposits"]["approved_amount"], "75.50")
        self.assertEqual(dash["deposits"]["pending_count"], 0)

    def test_withdrawal_approval_debits_once_and_reject_never_debits(self):
        approved = WithdrawRequest(
            user_id=self.user.id, method="CBE", account_name="Player",
            account_number="1000000000", amount=Decimal("40"), fee=Decimal("2"),
        )
        rejected = WithdrawRequest(
            user_id=self.user.id, method="CBE", account_name="Player",
            account_number="1000000000", amount=Decimal("10"), fee=Decimal("0"),
        )
        self.db.add_all([approved, rejected])
        self.db.commit()
        key = uuid.uuid4()
        first = service.decide_withdrawal(self.db, self.admin, approved.id, True, None, key)
        replay = service.decide_withdrawal(self.db, self.admin, approved.id, True, None, key)
        reject = service.decide_withdrawal(
            self.db, self.admin, rejected.id, False, "details do not match", uuid.uuid4()
        )
        self.db.refresh(self.user)
        self.assertFalse(first["idempotent"])
        self.assertIsNotNone(first["notify"])
        self.assertTrue(first["notify"]["approved"])
        self.assertEqual(first["notify"]["balance"], "58.00")
        self.assertTrue(replay["idempotent"])
        self.assertIsNone(replay["notify"])
        self.assertFalse(reject["idempotent"])
        self.assertFalse(reject["notify"]["approved"])
        self.assertEqual(reject["notify"]["reason"], "details do not match")
        self.assertEqual(self.user.balance, Decimal("58.00"))
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(rejected.status, "REJECTED")
        self.assertEqual(self.db.query(WalletTransaction).count(), 1)
        self.assertEqual(self.db.query(AdminAuditLog).count(), 2)

    def test_dashboard_does_not_double_count_plinko(self):
        self.db.add(PlinkoPlay(
            id=uuid.uuid4(), user_id=self.user.id, stake=Decimal("10"),
            risk="medium", rows=8, slot_index=4, multiplier=Decimal("1.5"),
            payout=Decimal("15"), net_result=Decimal("5"), is_demo=False,
        ))
        self.db.commit()
        result = service.dashboard(self.db, None, None)
        plinko = next(item for item in result["games"] if item["game"] == "plinko")
        self.assertEqual(plinko["turnover"], "10.00")
        self.assertEqual(plinko["payouts"], "15.00")
        self.assertEqual(plinko["ggr"], "-5.00")
        self.assertEqual(result["turnover"], "10.00")

    def test_game_fee_is_not_multiplied_by_participants(self):
        game = BingoGame(
            game_code="ADMIN1", room_id="room", status="finished",
            board_price=Decimal("10"), total_boards=2, total_players=2,
            derash=Decimal("20"), system_fee=Decimal("2"),
        )
        self.db.add(game)
        self.db.flush()
        self.db.add_all([
            BingoGameResult(
                game_id=game.id, user_id=self.user.id, boards_count=1,
                stake_amount=Decimal("10"), amount_won=Decimal("18"),
                is_winner=True,
            ),
            BingoGameResult(
                game_id=game.id, user_id=self.admin.id, boards_count=1,
                stake_amount=Decimal("10"), amount_won=Decimal("0"),
                is_winner=False,
            ),
        ])
        self.db.commit()
        result = service.game_summary(self.db, None, None)
        bingo = next(item for item in result["games"] if item["game"] == "bingo")
        self.assertEqual(bingo["turnover"], "20.00")
        self.assertEqual(bingo["explicit_system_fee"], "2.00")

    def test_user_search_isolated_and_decimal_strings(self):
        page = service.list_users(self.db, "player", None, 20, 0, "joined_desc")
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["username"], "player")
        self.assertEqual(page["items"][0]["balance"], "100.00")

    def test_list_endpoints_honor_limit_offset(self):
        for i in range(5):
            self._add_deposit(f"{10 + i}.00", "telebirr", f"SMSREF{i:03d}")
            self.db.add(WithdrawRequest(
                user_id=self.user.id, method="CBE", account_name="Player",
                account_number=f"100000000{i}", amount=Decimal("5"), fee=Decimal("0"),
            ))
            self.db.add(AdminAuditLog(
                id=uuid.uuid4(), admin_user_id=self.admin.id,
                action=f"test.action.{i}", target_type="user",
                target_id=str(self.user.id), reason="pagination",
                request_id=uuid.uuid4(),
            ))
        self.db.commit()

        deposits = service.list_deposits(self.db, "all", 2, 0)
        self.assertEqual(deposits["total"], 5)
        self.assertEqual(deposits["limit"], 2)
        self.assertEqual(deposits["offset"], 0)
        self.assertEqual(len(deposits["items"]), 2)
        deposits_page2 = service.list_deposits(self.db, "all", 2, 2)
        self.assertEqual(len(deposits_page2["items"]), 2)
        self.assertNotEqual(deposits["items"][0]["id"], deposits_page2["items"][0]["id"])

        withdrawals = service.list_withdrawals(self.db, "all", 3, 0)
        self.assertEqual(withdrawals["total"], 5)
        self.assertEqual(len(withdrawals["items"]), 3)
        self.assertLessEqual(len(withdrawals["items"]), withdrawals["limit"])

        audit = service.audit_feed(self.db, 2, 0)
        self.assertEqual(audit["total"], 5)
        self.assertEqual(len(audit["items"]), 2)

        for i in range(3):
            other = User(
                telegram_id=100 + i, username=f"p{i}", first_name=f"P{i}",
                referral_code=f"P{i}", balance=Decimal("0"),
            )
            self.db.add(other)
            self.db.flush()
            self.db.add(PlinkoPlay(
                id=uuid.uuid4(), user_id=other.id, stake=Decimal(str(i + 1)),
                risk="medium", rows=8, slot_index=1, multiplier=Decimal("1"),
                payout=Decimal("1"), net_result=Decimal("0"), is_demo=False,
            ))
        self.db.commit()
        players = service.game_players(self.db, "plinko", None, None, 2, 0)
        self.assertEqual(players["total"], 3)
        self.assertEqual(len(players["items"]), 2)

    def test_dashboard_is_aggregates_only_with_action_queue(self):
        self._add_deposit("20.00", "telebirr", "DASHREF1")
        self.db.add(WithdrawRequest(
            user_id=self.user.id, method="CBE", account_name="Player",
            account_number="1000000099", amount=Decimal("15"), fee=Decimal("0"),
        ))
        self.db.commit()
        dash = service.dashboard(self.db, None, None)
        self.assertNotIn("items", dash)
        self.assertNotIn("users", dash)
        self.assertNotIn("deposits_list", dash)
        self.assertIsInstance(dash["games"], list)
        self.assertLessEqual(len(dash["games"]), 10)
        self.assertEqual(dash["action_queue"]["pending_withdrawals"]["count"], 1)
        self.assertEqual(dash["action_queue"]["pending_withdrawals"]["amount"], "15.00")
        self.assertEqual(dash["deposits"]["approved_count"], 1)
        for game in dash["games"]:
            self.assertIn("turnover", game)
            self.assertNotIn("players", game)

    def test_frontend_admin_loads_sections_on_demand(self):
        root = Path(__file__).resolve().parents[2]
        dash = (root / "frontend/src/components/admin/AdminDashboard.tsx").read_text(encoding="utf-8")
        svc = (root / "frontend/src/services/admin.ts").read_text(encoding="utf-8")
        self.assertIn("ADMIN_PAGE_SIZE", svc)
        self.assertIn("loadKey", dash)
        self.assertIn("sectionVisit", dash)
        self.assertIn("debouncedSearch", dash)
        self.assertIn("paymentOffset", dash)
        self.assertIn("getDeposits({", dash)
        self.assertIn("limit: ADMIN_PAGE_SIZE", dash)
        # Must not prefetch every section on mount.
        self.assertNotRegex(
            dash,
            r"Promise\.all\(\s*\[\s*getDashboard|getUsers\([^)]*\)\s*,\s*getDeposits",
        )


class WithdrawalNotifyTests(TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()
        self.admin = User(
            telegram_id=1, username="has365", first_name="Admin",
            referral_code="ADMIN", balance=Decimal("0"),
        )
        self.user = User(
            telegram_id=99, username="player", first_name="Player",
            referral_code="PLAYER", balance=Decimal("200.00"),
            language_code="am",
        )
        self.db.add_all([self.admin, self.user])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_queue_notifies_once_and_idempotent_skips(self):
        row = WithdrawRequest(
            user_id=self.user.id, method="Telebirr", account_name="Player",
            account_number="0911000000", amount=Decimal("50"), fee=Decimal("0"),
        )
        self.db.add(row)
        self.db.commit()
        key = uuid.uuid4()
        first = service.decide_withdrawal(self.db, self.admin, row.id, True, None, key)
        tasks = BackgroundTasks()
        with mock.patch("app.admin.router.notify_withdrawal_decision") as send:
            _queue_withdrawal_notify(tasks, first)
            self.assertEqual(len(tasks.tasks), 1)
            replay = service.decide_withdrawal(self.db, self.admin, row.id, True, None, key)
            _queue_withdrawal_notify(tasks, replay)
            self.assertEqual(len(tasks.tasks), 1)
            self.assertIsNone(replay["notify"])

    def test_notifier_failure_does_not_undo_decision(self):
        row = WithdrawRequest(
            user_id=self.user.id, method="CBE", account_name="Player",
            account_number="1000000000", amount=Decimal("30"), fee=Decimal("0"),
        )
        self.db.add(row)
        self.db.commit()
        result = service.decide_withdrawal(
            self.db, self.admin, row.id, False, "bad details", uuid.uuid4()
        )
        self.db.refresh(row)
        self.db.refresh(self.user)
        self.assertEqual(row.status, "REJECTED")
        self.assertEqual(self.user.balance, Decimal("200.00"))

        async def boom(**_kwargs):
            raise RuntimeError("telegram down")

        tasks = BackgroundTasks()
        with mock.patch("app.admin.router.notify_withdrawal_decision", side_effect=boom):
            payload = _queue_withdrawal_notify(tasks, result)
        self.assertEqual(payload["status"], "REJECTED")
        self.assertNotIn("notify", payload)
        self.db.refresh(row)
        self.assertEqual(row.status, "REJECTED")

    def test_language_selection_en_and_am(self):
        en = t("en", "withdraw.decision.approved", amount="10.00", ref="abc", balance="5.00")
        am = t("am", "withdraw.decision.approved", amount="10.00", ref="abc", balance="5.00")
        self.assertIn("BRIGHT GAMES", en)
        self.assertIn("approved", en.lower())
        self.assertIn("BRIGHT GAMES", am)
        self.assertIn("ጸድቋል", am)
        self.assertNotEqual(en, am)
        rejected = t(
            "en", "withdraw.decision.rejected",
            amount="10.00", ref="abc", reason="mismatch",
        )
        self.assertIn("No funds were taken", rejected)
        self.assertTrue(len(abbreviate_id(uuid.uuid4())) <= 10)


class NotifyHelperAsyncTests(TestCase):
    def test_notify_uses_persisted_language(self):
        import asyncio

        async def run():
            with mock.patch("telegram.Bot") as bot_cls:
                bot = mock.AsyncMock()
                bot_cls.return_value = bot
                with mock.patch("app.bot.notify.settings.TELEGRAM_BOT_TOKEN", "token"):
                    ok = await notify_withdrawal_decision(
                        telegram_id=42,
                        language_code="am",
                        approved=True,
                        amount="12.00",
                        withdrawal_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                        balance="88.00",
                    )
                self.assertTrue(ok)
                bot.send_message.assert_awaited_once()
                kwargs = bot.send_message.await_args.kwargs
                self.assertEqual(kwargs["chat_id"], 42)
                self.assertIn("ጸድቋል", kwargs["text"])
                self.assertIn("BRIGHT GAMES", kwargs["text"])

                bot.reset_mock()
                with mock.patch("app.bot.notify.settings.TELEGRAM_BOT_TOKEN", "token"):
                    await notify_withdrawal_decision(
                        telegram_id=42,
                        language_code="en",
                        approved=False,
                        amount="12.00",
                        withdrawal_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                        reason="invalid account",
                    )
                text = bot.send_message.await_args.kwargs["text"]
                self.assertIn("rejected", text.lower())
                self.assertIn("invalid account", text)
                self.assertIn("No funds were taken", text)

        asyncio.run(run())


class AdminSanitizationTests(TestCase):
    def test_sensitive_fields_are_redacted_recursively(self):
        cleaned = sanitize({"token": "secret", "nested": {"account_number": "1234"}, "amount": Decimal("1.20")})
        self.assertEqual(cleaned["token"], "[REDACTED]")
        self.assertEqual(cleaned["nested"]["account_number"], "[REDACTED]")
        self.assertEqual(cleaned["amount"], "1.20")

    def test_frontend_visibility_uses_admin_me_not_username(self):
        root = Path(__file__).resolve().parents[2]
        shell = (root / "frontend/src/components/bingo/BingoGame.tsx").read_text(encoding="utf-8")
        nav = (root / "frontend/src/components/bingo/BottomNav.tsx").read_text(encoding="utf-8")
        dash = (root / "frontend/src/components/admin/AdminDashboard.tsx").read_text(encoding="utf-8")
        self.assertIn("getAdminMe()", shell)
        self.assertIn("capability.is_admin", shell)
        self.assertIn('id !== "admin" || isAdmin', nav)
        self.assertNotIn("has365", shell + nav)
        self.assertIn("depositStatus", dash)
        self.assertIn('"all"', dash)
