"""Dama stake validation — minimum 5 ETB."""

from decimal import Decimal

import pytest

from app.dama.wallet import MIN_STAKE, MAX_STAKE, parse_stake


def test_min_stake_is_five():
    assert MIN_STAKE == Decimal("5")


def test_parse_stake_rejects_below_min():
    with pytest.raises(ValueError, match="between"):
        parse_stake("1")
    with pytest.raises(ValueError, match="between"):
        parse_stake("4.99")


def test_parse_stake_accepts_min_and_presets():
    assert parse_stake("5") == Decimal("5.00")
    assert parse_stake("10") == Decimal("10.00")
    assert parse_stake("15") == Decimal("15.00")


def test_parse_stake_rejects_above_max():
    with pytest.raises(ValueError, match="between"):
        parse_stake(str(MAX_STAKE + 1))
