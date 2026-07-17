"""Tests for Telegram bot language persistence and Mini App deep links."""

from __future__ import annotations

from decimal import Decimal
from unittest import TestCase

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.bot.i18n import COMMAND_KEYS, t
from app.bot.links import (
    VALID_GAMES,
    build_startapp_payload,
    build_webapp_url,
    normalize_game_id,
    parse_start_param,
)
from app.bot.locale import (
    DEFAULT_LOCALE,
    get_user_locale,
    hint_locale_from_telegram,
    normalize_locale,
    set_user_locale,
)
from app.db.database import Base
from app.models.user import User


class LocaleHelperTests(TestCase):
    def test_default_is_english(self):
        self.assertEqual(DEFAULT_LOCALE, "en")
        self.assertEqual(hint_locale_from_telegram(None), "en")
        self.assertEqual(hint_locale_from_telegram("fr"), "en")

    def test_normalize_amharic_variants(self):
        self.assertEqual(normalize_locale("am"), "am")
        self.assertEqual(normalize_locale("am-ET"), "am")
        self.assertEqual(normalize_locale("AM"), "am")

    def test_telegram_hint_amharic(self):
        self.assertEqual(hint_locale_from_telegram("am"), "am")
        self.assertEqual(hint_locale_from_telegram("am-et"), "am")


class LocalePersistenceTests(TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine, tables=[User.__table__])
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()

    def tearDown(self):
        self.db.close()

    def _user(self, telegram_id: int = 42, language_code: str | None = None) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name="Tester",
            referral_code=f"U{telegram_id}",
            balance=Decimal("0"),
            language_code=language_code,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def test_unregistered_defaults_to_en(self):
        self.assertEqual(get_user_locale(self.db, 999), "en")

    def test_persisted_preference_wins(self):
        self._user(1, language_code="am")
        self.assertEqual(
            get_user_locale(self.db, 1, telegram_language_code="en"),
            "am",
        )

    def test_set_user_locale_persists(self):
        self._user(2, language_code="en")
        self.assertEqual(set_user_locale(self.db, 2, "am"), "am")
        self.db.expire_all()
        user = self.db.query(User).filter(User.telegram_id == 2).first()
        self.assertEqual(user.language_code, "am")
        self.assertEqual(get_user_locale(self.db, 2), "am")

    def test_unknown_stored_falls_back_to_hint(self):
        self._user(3, language_code="fr")
        self.assertEqual(
            get_user_locale(self.db, 3, telegram_language_code="am"),
            "am",
        )


class WebappLinkTests(TestCase):
    def test_build_game_and_lang_query(self):
        url = build_webapp_url(
            "dama",
            lang="am",
            base_url="https://app.example.com/",
        )
        self.assertTrue(url.startswith("https://app.example.com/"))
        self.assertIn("game=dama", url)
        self.assertIn("lang=am", url)

    def test_home_omits_game_param(self):
        url = build_webapp_url(
            "home",
            lang="en",
            base_url="https://app.example.com",
        )
        self.assertIn("lang=en", url)
        self.assertNotIn("game=", url)

    def test_preserves_existing_query(self):
        url = build_webapp_url(
            "bingo",
            lang="en",
            base_url="https://app.example.com/?foo=1",
        )
        self.assertIn("foo=1", url)
        self.assertIn("game=bingo", url)

    def test_normalize_and_parse_start_param(self):
        self.assertEqual(normalize_game_id("Dama"), "dama")
        self.assertIsNone(normalize_game_id("chess"))
        self.assertEqual(parse_start_param("dama"), ("dama", None))
        self.assertEqual(parse_start_param("dama_am"), ("dama", "am"))
        self.assertEqual(parse_start_param("game_plinko_en"), ("plinko", "en"))
        self.assertEqual(VALID_GAMES, frozenset({"bingo", "dama", "aviator", "plinko", "lotto", "home"}))

    def test_startapp_payload(self):
        self.assertEqual(build_startapp_payload("aviator"), "aviator")
        self.assertEqual(build_startapp_payload("lotto", lang="am"), "lotto_am")


class BotI18nTests(TestCase):
    def test_command_keys_cover_modern_commands(self):
        commands = {name for name, _ in COMMAND_KEYS}
        for expected in (
            "start",
            "play",
            "games",
            "bingo",
            "dama",
            "aviator",
            "plinko",
            "lotto",
            "balance",
            "language",
            "help",
        ):
            self.assertIn(expected, commands)

    def test_amharic_welcome_differs_from_english(self):
        en = t("en", "menu.games")
        am = t("am", "menu.games")
        self.assertNotEqual(en, am)
        self.assertIn("Games", en)
        self.assertIn("ጨዋታ", am)

    def test_withdrawal_decision_messages_exist_in_both_locales(self):
        for key in (
            "withdraw.decision.approved",
            "withdraw.decision.rejected",
            "withdraw.decision.no_reason",
        ):
            en = t("en", key, amount="1", ref="r", balance="2", reason="x")
            am = t("am", key, amount="1", ref="r", balance="2", reason="x")
            self.assertNotEqual(en, key)
            self.assertNotEqual(am, key)
            if key != "withdraw.decision.no_reason":
                self.assertIn("BRIGHT GAMES", en)
                self.assertIn("BRIGHT GAMES", am)

    def test_bot_module_imports(self):
        from app.bot import bot, handlers, keyboards, links, locale, notify  # noqa: F401
        from app.bot.bot import create_bot  # noqa: F401
        self.assertTrue(callable(create_bot))
        self.assertTrue(callable(notify.notify_withdrawal_decision))
