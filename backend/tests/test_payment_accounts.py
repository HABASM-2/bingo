"""Tests for admin-managed deposit/withdraw payment accounts."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest import TestCase, mock

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin import payment_accounts, service
from app.db.database import Base
from app.models import PaymentAccount, User, WithdrawRequest


class PaymentAccountTests(TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()
        self.admin = User(
            telegram_id=1,
            username="@HaS365",
            first_name="Admin",
            referral_code="ADMIN",
            balance=Decimal("500.00"),
        )
        self.user = User(
            telegram_id=2,
            username="player",
            first_name="Player",
            referral_code="PLAYER",
            balance=Decimal("200.00"),
            language_code="en",
        )
        self.db.add_all([self.admin, self.user])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _create(self, **overrides):
        payload = {
            "kind": "deposit",
            "bank": "Telebirr",
            "account_name": "House",
            "account_number": "0911223344",
            "is_enabled": True,
            "sort_order": 10,
            "request_id": uuid.uuid4(),
        }
        payload.update(overrides)
        return payment_accounts.create_account(self.db, self.admin, **payload)

    @mock.patch("app.admin.helpers.settings.ADMIN_TELEGRAM_USERNAMES", "has365")
    def test_create_list_update_toggle_delete(self):
        created = self._create()
        self.assertFalse(created["idempotent"])
        self.assertEqual(created["kind"], "deposit")
        self.assertTrue(created["is_enabled"])

        listed = payment_accounts.list_accounts(self.db, kind="deposit")
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["account_number"], "0911223344")

        rid = uuid.uuid4()
        updated = payment_accounts.update_account(
            self.db,
            self.admin,
            uuid.UUID(created["id"]),
            bank="CBE",
            account_name=None,
            account_number=None,
            is_enabled=False,
            sort_order=None,
            request_id=rid,
        )
        self.assertEqual(updated["bank"], "CBE")
        self.assertFalse(updated["is_enabled"])

        enabled_only = payment_accounts.list_enabled_public(self.db, "deposit")
        self.assertEqual(enabled_only["total"], 0)

        payment_accounts.update_account(
            self.db,
            self.admin,
            uuid.UUID(created["id"]),
            bank=None,
            account_name=None,
            account_number=None,
            is_enabled=True,
            sort_order=None,
            request_id=uuid.uuid4(),
        )
        enabled_only = payment_accounts.list_enabled_public(self.db, "deposit")
        self.assertEqual(enabled_only["total"], 1)

        deleted = payment_accounts.delete_account(
            self.db, self.admin, uuid.UUID(created["id"]), uuid.uuid4()
        )
        self.assertTrue(deleted["deleted"])
        self.assertEqual(payment_accounts.list_accounts(self.db)["total"], 0)

    def test_enabled_filter_hides_disabled(self):
        on = self._create(account_number="1001", bank="A")
        off = self._create(
            account_number="1002",
            bank="B",
            is_enabled=False,
            request_id=uuid.uuid4(),
        )
        public = payment_accounts.list_enabled_public(self.db, "deposit")
        ids = {item["id"] for item in public["items"]}
        self.assertIn(on["id"], ids)
        self.assertNotIn(off["id"], ids)

    def test_withdraw_kind_separate_from_deposit(self):
        self._create(kind="deposit", bank="Telebirr", account_number="1")
        self._create(
            kind="withdraw",
            bank="Telebirr",
            account_number="1",
            request_id=uuid.uuid4(),
        )
        deposits = payment_accounts.list_enabled_public(self.db, "deposit")
        withdraws = payment_accounts.list_enabled_public(self.db, "withdraw")
        self.assertEqual(deposits["total"], 1)
        self.assertEqual(withdraws["total"], 1)

    def test_approve_withdrawal_records_paid_from_account(self):
        house = self._create(
            kind="withdraw",
            bank="CBE",
            account_number="999",
            request_id=uuid.uuid4(),
        )
        req = WithdrawRequest(
            user_id=self.user.id,
            method="TELEBIRR",
            account_name="Player",
            account_number="0900000000",
            amount=Decimal("50.00"),
            fee=Decimal("0"),
            status="PENDING",
        )
        self.db.add(req)
        self.db.commit()

        result = service.decide_withdrawal(
            self.db,
            self.admin,
            req.id,
            True,
            None,
            uuid.uuid4(),
            paid_from_account_id=uuid.UUID(house["id"]),
        )
        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(result["paid_from_account_id"], house["id"])
        self.db.refresh(req)
        self.assertEqual(str(req.paid_from_account_id), house["id"])

    def test_approve_rejects_disabled_payout_account(self):
        house = self._create(
            kind="withdraw",
            bank="CBE",
            account_number="888",
            is_enabled=False,
            request_id=uuid.uuid4(),
        )
        req = WithdrawRequest(
            user_id=self.user.id,
            method="CBE",
            account_name="Player",
            account_number="0900000001",
            amount=Decimal("20.00"),
            fee=Decimal("0"),
            status="PENDING",
        )
        self.db.add(req)
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            service.decide_withdrawal(
                self.db,
                self.admin,
                req.id,
                True,
                None,
                uuid.uuid4(),
                paid_from_account_id=uuid.UUID(house["id"]),
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_create_is_idempotent(self):
        request_id = uuid.uuid4()
        first = self._create(request_id=request_id)
        second = self._create(request_id=request_id, account_number="different")
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.db.query(PaymentAccount).count(), 1)
