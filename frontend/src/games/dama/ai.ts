import {
  type Board,
  type Move,
  type Side,
  applyMove,
  evaluateOutcome,
  legalMoves,
  opposite,
  rowOf,
  colOf,
} from "./engine";

const MAN_VALUE = 100;
const KING_VALUE = 260;

/** Prefer center / advanced positions lightly. */
function positionBonus(index: number, side: Side, isKing: boolean): number {
  const r = rowOf(index);
  const c = colOf(index);
  const center = 3.5;
  const centerScore = 6 - (Math.abs(c - center) + Math.abs(r - center));
  const advance = side === "red" ? 7 - r : r;
  return isKing ? centerScore * 2 : centerScore + advance * 3;
}

function evaluate(board: Board, perspective: Side): number {
  const outcome = evaluateOutcome(board, perspective);
  if (outcome === perspective) return 50_000;
  if (outcome === opposite(perspective)) return -50_000;
  if (outcome === "draw") return 0;

  let score = 0;
  for (let i = 0; i < board.length; i++) {
    const p = board[i];
    if (!p) continue;
    const base = p.kind === "king" ? KING_VALUE : MAN_VALUE;
    const bonus = positionBonus(i, p.side, p.kind === "king");
    const value = base + bonus;
    score += p.side === perspective ? value : -value;
  }

  // Mobility nudge.
  const myMoves = legalMoves(board, perspective).length;
  const theirMoves = legalMoves(board, opposite(perspective)).length;
  score += (myMoves - theirMoves) * 4;

  return score;
}

function orderMoves(moves: Move[]): Move[] {
  return [...moves].sort((a, b) => {
    const cap = b.captures.length - a.captures.length;
    if (cap !== 0) return cap;
    return (b.promote ? 1 : 0) - (a.promote ? 1 : 0);
  });
}

function minimax(
  board: Board,
  side: Side,
  depth: number,
  alpha: number,
  beta: number,
  maximizing: boolean,
  rootSide: Side,
): number {
  const outcome = evaluateOutcome(board, side);
  if (outcome !== null || depth === 0) {
    return evaluate(board, rootSide);
  }

  const moves = orderMoves(legalMoves(board, side));
  if (moves.length === 0) {
    return evaluate(board, rootSide);
  }

  if (maximizing) {
    let best = -Infinity;
    for (const move of moves) {
      const next = applyMove(board, move);
      const value = minimax(
        next,
        opposite(side),
        depth - 1,
        alpha,
        beta,
        false,
        rootSide,
      );
      best = Math.max(best, value);
      alpha = Math.max(alpha, best);
      if (beta <= alpha) break;
    }
    return best;
  }

  let best = Infinity;
  for (const move of moves) {
    const next = applyMove(board, move);
    const value = minimax(
      next,
      opposite(side),
      depth - 1,
      alpha,
      beta,
      true,
      rootSide,
    );
    best = Math.min(best, value);
    beta = Math.min(beta, best);
    if (beta <= alpha) break;
  }
  return best;
}

export type AiStrength = "smart" | "sharp";

export function chooseAiMove(
  board: Board,
  side: Side,
  strength: AiStrength = "smart",
): Move | null {
  const moves = orderMoves(legalMoves(board, side));
  if (moves.length === 0) return null;
  if (moves.length === 1) return moves[0];

  const depth = strength === "sharp" ? 7 : 5;
  let bestMove = moves[0];
  let bestScore = -Infinity;

  for (const move of moves) {
    const next = applyMove(board, move);
    const score = minimax(
      next,
      opposite(side),
      depth - 1,
      -Infinity,
      Infinity,
      false,
      side,
    );
    // Tiny jitter so identical scores don't always pick the first move.
    const jitter = (Math.random() - 0.5) * 0.2;
    if (score + jitter > bestScore) {
      bestScore = score + jitter;
      bestMove = move;
    }
  }

  return bestMove;
}
