"""Crash multiplier generation and payout helpers."""

from __future__ import annotations

import math
import random
from decimal import Decimal, ROUND_DOWN

START_MULT = 1.0
MAX_CRASH = 15.0
MULT_GROWTH = 0.075  # mult = exp(MULT_GROWTH * sec), starts at 1.00x
MIN_CASHOUT_MULT = 1.01

# Distribution weights — most rounds end early (1x–3x), few climb higher.
INSTANT_CRASH_RATE = 0.07
LOW_BAND_RATE = 0.73  # of remaining mass after instant → 1.01 … 3.00
# leftover (~0.20 overall) → 3.10 … 15.00


def _skewed_unit(power: float = 1.45) -> float:
    """Random 0..1 biased toward smaller values (house-friendly)."""
    return random.random() ** power


def generate_crash_point() -> float:
    """
    Crash between 1.00x and 15.00x.
    Mostly 1.00–3.00; occasionally 3.10–15.00. Never above 15.
    """
    r = random.random()
    if r < INSTANT_CRASH_RATE:
        return 1.0

    if r < INSTANT_CRASH_RATE + LOW_BAND_RATE:
        # 1.01 … 3.00 — denser near 1.x
        value = 1.01 + _skewed_unit(1.55) * (3.0 - 1.01)
        return round(min(3.0, max(1.01, value)), 2)

    # 3.10 … 15.00 — denser near 3.x, rare near 15
    value = 3.10 + _skewed_unit(1.75) * (MAX_CRASH - 3.10)
    return round(min(MAX_CRASH, max(3.10, value)), 2)


def multiplier_at(elapsed_sec: float) -> float:
    raw = START_MULT * math.exp(MULT_GROWTH * max(0.0, elapsed_sec))
    return round(min(MAX_CRASH, raw), 2)


def pool_remaining(total_stake: Decimal, total_payout: Decimal) -> Decimal:
    return (total_stake - total_payout).quantize(Decimal("0.01"))


def cashout_payout(stake: Decimal, multiplier: float) -> Decimal:
    """Pay stake × live multiplier (capped at max crash display)."""
    mult = min(float(multiplier), MAX_CRASH)
    return (stake * Decimal(str(mult))).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
