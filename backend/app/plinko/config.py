"""Authoritative Plinko rules and multiplier tables.

House edge lives only in these multipliers (target RTP ~99%). Settlement pays
``stake * multiplier`` with no separate service fee / rake / commission.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from math import comb

ALLOWED_ROWS = (8, 10, 12, 14, 16)
ALLOWED_RISKS = ("low", "medium", "high")
MIN_STAKE = Decimal("1.00")
MAX_STAKE = Decimal("500.00")

# Player-friendlier than a hard 98% cut; kept under 100% after quantization.
TARGET_RTP = Decimal("0.9900")
_STEP = Decimal("0.01")
_RISK_BASE = {
    # Low: flatter. Medium: Stake-like outer edges. High: sharper extremes.
    "low": Decimal("1.22"),
    "medium": Decimal("1.58"),
    "high": Decimal("2.20"),
}
# Snap near-center bins onto clean labels so UI "1.0x" / "0.4x" match settlement.
_NICE = tuple(
    Decimal(str(value))
    for value in (
        0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9,
        1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9,
        2.0, 2.1, 2.2, 2.5,
    )
)


def _snap_nice(value: Decimal, tol: Decimal) -> Decimal:
    best = value
    for candidate in _NICE:
        delta = abs(candidate - value)
        if delta <= tol and delta < abs(best - value):
            best = candidate
    return best


def _build_table(rows: int, risk: str) -> tuple[Decimal, ...]:
    center = Decimal(rows) / 2
    center_f = float(center)
    base = _RISK_BASE[risk]
    raw = tuple(base ** abs(Decimal(i) - center) for i in range(rows + 1))
    expected = sum(
        (Decimal(comb(rows, i)) / Decimal(2**rows)) * raw[i]
        for i in range(rows + 1)
    )
    values = [
        (value * (TARGET_RTP / expected)).quantize(_STEP, rounding=ROUND_HALF_UP)
        for value in raw
    ]
    for index, value in enumerate(values):
        if abs(index - center_f) <= 3:
            values[index] = _snap_nice(value, Decimal("0.04"))
    for index in range(len(values) // 2):
        avg = ((values[index] + values[-1 - index]) / 2).quantize(
            _STEP, rounding=ROUND_HALF_UP
        )
        values[index] = avg
        values[-1 - index] = avg

    # Edges absorb residual RTP drift from center snaps.
    rtp_now = sum(
        (Decimal(comb(rows, i)) / Decimal(2**rows)) * values[i]
        for i in range(rows + 1)
    )
    scale = TARGET_RTP / rtp_now
    values = [
        (value * scale).quantize(_STEP, rounding=ROUND_HALF_UP) for value in values
    ]
    for index, value in enumerate(values):
        if abs(index - center_f) <= 2:
            values[index] = _snap_nice(value, Decimal("0.06"))
    for index in range(len(values) // 2):
        avg = ((values[index] + values[-1 - index]) / 2).quantize(
            _STEP, rounding=ROUND_HALF_UP
        )
        values[index] = max(_STEP, avg)
        values[-1 - index] = max(_STEP, avg)
    return tuple(values)


MULTIPLIER_TABLES = {
    risk: {rows: _build_table(rows, risk) for rows in ALLOWED_ROWS}
    for risk in ALLOWED_RISKS
}


def expected_rtp(rows: int, risk: str) -> Decimal:
    table = MULTIPLIER_TABLES[risk][rows]
    return sum(
        (Decimal(comb(rows, i)) / Decimal(2**rows)) * table[i]
        for i in range(rows + 1)
    )
