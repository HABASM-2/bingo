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
        deposit = self.db.query(Deposit).filter(
            Deposit.sms_transaction_id == f"ADMIN-{request_id}"
        ).one()
        self.assertEqual(deposit.amount, Decimal("25.00"))
        self.assertEqual(deposit.method, "admin_adjustment")
        self.assertEqual(self.db.query(Deposit).count(), 1)

        with self.assertRaises(HTTPException) as reused:
            service.adjust_balance(
                self.db, self.admin, self.admin.id, Decimal("1"),
                "different operation", request_id,
            )
        self.assertEqual(reused.exception.status_code, 403)

    def test_positive_adjustment_appears_in_deposit_lists(self):
        request_id = uuid.uuid4()
        service.adjust_balance(
            self.db, self.admin, self.user.id, Decimal("40.50"), "promo credit", request_id
        )
        page = service.list_deposits(self.db, "all", 20, 0)
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["method"], "admin_adjustment")
        self.assertEqual(page["items"][0]["amount"], "40.50")
        self.assertEqual(page["items"][0]["status"], "COMPLETED")
        detail = service.user_detail(self.db, self.user.id)
        self.assertEqual(len(detail["deposits"]), 1)
        self.assertEqual(detail["deposits"][0]["method"], "admin_adjustment")

    def test_negative_adjustment_creates_approved_withdraw_row(self):
        request_id = uuid.uuid4()
        result = service.adjust_balance(
            self.db, self.admin, self.user.id, Decimal("-30"), "clawback", request_id
        )
        self.db.refresh(self.user)
        self.assertEqual(result["balance"], "70.00")
        self.assertEqual(self.user.balance, Decimal("70.00"))
        row = self.db.query(WithdrawRequest).filter(WithdrawRequest.id == request_id).one()
        self.assertEqual(row.status, "APPROVED")
        self.assertEqual(row.method, "admin_adjustment")
        self.assertEqual(row.amount, Decimal("30.00"))
        self.assertEqual(Decimal(row.fee or 0), Decimal("0"))
        self.assertIsNotNone(row.processed_at)
        self.assertEqual(self.db.query(Deposit).count(), 0)
        self.assertEqual(self.db.query(WalletTransaction).count(), 1)
        page = service.list_withdrawals(self.db, "approved", 20, 0)
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["method"], "admin_adjustment")
        self.assertEqual(page["items"][0]["amount"], "30.00")
        detail = service.user_detail(self.db, self.user.id)
        self.assertEqual(len(detail["withdrawals"]), 1)
        self.assertEqual(detail["withdrawals"][0]["status"], "APPROVED")
        # Already approved — decide_withdrawal must not debit again.
        with self.assertRaises(HTTPException) as already:
            service.decide_withdrawal(
                self.db, self.admin, request_id, True, None, uuid.uuid4()
            )
        self.assertEqual(already.exception.status_code, 409)
        self.db.refresh(self.user)
        self.assertEqual(self.user.balance, Decimal("70.00"))

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
        self.assertEqual(self.db.query(Deposit).count(), 0)
        self.assertEqual(self.db.query(WithdrawRequest).count(), 0)

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
        # Legacy rows without stake breakdown still report system_fee as GGR.
        self.assertEqual(bingo["ggr"], "2.00")

    def test_wallet_liabilities_exclude_and_include_bots(self):
        bot = User(
            telegram_id=99, username="bright_bot", first_name="Bright Bot",
            referral_code="BOT99", balance=Decimal("500.00"), is_bot=True,
        )
        self.db.add(bot)
        self.db.commit()
        dash = service.dashboard(self.db, None, None)
        # Player 100 + admin 500 = 600 without bot; +500 bot = 1100 with bots.
        self.assertEqual(dash["wallet_liabilities_without_bots"], "600.00")
        self.assertEqual(dash["wallet_liabilities_with_bots"], "1100.00")
        self.assertEqual(dash["wallet_liabilities"], "600.00")

    def test_bingo_system_gain_bot_win_and_bot_loss(self):
        # Bot win: system_gain = real stakes only (5 × 10 = 50).
        bot_win = BingoGame(
            game_code="BOTWIN1", room_id="room", status="finished",
            board_price=Decimal("10"), total_boards=15, total_players=2,
            derash=Decimal("150"), system_fee=Decimal("150"),
            system_gain=Decimal("50"), bot_won=True,
            real_stake_total=Decimal("50"), bot_stake_total=Decimal("100"),
        )
        # Real win with bot boards: S = 20% × 150 = 30; gain = 30 − 100 = −70.
        bot_loss = BingoGame(
            game_code="BOTLOSS1", room_id="room", status="finished",
            board_price=Decimal("10"), total_boards=15, total_players=2,
            derash=Decimal("150"), system_fee=Decimal("30"),
            system_gain=Decimal("-70"), bot_won=False,
            real_stake_total=Decimal("50"), bot_stake_total=Decimal("100"),
        )
        # No-bot round: gain equals normal fee.
        plain = BingoGame(
            game_code="PLAIN1", room_id="room", status="finished",
            board_price=Decimal("10"), total_boards=6, total_players=2,
            derash=Decimal("60"), system_fee=Decimal("6"),
            system_gain=Decimal("6"), bot_won=False,
            real_stake_total=Decimal("60"), bot_stake_total=Decimal("0"),
        )
        self.db.add_all([bot_win, bot_loss, plain])
        self.db.flush()
        bot = User(
            telegram_id=99, username="bright_bot", first_name="Bright Bot",
            referral_code="BOT99", balance=Decimal("0"), is_bot=True,
        )
        self.db.add(bot)
        self.db.flush()
        for game, real_stake, bot_stake, real_won, bot_won_amt in (
            (bot_win, Decimal("50"), Decimal("100"), Decimal("0"), Decimal("0")),
            (bot_loss, Decimal("50"), Decimal("100"), Decimal("120"), Decimal("0")),
            (plain, Decimal("60"), Decimal("0"), Decimal("54"), Decimal("0")),
        ):
            self.db.add(BingoGameResult(
                game_id=game.id, user_id=self.user.id, boards_count=int(real_stake / 10),
                stake_amount=real_stake, amount_won=real_won, is_winner=real_won > 0,
            ))
            if bot_stake > 0:
                self.db.add(BingoGameResult(
                    game_id=game.id, user_id=bot.id, boards_count=int(bot_stake / 10),
                    stake_amount=bot_stake, amount_won=bot_won_amt,
                    is_winner=game.bot_won,
                ))
        self.db.commit()
        result = service.game_summary(self.db, None, None)
        bingo = next(item for item in result["games"] if item["game"] == "bingo")
        # 50 + (−70) + 6 = −14
        self.assertEqual(bingo["explicit_system_fee"], "-14.00")
        self.assertEqual(bingo["ggr"], "-14.00")
        self.assertEqual(bingo["bot_rounds"], 2)

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
        self.assertIn("getBingoBot", svc)
        self.assertIn("setBingoBot", svc)
        self.assertIn("BingoBotControl", dash)
        # Must not prefetch every section on mount.
        self.assertNotRegex(
            dash,
            r"Promise\.all\(\s*\[\s*getDashboard|getUsers\([^)]*\)\s*,\s*getDeposits",
        )


class BingoBotAdminToggleTests(TestCase):
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
        )
        self.db.add_all([self.admin, self.user])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    @mock.patch("app.admin.helpers.settings.ADMIN_TELEGRAM_USERNAMES", "has365")
    def test_non_admin_denied_for_bingo_bot_routes(self):
        with self.assertRaises(HTTPException) as denied:
            require_admin(self.user)
        self.assertEqual(denied.exception.status_code, 403)

    def test_toggle_writes_audit_and_persists_flag(self):
        import asyncio

        async def run():
            status_payload = {
                "enabled": False,
                "source": "redis",
                "boards_held": 0,
                "status": "inactive",
                "room_id": "default",
                "room_status": "lobby",
            }
            with (
                mock.patch(
                    "app.bingo.house_bot.set_bot_enabled",
                    new=mock.AsyncMock(),
                ) as set_flag,
                mock.patch(
                    "app.bingo.house_bot.tick_room",
                    new=mock.AsyncMock(),
                ) as tick,
                mock.patch(
                    "app.admin.service.bingo_bot_status",
                    new=mock.AsyncMock(
                        side_effect=[
                            {**status_payload, "enabled": True, "source": "env", "status": "active"},
                            status_payload,
                            status_payload,
                        ]
                    ),
                ),
            ):
                request_id = uuid.uuid4()
                result = await service.set_bingo_bot_enabled(
                    self.db, self.admin, False, request_id
                )
                set_flag.assert_awaited_once_with(False)
                tick.assert_awaited()
                self.assertFalse(result["enabled"])
                self.assertFalse(result["idempotent"])

                replay = await service.set_bingo_bot_enabled(
                    self.db, self.admin, False, request_id
                )
                self.assertTrue(replay["idempotent"])
                set_flag.assert_awaited_once()

            logs = self.db.query(AdminAuditLog).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].action, "bingo_bot.toggle")
            self.assertEqual(logs[0].target_type, "bingo_bot")
            self.assertEqual(logs[0].after_data["enabled"], False)

        asyncio.run(run())

    def test_status_reads_redis_flag(self):
        import asyncio

        async def run():
            with (
                mock.patch(
                    "app.bingo.house_bot.get_bot_enabled",
                    new=mock.AsyncMock(return_value=(True, "redis")),
                ),
                mock.patch(
                    "app.bingo.house_bot.cached_bot_user_id",
                    return_value=None,
                ),
                mock.patch(
                    "app.bingo.redis_store.get_room",
                    new=mock.AsyncMock(return_value=None),
                ),
            ):
                status = await service.bingo_bot_status()
            self.assertTrue(status["enabled"])
            self.assertEqual(status["source"], "redis")
            self.assertEqual(status["status"], "active")
            self.assertEqual(status["boards_held"], 0)

        asyncio.run(run())


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
        self.assertIn("maintenance", dash)
        self.assertIn("previewDataRetention", dash)


class AdminDataRetentionTests(TestCase):
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
        )
        self.bot = User(
            telegram_id=-1, username="house_bot", first_name="Bot",
            referral_code="HOUSEBOT", balance=Decimal("50.00"), is_bot=True,
        )
        self.db.add_all([self.admin, self.user, self.bot])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_clear_all_zeros_balances_keeps_users_deletes_ops(self):
        from datetime import datetime, timezone

        from app.admin import data_retention

        self.db.add(Deposit(
            user_id=self.user.id, amount=Decimal("20"), method="telebirr",
            sms_transaction_id="SMS1",
        ))
        self.db.add(WithdrawRequest(
            user_id=self.user.id, method="CBE", account_name="P",
            account_number="1", amount=Decimal("5"), fee=Decimal("0"),
            status="PENDING",
        ))
        self.db.add(WalletTransaction(
            user_id=self.user.id, transaction_type="ADMIN_ADJUSTMENT",
            amount=Decimal("1"), balance_before=Decimal("99"),
            balance_after=Decimal("100"), status="COMPLETED",
        ))
        self.db.add(PlinkoPlay(
            id=uuid.uuid4(), user_id=self.user.id, stake=Decimal("10"),
            risk="medium", rows=8, slot_index=4, multiplier=Decimal("1.5"),
            payout=Decimal("15"), net_result=Decimal("5"), is_demo=False,
        ))
        self.db.commit()

        preview = data_retention.preview_purge(self.db, "all")
        self.assertEqual(preview["confirmation_required"], "CLEAR")
        self.assertTrue(preview["zeros_balances"])
        self.assertGreaterEqual(preview["counts"]["deposits"], 1)

        async def run():
            with mock.patch(
                "app.admin.data_retention._flush_redis_game_keys",
                new=mock.AsyncMock(return_value=3),
            ):
                return await data_retention.run_purge(
                    self.db, self.admin,
                    option="all",
                    confirmation="CLEAR",
                    reason="format after staging load",
                    request_id=uuid.uuid4(),
                )

        import asyncio
        result = asyncio.run(run())
        self.assertFalse(result["idempotent"])
        self.assertEqual(result["users_kept"], 3)
        self.assertEqual(result["redis_keys_deleted"], 3)
        self.assertEqual(self.db.query(Deposit).count(), 0)
        self.assertEqual(self.db.query(WithdrawRequest).count(), 0)
        self.assertEqual(self.db.query(WalletTransaction).count(), 0)
        self.assertEqual(self.db.query(PlinkoPlay).count(), 0)
        self.assertEqual(self.db.query(User).count(), 3)
        self.db.refresh(self.user)
        self.db.refresh(self.admin)
        self.db.refresh(self.bot)
        self.assertEqual(self.user.balance, Decimal("0.00"))
        self.assertEqual(self.admin.balance, Decimal("0.00"))
        self.assertEqual(self.bot.balance, Decimal("0.00"))
        audits = self.db.query(AdminAuditLog).all()
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].action, "data.purge")

    def test_age_purge_keeps_recent_and_balances(self):
        from datetime import datetime, timedelta, timezone

        from app.admin import data_retention

        old = datetime.now(timezone.utc) - timedelta(days=40)
        recent = datetime.now(timezone.utc) - timedelta(days=2)
        old_dep = Deposit(
            user_id=self.user.id, amount=Decimal("10"), method="telebirr",
            sms_transaction_id="OLD1",
        )
        new_dep = Deposit(
            user_id=self.user.id, amount=Decimal("15"), method="telebirr",
            sms_transaction_id="NEW1",
        )
        self.db.add_all([old_dep, new_dep])
        self.db.flush()
        self.db.execute(
            Deposit.__table__.update()
            .where(Deposit.id == old_dep.id)
            .values(created_at=old.replace(tzinfo=None))
        )
        self.db.execute(
            Deposit.__table__.update()
            .where(Deposit.id == new_dep.id)
            .values(created_at=recent.replace(tzinfo=None))
        )
        self.db.commit()

        async def run():
            return await data_retention.run_purge(
                self.db, self.admin,
                option="30d",
                confirmation="DELETE",
                reason="trim old deposits",
                request_id=uuid.uuid4(),
            )

        import asyncio
        result = asyncio.run(run())
        self.assertEqual(result["deleted"]["deposits"], 1)
        self.assertEqual(self.db.query(Deposit).count(), 1)
        self.assertEqual(
            self.db.query(Deposit).one().sms_transaction_id, "NEW1"
        )
        self.db.refresh(self.user)
        self.assertEqual(self.user.balance, Decimal("100.00"))

    def test_purge_requires_confirmation_and_blocks_non_admin_word(self):
        from app.admin import data_retention
        import asyncio

        async def bad():
            await data_retention.run_purge(
                self.db, self.admin,
                option="all",
                confirmation="DELETE",
                reason="wrong word",
                request_id=uuid.uuid4(),
            )

        with self.assertRaises(HTTPException) as err:
            asyncio.run(bad())
        self.assertEqual(err.exception.status_code, 422)

    def test_games_only_purge_keeps_payments_and_balances(self):
        from app.admin import data_retention
        from app.models.aviator_game import AviatorRound

        self.db.add(Deposit(
            user_id=self.user.id, amount=Decimal("20"), method="telebirr",
            sms_transaction_id="KEEPDEP",
        ))
        self.db.add(WithdrawRequest(
            user_id=self.user.id, method="CBE", account_name="P",
            account_number="1", amount=Decimal("5"), fee=Decimal("0"),
            status="PENDING",
        ))
        self.db.add(WalletTransaction(
            user_id=self.user.id, transaction_type="ADMIN_ADJUSTMENT",
            amount=Decimal("1"), balance_before=Decimal("99"),
            balance_after=Decimal("100"), status="COMPLETED",
        ))
        self.db.add(WalletTransaction(
            user_id=self.user.id, transaction_type="BINGO_STAKE",
            amount=Decimal("-10"), balance_before=Decimal("110"),
            balance_after=Decimal("100"), status="COMPLETED",
        ))
        self.db.add(WalletTransaction(
            user_id=self.user.id, transaction_type="AVIATOR_BET",
            amount=Decimal("-5"), balance_before=Decimal("105"),
            balance_after=Decimal("100"), status="COMPLETED",
        ))
        self.db.add(WalletTransaction(
            user_id=self.user.id, transaction_type="WITHDRAWAL",
            amount=Decimal("-5"), balance_before=Decimal("105"),
            balance_after=Decimal("100"), status="COMPLETED",
        ))
        bingo = BingoGame(
            game_code="GONLY1", room_id="room", status="finished",
            board_price=Decimal("10"), total_boards=1, total_players=1,
            derash=Decimal("10"), system_fee=Decimal("1"),
        )
        self.db.add(bingo)
        self.db.flush()
        self.db.add(BingoGameResult(
            game_id=bingo.id, user_id=self.user.id, boards_count=1,
            stake_amount=Decimal("10"), amount_won=Decimal("0"),
            is_winner=False,
        ))
        self.db.add(PlinkoPlay(
            id=uuid.uuid4(), user_id=self.user.id, stake=Decimal("10"),
            risk="medium", rows=8, slot_index=4, multiplier=Decimal("1.5"),
            payout=Decimal("15"), net_result=Decimal("5"), is_demo=False,
        ))
        self.db.add(AviatorRound(
            id=uuid.uuid4(), round_code="AV1", status="crashed",
            crash_multiplier=Decimal("2.0"), player_count=1,
            total_stake=Decimal("5"), total_payout=Decimal("0"),
            system_fee=Decimal("0"),
        ))
        self.db.commit()

        preview = data_retention.preview_purge(self.db, "games_only")
        self.assertEqual(preview["confirmation_required"], "CLEAR_GAMES")
        self.assertFalse(preview["zeros_balances"])
        self.assertTrue(preview["keeps_payments"])
        self.assertTrue(preview["flushes_redis_game_keys"])
        self.assertEqual(preview["counts"]["deposits"], 0)
        self.assertGreaterEqual(preview["counts"]["bingo_games"], 1)
        self.assertGreaterEqual(preview["counts"]["wallet_transactions"], 2)

        async def run():
            with mock.patch(
                "app.admin.data_retention._flush_redis_game_keys",
                new=mock.AsyncMock(return_value=2),
            ):
                return await data_retention.run_purge(
                    self.db, self.admin,
                    option="games_only",
                    confirmation="CLEAR_GAMES",
                    reason="clear game history only",
                    request_id=uuid.uuid4(),
                )

        import asyncio
        result = asyncio.run(run())
        self.assertFalse(result["idempotent"])
        self.assertEqual(result["users_kept"], 3)
        self.assertEqual(result["balances_zeroed"], 0)
        self.assertEqual(result["redis_keys_deleted"], 2)

        self.assertEqual(self.db.query(Deposit).count(), 1)
        self.assertEqual(
            self.db.query(Deposit).one().sms_transaction_id, "KEEPDEP"
        )
        self.assertEqual(self.db.query(WithdrawRequest).count(), 1)
        self.assertEqual(self.db.query(BingoGame).count(), 0)
        self.assertEqual(self.db.query(BingoGameResult).count(), 0)
        self.assertEqual(self.db.query(PlinkoPlay).count(), 0)
        self.assertEqual(self.db.query(AviatorRound).count(), 0)
        self.assertEqual(self.db.query(User).count(), 3)

        remaining_types = {
            row.transaction_type
            for row in self.db.query(WalletTransaction).all()
        }
        self.assertEqual(remaining_types, {"ADMIN_ADJUSTMENT", "WITHDRAWAL"})
        self.assertEqual(self.db.query(WalletTransaction).count(), 2)

        self.db.refresh(self.user)
        self.db.refresh(self.admin)
        self.db.refresh(self.bot)
        self.assertEqual(self.user.balance, Decimal("100.00"))
        self.assertEqual(self.admin.balance, Decimal("500.00"))
        self.assertEqual(self.bot.balance, Decimal("50.00"))

        audits = self.db.query(AdminAuditLog).all()
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].action, "data.purge")
        self.assertEqual(audits[0].target_id, "games_only")
