"""Pattern-based Bingo claim validation.

The card is fixed at 5x5 (25 cells), so the marked state is packed into a
25-bit integer and each candidate pattern is a precomputed bitmask
(``app.bingo.patterns``). Validating a claim is then a handful of O(1)
bitwise AND/compare operations - O(number of patterns), independent of how
many numbers have been drawn.
"""

from __future__ import annotations

from app.bingo.patterns import DEFAULT_PATTERNS, Pattern

CardGrid = list[list[int | None]]


def compute_marked_mask(card: CardGrid, drawn_numbers: set[int]) -> int:
    """Marks are derived authoritatively from the numbers the server has
    actually drawn (plus the always-free center) - never from client-sent
    daub state - so a claim can't be forged by marking cells client-side."""

    mask = 0
    bit = 0

    for row in card:
        for value in row:
            if value is None or value in drawn_numbers:
                mask |= 1 << bit
            bit += 1

    return mask


def find_winning_pattern(
    card: CardGrid,
    drawn_numbers: set[int],
    patterns: tuple[Pattern, ...] = DEFAULT_PATTERNS,
) -> Pattern | None:
    marked_mask = compute_marked_mask(card, drawn_numbers)

    for pattern in patterns:
        if (marked_mask & pattern.mask) == pattern.mask:
            return pattern

    return None


def is_winning_card(
    card: CardGrid,
    drawn_numbers: set[int],
    patterns: tuple[Pattern, ...] = DEFAULT_PATTERNS,
) -> bool:
    return find_winning_pattern(card, drawn_numbers, patterns) is not None
