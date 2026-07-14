"""5x5 Bingo cartela generation.

Column ranges follow standard Bingo 75 rules:
  B -> 1-15, I -> 16-30, N -> 31-45 (center is FREE), G -> 46-60, O -> 61-75

Cartelas are *deterministic* per board id (1..400): the same board number
always produces the same 5x5 pattern. The frontend mirrors this exact
algorithm (see ``frontend/src/utils/cartela.ts``) so it can render lobby
previews and auto-dab live cards without a round-trip, while the server
stays the single source of truth for win validation.
"""

from __future__ import annotations

import random

from app.bingo.patterns import CARD_SIZE, FREE_COL, FREE_ROW

CardGrid = list[list[int | None]]

COLUMN_RANGES: dict[int, tuple[int, int]] = {
    0: (1, 15),
    1: (16, 30),
    2: (31, 45),
    3: (46, 60),
    4: (61, 75),
}

COLUMN_LETTERS = ("B", "I", "N", "G", "O")

_UINT32 = 0xFFFFFFFF


def _make_rng(seed: int):
    """Tiny LCG (Numerical Recipes constants) reproduced byte-for-byte in
    the TypeScript client. Returns a callable yielding floats in [0, 1)."""

    state = (seed * 2654435761) & _UINT32

    def rnd() -> float:
        nonlocal state
        state = (state * 1664525 + 1013904223) & _UINT32
        return state / 0x100000000

    return rnd


def _shuffled_pool(low: int, high: int, rnd) -> list[int]:
    """Ascending Fisher-Yates shuffle - must match the TS implementation."""

    pool = list(range(low, high + 1))

    for i in range(len(pool) - 1):
        j = i + int(rnd() * (len(pool) - i))
        pool[i], pool[j] = pool[j], pool[i]

    return pool


def generate_card_for_board(board_id: int) -> CardGrid:
    """Deterministic 5x5 cartela for a board id (FREE center)."""

    rnd = _make_rng(board_id)
    card: CardGrid = [[None] * CARD_SIZE for _ in range(CARD_SIZE)]

    for col in range(CARD_SIZE):
        low, high = COLUMN_RANGES[col]
        pool = _shuffled_pool(low, high, rnd)
        idx = 0

        for row in range(CARD_SIZE):
            if row == FREE_ROW and col == FREE_COL:
                card[row][col] = None
                continue

            card[row][col] = pool[idx]
            idx += 1

    return card


def generate_card() -> CardGrid:
    """Random (non-deterministic) cartela - kept for tests / ad-hoc use."""

    board_id = random.randint(1, 1_000_000)

    return generate_card_for_board(board_id)


def empty_marks() -> list[list[bool]]:
    """Marked-cell grid with the FREE center pre-daubed."""

    marks = [[False] * CARD_SIZE for _ in range(CARD_SIZE)]
    marks[FREE_ROW][FREE_COL] = True

    return marks
