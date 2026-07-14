"""Winning pattern definitions for Bingo 75.

Patterns are described as a set of (row, col) cells on the 5x5 card and are
compiled into a bitmask so validation is a single AND + compare per pattern
(see ``app.bingo.validator``). New patterns (four corners, full card, ...)
can be added to ``PATTERN_REGISTRY`` without touching the validator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CARD_SIZE = 5
FREE_ROW = 2
FREE_COL = 2


def cell_index(row: int, col: int) -> int:
    return row * CARD_SIZE + col


def _mask_from_cells(cells: tuple[tuple[int, int], ...]) -> int:
    mask = 0

    for row, col in cells:
        mask |= 1 << cell_index(row, col)

    return mask


@dataclass(frozen=True)
class Pattern:
    name: str
    cells: tuple[tuple[int, int], ...]
    mask: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "mask", _mask_from_cells(self.cells))


def _row_pattern(row: int) -> Pattern:
    return Pattern(
        name=f"row_{row}",
        cells=tuple((row, col) for col in range(CARD_SIZE)),
    )


def _col_pattern(col: int) -> Pattern:
    return Pattern(
        name=f"col_{col}",
        cells=tuple((row, col) for row in range(CARD_SIZE)),
    )


_DIAGONAL_TOP_LEFT = Pattern(
    name="diagonal_top_left",
    cells=tuple((i, i) for i in range(CARD_SIZE)),
)

_DIAGONAL_TOP_RIGHT = Pattern(
    name="diagonal_top_right",
    cells=tuple((i, CARD_SIZE - 1 - i) for i in range(CARD_SIZE)),
)

LINE_PATTERNS: tuple[Pattern, ...] = (
    *(_row_pattern(row) for row in range(CARD_SIZE)),
    *(_col_pattern(col) for col in range(CARD_SIZE)),
    _DIAGONAL_TOP_LEFT,
    _DIAGONAL_TOP_RIGHT,
)

FOUR_CORNERS = Pattern(
    name="four_corners",
    cells=(
        (0, 0),
        (0, CARD_SIZE - 1),
        (CARD_SIZE - 1, 0),
        (CARD_SIZE - 1, CARD_SIZE - 1),
    ),
)

FULL_CARD = Pattern(
    name="full_card",
    cells=tuple(
        (row, col)
        for row in range(CARD_SIZE)
        for col in range(CARD_SIZE)
    ),
)

# Default win condition: any full row, column, or diagonal.
DEFAULT_PATTERNS: tuple[Pattern, ...] = LINE_PATTERNS

# Registry so future modes (four corners, full card / blackout, ...) can be
# enabled per-room just by referencing their name.
PATTERN_REGISTRY: dict[str, Pattern] = {
    pattern.name: pattern
    for pattern in (*LINE_PATTERNS, FOUR_CORNERS, FULL_CARD)
}


def get_patterns(names: list[str] | None = None) -> tuple[Pattern, ...]:
    """Resolve a list of pattern names to Pattern objects, falling back to
    the default line patterns when no names are provided."""

    if not names:
        return DEFAULT_PATTERNS

    return tuple(
        PATTERN_REGISTRY[name]
        for name in names
        if name in PATTERN_REGISTRY
    )
