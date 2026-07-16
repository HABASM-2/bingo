/** Ethiopian-style Dama (checkers) on an 8×8 board with flying kings. */

export type Side = "red" | "black";
export type PieceKind = "man" | "king";

export interface Piece {
  side: Side;
  kind: PieceKind;
}

/** Board is row-major; null = empty. Dark playable squares only matter for UI. */
export type Board = (Piece | null)[];

export interface Move {
  from: number;
  to: number;
  /** Captured square indices in jump order (empty for quiet moves). */
  captures: number[];
  /** Landing squares visited after `from` (for multi-jump animation). */
  path: number[];
  promote: boolean;
}

export type GameMode = "ai" | "local" | "online";

export const BOARD_SIZE = 8;
export const SQUARE_COUNT = BOARD_SIZE * BOARD_SIZE;

export function idx(row: number, col: number): number {
  return row * BOARD_SIZE + col;
}

export function rowOf(i: number): number {
  return Math.floor(i / BOARD_SIZE);
}

export function colOf(i: number): number {
  return i % BOARD_SIZE;
}

export function opposite(side: Side): Side {
  return side === "red" ? "black" : "red";
}

/** Dark squares are playable (row+col odd). */
export function isPlayable(i: number): boolean {
  const r = rowOf(i);
  const c = colOf(i);
  return (r + c) % 2 === 1;
}

export function createInitialBoard(): Board {
  const board: Board = Array(SQUARE_COUNT).fill(null);

  for (let i = 0; i < SQUARE_COUNT; i++) {
    if (!isPlayable(i)) continue;
    const r = rowOf(i);
    if (r < 3) board[i] = { side: "black", kind: "man" };
    else if (r > 4) board[i] = { side: "red", kind: "man" };
  }

  return board;
}

function inBounds(row: number, col: number): boolean {
  return row >= 0 && row < BOARD_SIZE && col >= 0 && col < BOARD_SIZE;
}

function cloneBoard(board: Board): Board {
  return board.map((p) => (p ? { ...p } : null));
}

/** Quiet moves for men stay forward only. */
function manMoveDirs(side: Side): Array<[number, number]> {
  return side === "red"
    ? [
        [-1, -1],
        [-1, 1],
      ]
    : [
        [1, -1],
        [1, 1],
      ];
}

/** Men may capture in all four diagonal directions (back-eating allowed). */
const MAN_CAPTURE_DIRS: Array<[number, number]> = [
  [-1, -1],
  [-1, 1],
  [1, -1],
  [1, 1],
];

const KING_DIRS: Array<[number, number]> = [
  [-1, -1],
  [-1, 1],
  [1, -1],
  [1, 1],
];

function shouldPromote(side: Side, to: number): boolean {
  const r = rowOf(to);
  return side === "red" ? r === 0 : r === BOARD_SIZE - 1;
}

/**
 * Collect captures for a piece. Men jump adjacent enemies (any diagonal).
 * Kings fly any distance. If a man lands on the crowning row mid-sequence,
 * the move ends there — no immediate king capture on the same turn.
 */
function collectCaptures(
  board: Board,
  from: number,
  side: Side,
  kind: PieceKind,
  origin: number,
  landings: number[],
  capturedOrdered: number[],
  capturedSet: Set<number>,
  results: Move[],
): void {
  let extended = false;
  const dirs = kind === "king" ? KING_DIRS : MAN_CAPTURE_DIRS;
  const fr = rowOf(from);
  const fc = colOf(from);

  for (const [dr, dc] of dirs) {
    if (kind === "man") {
      const er = fr + dr;
      const ec = fc + dc;
      const lr = fr + 2 * dr;
      const lc = fc + 2 * dc;
      if (!inBounds(er, ec) || !inBounds(lr, lc)) continue;

      const enemyIdx = idx(er, ec);
      const landIdx = idx(lr, lc);
      const enemy = board[enemyIdx];
      if (!enemy || enemy.side === side) continue;
      if (capturedSet.has(enemyIdx)) continue;
      if (board[landIdx] !== null) continue;

      const nextBoard = cloneBoard(board);
      nextBoard[from] = null;
      nextBoard[enemyIdx] = null;

      const nextCapturedOrdered = [...capturedOrdered, enemyIdx];
      const nextCapturedSet = new Set(capturedSet);
      nextCapturedSet.add(enemyIdx);
      const nextLandings = [...landings, landIdx];
      const promotes = shouldPromote(side, landIdx);

      if (promotes) {
        // Become king and end the turn — no further eating this move.
        nextBoard[landIdx] = { side, kind: "king" };
        results.push({
          from: origin,
          to: landIdx,
          captures: nextCapturedOrdered,
          path: nextLandings,
          promote: true,
        });
        extended = true;
        continue;
      }

      nextBoard[landIdx] = { side, kind: "man" };
      const before = results.length;
      collectCaptures(
        nextBoard,
        landIdx,
        side,
        "man",
        origin,
        nextLandings,
        nextCapturedOrdered,
        nextCapturedSet,
        results,
      );
      if (results.length === before) {
        results.push({
          from: origin,
          to: landIdx,
          captures: nextCapturedOrdered,
          path: nextLandings,
          promote: false,
        });
      }
      extended = true;
    } else {
      let er = fr + dr;
      let ec = fc + dc;
      while (inBounds(er, ec) && board[idx(er, ec)] === null) {
        er += dr;
        ec += dc;
      }
      if (!inBounds(er, ec)) continue;

      const enemyIdx = idx(er, ec);
      const enemy = board[enemyIdx];
      if (!enemy || enemy.side === side) continue;
      if (capturedSet.has(enemyIdx)) continue;

      let lr = er + dr;
      let lc = ec + dc;
      while (inBounds(lr, lc) && board[idx(lr, lc)] === null) {
        const landIdx = idx(lr, lc);
        const nextBoard = cloneBoard(board);
        nextBoard[from] = null;
        nextBoard[enemyIdx] = null;
        nextBoard[landIdx] = { side, kind: "king" };

        const nextCapturedOrdered = [...capturedOrdered, enemyIdx];
        const nextCapturedSet = new Set(capturedSet);
        nextCapturedSet.add(enemyIdx);
        const nextLandings = [...landings, landIdx];

        const before = results.length;
        collectCaptures(
          nextBoard,
          landIdx,
          side,
          "king",
          origin,
          nextLandings,
          nextCapturedOrdered,
          nextCapturedSet,
          results,
        );
        if (results.length === before) {
          results.push({
            from: origin,
            to: landIdx,
            captures: nextCapturedOrdered,
            path: nextLandings,
            promote: false,
          });
        }
        extended = true;
        lr += dr;
        lc += dc;
      }
    }
  }

  void extended;
}

function quietMovesFor(board: Board, from: number, side: Side, kind: PieceKind): Move[] {
  const moves: Move[] = [];
  const fr = rowOf(from);
  const fc = colOf(from);
  const dirs = kind === "king" ? KING_DIRS : manMoveDirs(side);

  for (const [dr, dc] of dirs) {
    if (kind === "man") {
      const nr = fr + dr;
      const nc = fc + dc;
      if (!inBounds(nr, nc)) continue;
      const to = idx(nr, nc);
      if (board[to] !== null) continue;
      moves.push({
        from,
        to,
        captures: [],
        path: [to],
        promote: shouldPromote(side, to),
      });
    } else {
      let nr = fr + dr;
      let nc = fc + dc;
      while (inBounds(nr, nc) && board[idx(nr, nc)] === null) {
        const to = idx(nr, nc);
        moves.push({
          from,
          to,
          captures: [],
          path: [to],
          promote: false,
        });
        nr += dr;
        nc += dc;
      }
    }
  }

  return moves;
}

/** All legal moves for ``side``. Captures are mandatory when available. */
export function legalMoves(board: Board, side: Side): Move[] {
  const captures: Move[] = [];
  const quiet: Move[] = [];

  for (let i = 0; i < SQUARE_COUNT; i++) {
    const piece = board[i];
    if (!piece || piece.side !== side) continue;

    const pieceCaptures: Move[] = [];
    collectCaptures(
      board,
      i,
      side,
      piece.kind,
      i,
      [],
      [],
      new Set(),
      pieceCaptures,
    );
    captures.push(...pieceCaptures);

    if (pieceCaptures.length === 0) {
      quiet.push(...quietMovesFor(board, i, side, piece.kind));
    }
  }

  if (captures.length > 0) {
    const maxLen = Math.max(...captures.map((m) => m.captures.length));
    return captures.filter((m) => m.captures.length === maxLen);
  }

  return quiet;
}

export function applyMove(board: Board, move: Move): Board {
  const next = cloneBoard(board);
  const piece = next[move.from];
  if (!piece) return next;

  next[move.from] = null;
  for (const c of move.captures) next[c] = null;

  let kind = piece.kind;
  if (move.promote || shouldPromote(piece.side, move.to)) {
    kind = "king";
  }
  next[move.to] = { side: piece.side, kind };
  return next;
}

export type Outcome = "red" | "black" | "draw" | null;

export function evaluateOutcome(board: Board, sideToMove: Side): Outcome {
  const moves = legalMoves(board, sideToMove);
  if (moves.length > 0) return null;

  const hasRed = board.some((p) => p?.side === "red");
  const hasBlack = board.some((p) => p?.side === "black");
  if (!hasRed && !hasBlack) return "draw";
  if (!hasRed) return "black";
  if (!hasBlack) return "red";
  return opposite(sideToMove);
}

export function countPieces(board: Board, side: Side): { men: number; kings: number } {
  let men = 0;
  let kings = 0;
  for (const p of board) {
    if (!p || p.side !== side) continue;
    if (p.kind === "king") kings += 1;
    else men += 1;
  }
  return { men, kings };
}

export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
