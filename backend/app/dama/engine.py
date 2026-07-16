"""Ethiopian-style Dama rules (mirrors frontend/src/games/dama/engine.ts)."""

from __future__ import annotations

from copy import deepcopy
from typing import Literal

Side = Literal["red", "black"]
PieceKind = Literal["man", "king"]

BOARD_SIZE = 8
SQUARE_COUNT = BOARD_SIZE * BOARD_SIZE

Piece = dict  # {side, kind}
Board = list  # length 64, Piece | None
Move = dict  # {from, to, captures, path, promote}


def idx(row: int, col: int) -> int:
    return row * BOARD_SIZE + col


def row_of(i: int) -> int:
    return i // BOARD_SIZE


def col_of(i: int) -> int:
    return i % BOARD_SIZE


def opposite(side: Side) -> Side:
    return "black" if side == "red" else "red"


def is_playable(i: int) -> bool:
    return (row_of(i) + col_of(i)) % 2 == 1


def create_initial_board() -> Board:
    board: Board = [None] * SQUARE_COUNT
    for i in range(SQUARE_COUNT):
        if not is_playable(i):
            continue
        r = row_of(i)
        if r < 3:
            board[i] = {"side": "black", "kind": "man"}
        elif r > 4:
            board[i] = {"side": "red", "kind": "man"}
    return board


def _in_bounds(row: int, col: int) -> bool:
    return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE


def _clone(board: Board) -> Board:
    return deepcopy(board)


def _man_move_dirs(side: Side) -> list[tuple[int, int]]:
    return [(-1, -1), (-1, 1)] if side == "red" else [(1, -1), (1, 1)]


MAN_CAPTURE_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
KING_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]


def _should_promote(side: Side, to: int) -> bool:
    r = row_of(to)
    return r == 0 if side == "red" else r == BOARD_SIZE - 1


def _collect_captures(
    board: Board,
    from_sq: int,
    side: Side,
    kind: PieceKind,
    origin: int,
    landings: list[int],
    captured_ordered: list[int],
    captured_set: set[int],
    results: list[Move],
) -> None:
    dirs = KING_DIRS if kind == "king" else MAN_CAPTURE_DIRS
    fr, fc = row_of(from_sq), col_of(from_sq)

    for dr, dc in dirs:
        if kind == "man":
            er, ec = fr + dr, fc + dc
            lr, lc = fr + 2 * dr, fc + 2 * dc
            if not _in_bounds(er, ec) or not _in_bounds(lr, lc):
                continue

            enemy_idx = idx(er, ec)
            land_idx = idx(lr, lc)
            enemy = board[enemy_idx]
            if not enemy or enemy["side"] == side:
                continue
            if enemy_idx in captured_set or board[land_idx] is not None:
                continue

            next_board = _clone(board)
            next_board[from_sq] = None
            next_board[enemy_idx] = None

            next_captured_ordered = [*captured_ordered, enemy_idx]
            next_captured_set = set(captured_set)
            next_captured_set.add(enemy_idx)
            next_landings = [*landings, land_idx]
            promotes = _should_promote(side, land_idx)

            if promotes:
                next_board[land_idx] = {"side": side, "kind": "king"}
                results.append(
                    {
                        "from": origin,
                        "to": land_idx,
                        "captures": next_captured_ordered,
                        "path": next_landings,
                        "promote": True,
                    }
                )
                continue

            next_board[land_idx] = {"side": side, "kind": "man"}
            before = len(results)
            _collect_captures(
                next_board,
                land_idx,
                side,
                "man",
                origin,
                next_landings,
                next_captured_ordered,
                next_captured_set,
                results,
            )
            if len(results) == before:
                results.append(
                    {
                        "from": origin,
                        "to": land_idx,
                        "captures": next_captured_ordered,
                        "path": next_landings,
                        "promote": False,
                    }
                )
        else:
            er, ec = fr + dr, fc + dc
            while _in_bounds(er, ec) and board[idx(er, ec)] is None:
                er += dr
                ec += dc
            if not _in_bounds(er, ec):
                continue

            enemy_idx = idx(er, ec)
            enemy = board[enemy_idx]
            if not enemy or enemy["side"] == side or enemy_idx in captured_set:
                continue

            lr, lc = er + dr, ec + dc
            while _in_bounds(lr, lc) and board[idx(lr, lc)] is None:
                land_idx = idx(lr, lc)
                next_board = _clone(board)
                next_board[from_sq] = None
                next_board[enemy_idx] = None
                next_board[land_idx] = {"side": side, "kind": "king"}

                next_captured_ordered = [*captured_ordered, enemy_idx]
                next_captured_set = set(captured_set)
                next_captured_set.add(enemy_idx)
                next_landings = [*landings, land_idx]

                before = len(results)
                _collect_captures(
                    next_board,
                    land_idx,
                    side,
                    "king",
                    origin,
                    next_landings,
                    next_captured_ordered,
                    next_captured_set,
                    results,
                )
                if len(results) == before:
                    results.append(
                        {
                            "from": origin,
                            "to": land_idx,
                            "captures": next_captured_ordered,
                            "path": next_landings,
                            "promote": False,
                        }
                    )
                lr += dr
                lc += dc


def _quiet_moves(board: Board, from_sq: int, side: Side, kind: PieceKind) -> list[Move]:
    moves: list[Move] = []
    fr, fc = row_of(from_sq), col_of(from_sq)
    dirs = KING_DIRS if kind == "king" else _man_move_dirs(side)

    for dr, dc in dirs:
        if kind == "man":
            nr, nc = fr + dr, fc + dc
            if not _in_bounds(nr, nc):
                continue
            to = idx(nr, nc)
            if board[to] is not None:
                continue
            moves.append(
                {
                    "from": from_sq,
                    "to": to,
                    "captures": [],
                    "path": [to],
                    "promote": _should_promote(side, to),
                }
            )
        else:
            nr, nc = fr + dr, fc + dc
            while _in_bounds(nr, nc) and board[idx(nr, nc)] is None:
                to = idx(nr, nc)
                moves.append(
                    {
                        "from": from_sq,
                        "to": to,
                        "captures": [],
                        "path": [to],
                        "promote": False,
                    }
                )
                nr += dr
                nc += dc
    return moves


def legal_moves(board: Board, side: Side) -> list[Move]:
    captures: list[Move] = []
    quiet: list[Move] = []

    for i in range(SQUARE_COUNT):
        piece = board[i]
        if not piece or piece["side"] != side:
            continue

        piece_captures: list[Move] = []
        _collect_captures(
            board, i, side, piece["kind"], i, [], [], set(), piece_captures
        )
        captures.extend(piece_captures)

        if not piece_captures:
            quiet.extend(_quiet_moves(board, i, side, piece["kind"]))

    if captures:
        max_len = max(len(m["captures"]) for m in captures)
        return [m for m in captures if len(m["captures"]) == max_len]
    return quiet


def apply_move(board: Board, move: Move) -> Board:
    next_board = _clone(board)
    piece = next_board[move["from"]]
    if not piece:
        return next_board

    next_board[move["from"]] = None
    for c in move["captures"]:
        next_board[c] = None

    kind = piece["kind"]
    if move.get("promote") or _should_promote(piece["side"], move["to"]):
        kind = "king"
    next_board[move["to"]] = {"side": piece["side"], "kind": kind}
    return next_board


def evaluate_outcome(board: Board, side_to_move: Side) -> Side | Literal["draw"] | None:
    moves = legal_moves(board, side_to_move)
    if moves:
        return None

    has_red = any(p and p["side"] == "red" for p in board)
    has_black = any(p and p["side"] == "black" for p in board)
    if not has_red and not has_black:
        return "draw"
    if not has_red:
        return "black"
    if not has_black:
        return "red"
    return opposite(side_to_move)


def find_legal_move(board: Board, side: Side, from_sq: int, to_sq: int) -> Move | None:
    for move in legal_moves(board, side):
        if move["from"] == from_sq and move["to"] == to_sq:
            return move
    return None
