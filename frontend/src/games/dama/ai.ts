/**
 * Professional Dama AI: iterative-deepening negamax with alpha-beta,
 * transposition table, quiescence, and a strategic evaluation.
 * Moves are full legal turns from the shared engine (atomic multi-jumps).
 */

import {
  type Board,
  type Move,
  type Piece,
  type Side,
  BOARD_SIZE,
  SQUARE_COUNT,
  applyMove,
  colOf,
  legalMoves,
  opposite,
  rowOf,
} from "./engine";

export type AiDifficulty = "easy" | "medium" | "hard";
/** @deprecated Use AiDifficulty — kept for callers that still pass "smart"/"sharp". */
export type AiStrength = AiDifficulty | "smart" | "sharp";

export interface SearchOptions {
  difficulty?: AiDifficulty;
  /** Override max iterative depth (plies = complete turns). */
  maxDepth?: number;
  /** Soft wall-clock budget; returns best completed depth. */
  timeBudgetMs?: number;
  /** Checked frequently; abort returns best completed result. */
  shouldCancel?: () => boolean;
  /** Prior position hashes (side-to-move keyed) for repetition awareness. */
  historyHashes?: number[];
}

export interface SearchResult {
  move: Move | null;
  score: number;
  depth: number;
  nodes: number;
  aborted: boolean;
}

export const MAN_VALUE = 100;
export const KING_VALUE = 340;
const MATE_SCORE = 100_000;
const DRAW_SCORE = 0;

/** Half-moves before a human may offer a draw vs computer. */
export const DRAW_OFFER_MIN_PLY = 10;
/** Hide offer when computer is ahead by ~1 man-equivalent (human POV). */
const DRAW_HIDE_COMPUTER_LEAD = MAN_VALUE;
/** Hide offer when human is crushing (not competitive). */
const DRAW_HIDE_HUMAN_CRUSH = MAN_VALUE * 2;
/** Computer rejects draws when ahead by more than this (computer POV). */
const DRAW_ACCEPT_MAX_LEAD = 40;

const TT_SIZE = 1 << 18; // ~262k entries, power of two
const TT_MASK = TT_SIZE - 1;

const FLAG_EXACT = 0;
const FLAG_LOWER = 1;
const FLAG_UPPER = 2;

interface TtEntry {
  key: number;
  depth: number;
  score: number;
  flag: number;
  moveFrom: number;
  moveTo: number;
  moveCapLen: number;
}

const tt: TtEntry[] = new Array(TT_SIZE);
for (let i = 0; i < TT_SIZE; i++) {
  tt[i] = {
    key: 0,
    depth: -1,
    score: 0,
    flag: FLAG_EXACT,
    moveFrom: -1,
    moveTo: -1,
    moveCapLen: -1,
  };
}

/** Zobrist tables — stable across searches for TT usefulness. */
const ZOBRIST_PIECE: number[][] = [];
const ZOBRIST_SIDE = (Math.imul(0x9e3779b1, 0x85ebca6b) >>> 0) || 1;

(function initZobrist() {
  let seed = 0xc0ffee11;
  const next = () => {
    seed = (Math.imul(seed ^ (seed >>> 16), 0x7feb352d) >>> 0) || 1;
    seed = (Math.imul(seed ^ (seed >>> 15), 0x846ca68b) >>> 0) || 1;
    return (seed ^ (seed >>> 16)) >>> 0;
  };
  for (let sq = 0; sq < SQUARE_COUNT; sq++) {
    ZOBRIST_PIECE[sq] = [next(), next(), next(), next()]; // red-man, red-king, black-man, black-king
  }
})();

function pieceZIndex(p: Piece): number {
  const sideBit = p.side === "red" ? 0 : 2;
  const kindBit = p.kind === "king" ? 1 : 0;
  return sideBit + kindBit;
}

export function hashPosition(board: Board, side: Side): number {
  let h = side === "black" ? ZOBRIST_SIDE : 0;
  for (let i = 0; i < SQUARE_COUNT; i++) {
    const p = board[i];
    if (!p) continue;
    h ^= ZOBRIST_PIECE[i][pieceZIndex(p)];
  }
  return h >>> 0;
}

function countAllPieces(board: Board): number {
  let n = 0;
  for (const p of board) if (p) n += 1;
  return n;
}

function materialOfCapture(board: Board, move: Move): number {
  let v = 0;
  for (const c of move.captures) {
    const p = board[c];
    if (!p) continue;
    v += p.kind === "king" ? KING_VALUE : MAN_VALUE;
  }
  return v;
}

function movesEqualHint(a: Move, from: number, to: number, capLen: number): boolean {
  return a.from === from && a.to === to && a.captures.length === capLen;
}

function storeTt(
  key: number,
  depth: number,
  score: number,
  flag: number,
  best: Move | null,
): void {
  const slot = tt[key & TT_MASK];
  if (slot.key === key && slot.depth > depth) return;
  slot.key = key;
  slot.depth = depth;
  slot.score = score;
  slot.flag = flag;
  if (best) {
    slot.moveFrom = best.from;
    slot.moveTo = best.to;
    slot.moveCapLen = best.captures.length;
  } else {
    slot.moveFrom = -1;
    slot.moveTo = -1;
    slot.moveCapLen = -1;
  }
}

function probeTt(key: number): TtEntry | null {
  const slot = tt[key & TT_MASK];
  return slot.key === key ? slot : null;
}

/** Clear TT between independent games (optional; size is bounded). */
export function clearAiTranspositionTable(): void {
  for (const slot of tt) {
    slot.key = 0;
    slot.depth = -1;
    slot.moveFrom = -1;
  }
}

function difficultyPreset(d: AiDifficulty): {
  maxDepth: number;
  timeBudgetMs: number;
  useNoise: boolean;
  noiseChance: number;
} {
  switch (d) {
    case "easy":
      return { maxDepth: 2, timeBudgetMs: 180, useNoise: true, noiseChance: 0.35 };
    case "medium":
      return { maxDepth: 3, timeBudgetMs: 450, useNoise: true, noiseChance: 0.12 };
    case "hard":
    default:
      // Mobile-safe: ~2.5s soft budget; endgame bonuses push toward ~3s.
      return { maxDepth: 9, timeBudgetMs: 2500, useNoise: false, noiseChance: 0 };
  }
}

function normalizeDifficulty(strength: AiStrength = "hard"): AiDifficulty {
  if (strength === "smart") return "medium";
  if (strength === "sharp") return "hard";
  return strength;
}

function endgameDepthBonus(pieceCount: number, base: number): number {
  if (pieceCount <= 4) return Math.min(base + 5, 14);
  if (pieceCount <= 6) return Math.min(base + 4, 13);
  if (pieceCount <= 8) return Math.min(base + 3, 12);
  if (pieceCount <= 12) return Math.min(base + 2, 11);
  return base;
}

function endgameTimeBonus(pieceCount: number, base: number): number {
  if (pieceCount <= 6) return Math.min(base + 800, 3200);
  if (pieceCount <= 10) return Math.min(base + 450, 3000);
  return Math.min(base, 2800);
}

/** Alias kept for callers / UX helpers — same engine eval as search. */
export function evaluatePosition(board: Board, perspective: Side): number {
  return evaluateBoard(board, perspective);
}

function sideMaterial(board: Board, side: Side): {
  men: number;
  kings: number;
  total: number;
} {
  let men = 0;
  let kings = 0;
  for (const p of board) {
    if (!p || p.side !== side) continue;
    if (p.kind === "king") kings += 1;
    else men += 1;
  }
  return { men, kings, total: men + kings };
}

/**
 * Vs Computer: show Offer draw only when the game is still competitive.
 * Uses the same evaluateBoard scores as Hard AI (MAN_VALUE = 100).
 */
export function canHumanOfferDrawVsComputer(opts: {
  board: Board;
  humanSide: Side;
  plyCount: number;
  gameOver?: boolean;
  aiThinking?: boolean;
  animating?: boolean;
  offerPending?: boolean;
}): boolean {
  if (opts.gameOver || opts.aiThinking || opts.animating || opts.offerPending) {
    return false;
  }
  if (opts.plyCount < DRAW_OFFER_MIN_PLY) return false;

  const human = opts.humanSide;
  const computer = opposite(human);
  const score = evaluateBoard(opts.board, human);
  if (score <= -DRAW_HIDE_COMPUTER_LEAD) return false;
  if (score >= DRAW_HIDE_HUMAN_CRUSH) return false;

  const h = sideMaterial(opts.board, human);
  const c = sideMaterial(opts.board, computer);
  const computerMatLead =
    (c.men - h.men) * MAN_VALUE + (c.kings - h.kings) * KING_VALUE;
  // Decisive material: +king or +2 men for computer.
  if (computerMatLead >= KING_VALUE - 20) return false;
  if (computerMatLead >= MAN_VALUE * 2 - 20) return false;

  const total = h.total + c.total;
  // Late runaway: few pieces and computer material lead.
  if (total <= 6 && computerMatLead >= MAN_VALUE - 20) return false;
  if (total <= 4 && computerMatLead > 0) return false;

  return true;
}

/** Computer accepts only when equal or slightly worse; rejects when ahead. */
export function shouldComputerAcceptDraw(
  board: Board,
  computerSide: Side,
): boolean {
  const score = evaluateBoard(board, computerSide);
  return score <= DRAW_ACCEPT_MAX_LEAD;
}

/** Strategic evaluation from `perspective`'s point of view. */
export function evaluateBoard(board: Board, perspective: Side): number {
  const opp = opposite(perspective);
  let myMen = 0;
  let myKings = 0;
  let theirMen = 0;
  let theirKings = 0;
  let score = 0;

  const mySquares: number[] = [];
  const theirSquares: number[] = [];

  for (let i = 0; i < SQUARE_COUNT; i++) {
    const p = board[i];
    if (!p) continue;
    const r = rowOf(i);
    const c = colOf(i);
    const centerDist = Math.abs(c - 3.5) + Math.abs(r - 3.5);
    const center = 7 - centerDist;
    const isMine = p.side === perspective;

    if (p.kind === "king") {
      // King safety: rim is safer vs flying kings; center is more active.
      const rim =
        (r === 0 || r === 7 ? 1 : 0) + (c === 0 || c === 7 ? 1 : 0);
      if (isMine) {
        myKings += 1;
        mySquares.push(i);
        score += KING_VALUE + center * 3;
        // Midgame: slight rim cost (passive). Endgame handled below.
        if (rim > 0) score -= 3 * rim;
      } else {
        theirKings += 1;
        theirSquares.push(i);
        score -= KING_VALUE + center * 3;
        if (rim > 0) score += 3 * rim;
      }
    } else {
      const advance = isMine
        ? perspective === "red"
          ? 7 - r
          : r
        : perspective === "red"
          ? r
          : 7 - r;
      const promoNear = advance >= 5 ? (advance - 4) * 16 : advance * 3;
      const backRank =
        (perspective === "red" && isMine && r === 7) ||
        (perspective === "black" && isMine && r === 0) ||
        (perspective === "red" && !isMine && r === 0) ||
        (perspective === "black" && !isMine && r === 7)
          ? 8
          : 0;

      // Runaway man: deep advance with little opposing density ahead.
      let runaway = 0;
      if (advance >= 4) {
        const dir = perspective === "red" ? (isMine ? -1 : 1) : isMine ? 1 : -1;
        let blockers = 0;
        for (let rr = r + dir; rr >= 0 && rr < BOARD_SIZE; rr += dir) {
          for (const dc of [-1, 0, 1]) {
            const cc = c + dc;
            if (cc < 0 || cc >= BOARD_SIZE) continue;
            const q = board[rr * BOARD_SIZE + cc];
            if (q && q.side !== p.side) blockers += 1;
          }
        }
        if (blockers === 0) runaway = 10 + (advance - 3) * 8;
        else if (blockers === 1 && advance >= 5) runaway = 6;
      }

      if (isMine) {
        myMen += 1;
        mySquares.push(i);
        score += MAN_VALUE + promoNear + center + backRank + runaway;
      } else {
        theirMen += 1;
        theirSquares.push(i);
        score -= MAN_VALUE + promoNear + center + backRank + runaway;
      }
    }
  }

  if (myMen + myKings === 0) return -MATE_SCORE;
  if (theirMen + theirKings === 0) return MATE_SCORE;

  // Connectivity: adjacent friendly pieces (diagonal neighbors).
  score += connectivityBonus(mySquares) - connectivityBonus(theirSquares);

  // Mobility (legal move counts).
  const myMoves = legalMoves(board, perspective);
  const theirMoves = legalMoves(board, opp);
  if (myMoves.length === 0) return -MATE_SCORE;
  if (theirMoves.length === 0) return MATE_SCORE;
  score += (myMoves.length - theirMoves.length) * 6;

  // Capture opportunity / vulnerability from legal turn sets.
  const myCap = myMoves[0]?.captures.length ?? 0;
  const theirCap = theirMoves[0]?.captures.length ?? 0;
  if (myCap > 0) score += 12 + myCap * 18 + materialOfCapture(board, myMoves[0]) * 0.15;
  if (theirCap > 0) score -= 14 + theirCap * 20 + materialOfCapture(board, theirMoves[0]) * 0.18;

  // Hanging: pieces that appear in opponent's forced capture set.
  for (const m of theirMoves) {
    for (const c of m.captures) {
      const p = board[c];
      if (!p || p.side !== perspective) continue;
      score -= p.kind === "king" ? 60 : 30;
    }
  }
  for (const m of myMoves) {
    for (const c of m.captures) {
      const p = board[c];
      if (!p || p.side !== opp) continue;
      score += p.kind === "king" ? 42 : 20;
    }
  }

  // Endgame: chase with kings, opposition / tempo, cornering.
  const total = myMen + myKings + theirMen + theirKings;
  if (total <= 8) {
    score += kingActivity(board, perspective) - kingActivity(board, opp);
    if (myKings >= 1 && theirKings >= 1 && mySquares.length && theirSquares.length) {
      // Opposition: closer kings when ahead presses; distance when behind stalls.
      let minDist = 99;
      for (const a of mySquares) {
        const pa = board[a];
        if (!pa || pa.kind !== "king") continue;
        for (const b of theirSquares) {
          const pb = board[b];
          if (!pb || pb.kind !== "king") continue;
          const d = Math.abs(rowOf(a) - rowOf(b)) + Math.abs(colOf(a) - colOf(b));
          if (d < minDist) minDist = d;
        }
      }
      if (minDist < 99) {
        const matDiffEarly =
          (myMen - theirMen) * MAN_VALUE + (myKings - theirKings) * KING_VALUE;
        if (matDiffEarly > 40) score += Math.max(0, 14 - minDist);
        else if (matDiffEarly < -40) score -= Math.max(0, 10 - minDist);
      }
    }
    if (theirMen + theirKings === 1 && myKings >= 1) {
      score += 40; // cornering pressure
      const lone = theirSquares[0];
      if (lone !== undefined) {
        const lr = rowOf(lone);
        const lc = colOf(lone);
        const edge = (lr === 0 || lr === 7 ? 14 : 0) + (lc === 0 || lc === 7 ? 14 : 0);
        score += edge;
      }
    }
  }

  // Tempo / conversion when ahead — avoid sitting on a lead.
  const matDiff =
    (myMen - theirMen) * MAN_VALUE + (myKings - theirKings) * KING_VALUE;
  if (matDiff > 80 && total <= 12) score += 12;
  if (matDiff < -80 && total <= 12) score -= 12;
  if (matDiff > 150) score += 10;
  if (matDiff < -150) score -= 10;

  return score | 0;
}

function connectivityBonus(squares: number[]): number {
  let bonus = 0;
  const set = new Set(squares);
  for (const s of squares) {
    const r = rowOf(s);
    const c = colOf(s);
    for (const [dr, dc] of [
      [-1, -1],
      [-1, 1],
      [1, -1],
      [1, 1],
    ] as const) {
      const nr = r + dr;
      const nc = c + dc;
      if (nr < 0 || nr >= BOARD_SIZE || nc < 0 || nc >= BOARD_SIZE) continue;
      if (set.has(nr * BOARD_SIZE + nc)) bonus += 3;
    }
  }
  return bonus;
}

function kingActivity(board: Board, side: Side): number {
  let act = 0;
  for (let i = 0; i < SQUARE_COUNT; i++) {
    const p = board[i];
    if (!p || p.side !== side || p.kind !== "king") continue;
    const r = rowOf(i);
    const c = colOf(i);
    act += 10 - (Math.abs(r - 3.5) + Math.abs(c - 3.5));
  }
  return act;
}

function orderMoves(
  board: Board,
  moves: Move[],
  ttMove: TtEntry | null,
  killers: Move[],
  history: Int32Array,
): Move[] {
  const scored = moves.map((m) => {
    let s = 0;
    if (
      ttMove &&
      ttMove.moveFrom >= 0 &&
      movesEqualHint(m, ttMove.moveFrom, ttMove.moveTo, ttMove.moveCapLen)
    ) {
      s += 50_000;
    }
    if (m.captures.length > 0) {
      s += 10_000 + m.captures.length * 800 + materialOfCapture(board, m);
    }
    if (m.promote) s += 900;
    for (const k of killers) {
      if (k && k.from === m.from && k.to === m.to && k.captures.length === m.captures.length) {
        s += 700;
        break;
      }
    }
    s += history[(m.from << 6) | m.to] ?? 0;
    // Prefer advancing men slightly.
    const fromR = rowOf(m.from);
    const toR = rowOf(m.to);
    s += Math.abs(toR - fromR);
    return { m, s };
  });
  scored.sort((a, b) => b.s - a.s);
  return scored.map((x) => x.m);
}

interface SearchCtx {
  nodes: number;
  deadline: number;
  shouldCancel?: () => boolean;
  aborted: boolean;
  killers: Move[][];
  history: Int32Array;
  repHashes: Set<number>;
}

function timeUp(ctx: SearchCtx): boolean {
  if (ctx.aborted) return true;
  if (ctx.shouldCancel?.()) {
    ctx.aborted = true;
    return true;
  }
  if (ctx.nodes % 64 === 0 && performance.now() >= ctx.deadline) {
    ctx.aborted = true;
    return true;
  }
  return false;
}

function mateScore(win: boolean, ply: number): number {
  return win ? MATE_SCORE - ply : -MATE_SCORE + ply;
}

function quiescence(
  board: Board,
  side: Side,
  alpha: number,
  beta: number,
  ply: number,
  qDepth: number,
  ctx: SearchCtx,
): number {
  ctx.nodes += 1;
  // Stand-pat from side-to-move perspective (negamax).
  if (timeUp(ctx)) return evaluateBoard(board, side);

  const stand = evaluateBoard(board, side);
  if (qDepth <= 0) return stand;

  if (stand >= beta) return stand;
  let a = alpha;
  if (stand > a) a = stand;

  const moves = legalMoves(board, side);
  if (moves.length === 0) return mateScore(false, ply);

  // Only extend forced captures / promotions.
  const noisy = moves.filter((m) => m.captures.length > 0 || m.promote);
  if (noisy.length === 0) return stand;

  const ordered = orderMoves(board, noisy, null, ctx.killers[ply] ?? [], ctx.history);
  for (const move of ordered) {
    if (timeUp(ctx)) break;
    const next = applyMove(board, move);
    const score = -quiescence(
      next,
      opposite(side),
      -beta,
      -a,
      ply + 1,
      qDepth - 1,
      ctx,
    );
    if (score >= beta) return score;
    if (score > a) a = score;
  }
  return a;
}

function negamax(
  board: Board,
  side: Side,
  depth: number,
  alpha: number,
  beta: number,
  ply: number,
  ctx: SearchCtx,
): number {
  ctx.nodes += 1;
  if (timeUp(ctx)) return evaluateBoard(board, side);

  const key = hashPosition(board, side);
  if (ply > 0 && ctx.repHashes.has(key)) {
    // Avoid false draws when clearly ahead; prefer a real draw when losing.
    const stand = evaluateBoard(board, side);
    if (stand > 80) return -18;
    if (stand < -80) return 12;
    return DRAW_SCORE;
  }

  const ttHit = probeTt(key);
  if (ttHit && ttHit.depth >= depth) {
    if (ttHit.flag === FLAG_EXACT) return ttHit.score;
    if (ttHit.flag === FLAG_LOWER && ttHit.score >= beta) return ttHit.score;
    if (ttHit.flag === FLAG_UPPER && ttHit.score <= alpha) return ttHit.score;
  }

  const moves = legalMoves(board, side);
  if (moves.length === 0) return mateScore(false, ply);

  // Quiescence at leaves — avoid horizon capture blunders.
  if (depth <= 0) {
    const hasCapture = moves.some((m) => m.captures.length > 0);
    if (hasCapture) {
      return quiescence(board, side, alpha, beta, ply, 6, ctx);
    }
    return evaluateBoard(board, side);
  }

  const searchDepth = depth;

  let a = alpha;
  let b = beta;
  if (ttHit) {
    if (ttHit.flag === FLAG_LOWER) a = Math.max(a, ttHit.score);
    if (ttHit.flag === FLAG_UPPER) b = Math.min(b, ttHit.score);
    if (a >= b) return ttHit.score;
  }

  if (!ctx.killers[ply]) ctx.killers[ply] = [];
  const ordered = orderMoves(board, moves, ttHit, ctx.killers[ply], ctx.history);

  let bestScore = -Infinity;
  let bestMove: Move | null = null;
  let flag = FLAG_UPPER;

  ctx.repHashes.add(key);
  for (let i = 0; i < ordered.length; i++) {
    if (timeUp(ctx)) break;
    const move = ordered[i];
    const next = applyMove(board, move);

    let score: number;
    // Late move reduction for quiet late moves at deeper plies.
    const quiet =
      move.captures.length === 0 && !move.promote && i >= 3 && searchDepth >= 3 && ply >= 2;
    if (quiet) {
      score = -negamax(
        next,
        opposite(side),
        searchDepth - 2,
        -a - 1,
        -a,
        ply + 1,
        ctx,
      );
      if (score > a) {
        score = -negamax(
          next,
          opposite(side),
          searchDepth - 1,
          -b,
          -a,
          ply + 1,
          ctx,
        );
      }
    } else {
      score = -negamax(
        next,
        opposite(side),
        searchDepth - 1,
        -b,
        -a,
        ply + 1,
        ctx,
      );
    }

    if (score > bestScore) {
      bestScore = score;
      bestMove = move;
    }
    if (score > a) {
      a = score;
      flag = FLAG_EXACT;
    }
    if (a >= b) {
      flag = FLAG_LOWER;
      if (move.captures.length === 0) {
        const killers = ctx.killers[ply];
        if (!killers.some((k) => k.from === move.from && k.to === move.to)) {
          killers.unshift(move);
          if (killers.length > 2) killers.length = 2;
        }
        const hIdx = (move.from << 6) | move.to;
        ctx.history[hIdx] = Math.min(
          20_000,
          (ctx.history[hIdx] ?? 0) + searchDepth * searchDepth,
        );
      }
      break;
    }
  }
  ctx.repHashes.delete(key);

  if (!ctx.aborted && bestMove) {
    storeTt(key, depth, bestScore, flag, bestMove);
  }
  return bestScore;
}

export function searchBestMove(
  board: Board,
  side: Side,
  options: SearchOptions = {},
): SearchResult {
  const difficulty = options.difficulty ?? "hard";
  const preset = difficultyPreset(difficulty);
  const pieceCount = countAllPieces(board);
  const maxDepth =
    options.maxDepth ??
    (difficulty === "hard" ? endgameDepthBonus(pieceCount, preset.maxDepth) : preset.maxDepth);
  const timeBudgetMs =
    options.timeBudgetMs ??
    (difficulty === "hard"
      ? endgameTimeBonus(pieceCount, preset.timeBudgetMs)
      : preset.timeBudgetMs);

  const rootMoves = legalMoves(board, side);
  if (rootMoves.length === 0) {
    return { move: null, score: mateScore(false, 0), depth: 0, nodes: 0, aborted: false };
  }
  if (rootMoves.length === 1) {
    return {
      move: rootMoves[0],
      score: 0,
      depth: 0,
      nodes: 1,
      aborted: false,
    };
  }

  // Snapshot guard — search never mutates caller board (applyMove clones).
  const deadline = performance.now() + timeBudgetMs;
  const ctx: SearchCtx = {
    nodes: 0,
    deadline,
    shouldCancel: options.shouldCancel,
    aborted: false,
    killers: [],
    history: new Int32Array(SQUARE_COUNT * SQUARE_COUNT),
    repHashes: new Set(options.historyHashes ?? []),
  };

  const rootKey = hashPosition(board, side);
  ctx.repHashes.add(rootKey);

  let bestMove = rootMoves[0];
  let bestScore = -Infinity;
  let completedDepth = 0;

  // Root move scores for optional easy/medium noise.
  let lastRootScores: { move: Move; score: number }[] = [];

  for (let depth = 1; depth <= maxDepth; depth++) {
    if (timeUp(ctx) && completedDepth > 0) break;

    let a = -Infinity;
    const b = Infinity;
    const ttHit = probeTt(rootKey);
    const ordered = orderMoves(board, rootMoves, ttHit, ctx.killers[0] ?? [], ctx.history);
    const depthScores: { move: Move; score: number }[] = [];
    let depthBest: Move | null = null;
    let depthBestScore = -Infinity;
    let depthAborted = false;

    for (const move of ordered) {
      if (timeUp(ctx)) {
        depthAborted = true;
        break;
      }
      const next = applyMove(board, move);
      const score = -negamax(next, opposite(side), depth - 1, -b, -a, 1, ctx);
      depthScores.push({ move, score });
      if (score > depthBestScore) {
        depthBestScore = score;
        depthBest = move;
      }
      if (score > a) a = score;
    }

    if (depthAborted && completedDepth > 0) {
      // Keep previous fully completed iteration.
      break;
    }
    if (!depthBest) break;

    bestMove = depthBest;
    bestScore = depthBestScore;
    completedDepth = depth;
    lastRootScores = depthScores;
    storeTt(rootKey, depth, bestScore, FLAG_EXACT, bestMove);

    // Mate found — no need to go deeper.
    if (Math.abs(bestScore) >= MATE_SCORE - 200) break;

    // Fast forced replies: if one capture is clearly winning, stop early.
    if (
      depth >= 3 &&
      bestMove.captures.length > 0 &&
      bestScore > 400 &&
      performance.now() + 80 >= deadline
    ) {
      break;
    }
  }

  // Deliberate mistakes only on easy/medium.
  if (preset.useNoise && lastRootScores.length > 1 && Math.random() < preset.noiseChance) {
    lastRootScores.sort((x, y) => y.score - x.score);
    const pick = lastRootScores[Math.min(1 + Math.floor(Math.random() * 2), lastRootScores.length - 1)];
    bestMove = pick.move;
    bestScore = pick.score;
  }

  return {
    move: bestMove,
    score: bestScore,
    depth: completedDepth,
    nodes: ctx.nodes,
    aborted: ctx.aborted,
  };
}

/** Synchronous chooser used by tests and as a main-thread fallback. */
export function chooseAiMove(
  board: Board,
  side: Side,
  strength: AiStrength = "hard",
  options: Omit<SearchOptions, "difficulty"> = {},
): Move | null {
  const difficulty = normalizeDifficulty(strength);
  return searchBestMove(board, side, { ...options, difficulty }).move;
}

export function chooseAiMoveDetailed(
  board: Board,
  side: Side,
  strength: AiStrength = "hard",
  options: Omit<SearchOptions, "difficulty"> = {},
): SearchResult {
  const difficulty = normalizeDifficulty(strength);
  return searchBestMove(board, side, { ...options, difficulty });
}
