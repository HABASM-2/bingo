/**
 * Deterministic Dama AI tests — run with:
 *   npx --yes tsx src/games/dama/ai.test.ts
 */

import assert from "node:assert/strict";
import {
  type Board,
  type Move,
  type Piece,
  applyMove,
  createInitialBoard,
  idx,
  legalMoves,
} from "./engine";
import {
  chooseAiMove,
  chooseAiMoveDetailed,
  clearAiTranspositionTable,
  canHumanOfferDrawVsComputer,
  DRAW_OFFER_MIN_PLY,
  evaluateBoard,
  hashPosition,
  searchBestMove,
  shouldComputerAcceptDraw,
} from "./ai";
import { DAMA_MIN_STAKE, isValidDamaStake } from "./constants";

function emptyBoard(): Board {
  return Array(64).fill(null);
}

function place(board: Board, row: number, col: number, piece: Piece): void {
  board[idx(row, col)] = piece;
}

function cloneBoard(board: Board): Board {
  return board.map((p) => (p ? { ...p } : null));
}

function boardEqual(a: Board, b: Board): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function moveKey(m: Move): string {
  return `${m.from}->${m.to}:[${m.captures.join(",")}]`;
}

function rowOf(i: number): number {
  return Math.floor(i / 8);
}

let passed = 0;
let failed = 0;

function test(name: string, fn: () => void): void {
  clearAiTranspositionTable();
  try {
    fn();
    passed += 1;
    console.log(`  ✓ ${name}`);
  } catch (err) {
    failed += 1;
    console.error(`  ✗ ${name}`);
    console.error(err);
  }
}

console.log("Dama AI tests\n");

test("AI always chooses a forced capture", () => {
  const board = emptyBoard();
  place(board, 2, 1, { side: "black", kind: "man" });
  place(board, 3, 2, { side: "red", kind: "man" });
  place(board, 1, 0, { side: "black", kind: "man" });

  const legal = legalMoves(board, "black");
  assert.ok(legal.every((m) => m.captures.length > 0), "captures mandatory");
  const move = chooseAiMove(board, "black", "hard", { maxDepth: 3, timeBudgetMs: 400 });
  assert.ok(move);
  assert.ok(move!.captures.length > 0);
});

test("AI chooses maximum capture sequence when required", () => {
  const board = emptyBoard();
  place(board, 1, 2, { side: "black", kind: "man" });
  place(board, 2, 3, { side: "red", kind: "man" });
  place(board, 4, 5, { side: "red", kind: "man" });
  place(board, 1, 6, { side: "black", kind: "man" });
  place(board, 2, 5, { side: "red", kind: "man" });

  const legal = legalMoves(board, "black");
  const maxLen = Math.max(...legal.map((m) => m.captures.length));
  assert.equal(maxLen, 2);
  assert.ok(legal.every((m) => m.captures.length === 2));

  const move = chooseAiMove(board, "black", "hard", { maxDepth: 2, timeBudgetMs: 300 });
  assert.ok(move);
  assert.equal(move!.captures.length, 2);
});

test("AI finds a multi-ply tactical capture win", () => {
  const board = emptyBoard();
  place(board, 4, 3, { side: "black", kind: "king" });
  place(board, 2, 1, { side: "red", kind: "man" });
  place(board, 2, 5, { side: "red", kind: "man" });
  place(board, 0, 1, { side: "red", kind: "man" });

  const result = searchBestMove(board, "black", {
    difficulty: "hard",
    maxDepth: 5,
    timeBudgetMs: 1200,
  });
  assert.ok(result.move);
  const legal = legalMoves(board, "black");
  if (legal.some((m) => m.captures.length > 0)) {
    assert.ok(result.move!.captures.length > 0);
  }
  assert.ok(
    result.score > 50 || result.move!.captures.length > 0,
    `expected strong tactical result, score=${result.score}`,
  );
});

test("AI avoids an obvious hanging-piece trap", () => {
  const board = emptyBoard();
  place(board, 3, 2, { side: "black", kind: "man" });
  place(board, 5, 4, { side: "red", kind: "man" });
  place(board, 4, 5, { side: "red", kind: "king" });
  place(board, 1, 0, { side: "black", kind: "man" });

  const moves = legalMoves(board, "black");
  assert.ok(moves.every((m) => m.captures.length === 0));
  assert.ok(moves.some((m) => m.to === idx(4, 3)));
  assert.ok(moves.some((m) => m.to === idx(4, 1)));

  const pick = chooseAiMove(board, "black", "hard", { maxDepth: 5, timeBudgetMs: 1000 });
  assert.ok(pick);
  assert.notEqual(
    pick!.to,
    idx(4, 3),
    `AI walked into hang trap: ${moveKey(pick!)}`,
  );
});

test("AI promotes when strategically correct", () => {
  const board = emptyBoard();
  place(board, 6, 3, { side: "black", kind: "man" });
  place(board, 0, 1, { side: "red", kind: "man" });
  place(board, 1, 6, { side: "black", kind: "man" });

  const moves = legalMoves(board, "black");
  assert.ok(moves.some((m) => m.promote || rowOf(m.to) === 7));

  const pick = chooseAiMove(board, "black", "hard", { maxDepth: 4, timeBudgetMs: 600 });
  assert.ok(pick);
  assert.ok(
    pick!.promote || rowOf(pick!.to) === 7,
    `expected promotion, got ${moveKey(pick!)}`,
  );
});

test("AI takes immediate forced win", () => {
  const winBoard = emptyBoard();
  place(winBoard, 3, 2, { side: "black", kind: "king" });
  place(winBoard, 4, 3, { side: "red", kind: "man" });

  const winMove = chooseAiMove(winBoard, "black", "hard", {
    maxDepth: 4,
    timeBudgetMs: 500,
  });
  assert.ok(winMove);
  assert.ok(winMove!.captures.length >= 1);
  const after = applyMove(winBoard, winMove!);
  assert.ok(!after.some((p) => p?.side === "red"));
});

test("AI delays forced loss (search completes with negative score)", () => {
  const loseBoard = emptyBoard();
  place(loseBoard, 0, 1, { side: "black", kind: "man" });
  place(loseBoard, 2, 1, { side: "red", kind: "king" });
  place(loseBoard, 2, 3, { side: "red", kind: "king" });
  place(loseBoard, 1, 4, { side: "red", kind: "king" });

  const loseResult = searchBestMove(loseBoard, "black", {
    difficulty: "hard",
    maxDepth: 5,
    timeBudgetMs: 800,
  });
  assert.ok(loseResult.move);
  assert.ok(loseResult.depth >= 1);
  assert.ok(loseResult.score < 0, `expected losing score, got ${loseResult.score}`);
});

test("Search respects cancellation budget", () => {
  const board = emptyBoard();
  place(board, 2, 1, { side: "black", kind: "man" });
  place(board, 2, 3, { side: "black", kind: "man" });
  place(board, 2, 5, { side: "black", kind: "man" });
  place(board, 3, 0, { side: "black", kind: "king" });
  place(board, 5, 2, { side: "red", kind: "man" });
  place(board, 5, 4, { side: "red", kind: "man" });
  place(board, 5, 6, { side: "red", kind: "man" });
  place(board, 6, 1, { side: "red", kind: "king" });

  let cancelAfter = false;
  const start = performance.now();
  const result = searchBestMove(board, "black", {
    difficulty: "hard",
    maxDepth: 10,
    timeBudgetMs: 50,
    shouldCancel: () => {
      if (performance.now() - start > 30) cancelAfter = true;
      return cancelAfter;
    },
  });
  const elapsed = performance.now() - start;
  assert.ok(result.move, "should still return a move");
  assert.ok(elapsed < 500, `cancelled search took too long: ${elapsed}ms`);
});

test("Input board is not mutated", () => {
  const board = emptyBoard();
  place(board, 2, 1, { side: "black", kind: "man" });
  place(board, 3, 2, { side: "red", kind: "man" });
  place(board, 5, 4, { side: "red", kind: "man" });
  place(board, 5, 6, { side: "black", kind: "king" });
  const snapshot = cloneBoard(board);

  chooseAiMove(board, "black", "hard", { maxDepth: 4, timeBudgetMs: 400 });
  assert.ok(boardEqual(board, snapshot), "board mutated during search");
});

test("Hash is stable and side-sensitive", () => {
  const board = emptyBoard();
  place(board, 3, 2, { side: "black", kind: "man" });
  const h1 = hashPosition(board, "black");
  const h2 = hashPosition(board, "black");
  const h3 = hashPosition(board, "red");
  assert.equal(h1, h2);
  assert.notEqual(h1, h3);
});

test("Hard AI is deterministic (no noise)", () => {
  const board = emptyBoard();
  place(board, 2, 1, { side: "black", kind: "man" });
  place(board, 2, 3, { side: "black", kind: "man" });
  place(board, 5, 2, { side: "red", kind: "man" });
  place(board, 5, 4, { side: "red", kind: "man" });
  place(board, 4, 5, { side: "red", kind: "king" });

  clearAiTranspositionTable();
  const a = chooseAiMoveDetailed(board, "black", "hard", {
    maxDepth: 4,
    timeBudgetMs: 400,
  });
  clearAiTranspositionTable();
  const b = chooseAiMoveDetailed(board, "black", "hard", {
    maxDepth: 4,
    timeBudgetMs: 400,
  });
  assert.ok(a.move && b.move);
  assert.equal(moveKey(a.move!), moveKey(b.move!));
});

test("evaluateBoard prefers material and kings", () => {
  const weak = emptyBoard();
  place(weak, 3, 2, { side: "black", kind: "man" });
  place(weak, 5, 4, { side: "red", kind: "man" });
  place(weak, 5, 6, { side: "red", kind: "man" });

  const strong = emptyBoard();
  place(strong, 3, 2, { side: "black", kind: "king" });
  place(strong, 4, 5, { side: "black", kind: "man" });
  place(strong, 5, 4, { side: "red", kind: "man" });

  assert.ok(evaluateBoard(strong, "black") > evaluateBoard(weak, "black"));
});

test("Even position → draw offer available after min plies", () => {
  const board = createInitialBoard();
  assert.equal(
    canHumanOfferDrawVsComputer({
      board,
      humanSide: "red",
      plyCount: DRAW_OFFER_MIN_PLY - 1,
    }),
    false,
    "blocked before min ply",
  );
  assert.equal(
    canHumanOfferDrawVsComputer({
      board,
      humanSide: "red",
      plyCount: DRAW_OFFER_MIN_PLY,
    }),
    true,
    "even opening after min ply",
  );
});

test("Computer material winning → draw offer hidden", () => {
  const board = emptyBoard();
  // Computer (black) has king + 2 men; human (red) has one man.
  place(board, 2, 1, { side: "black", kind: "king" });
  place(board, 3, 2, { side: "black", kind: "man" });
  place(board, 4, 5, { side: "black", kind: "man" });
  place(board, 5, 2, { side: "red", kind: "man" });

  assert.equal(
    canHumanOfferDrawVsComputer({
      board,
      humanSide: "red",
      plyCount: 20,
    }),
    false,
  );
  assert.equal(shouldComputerAcceptDraw(board, "black"), false);
});

test("Game over / AI thinking / animating → draw offer hidden", () => {
  const board = createInitialBoard();
  assert.equal(
    canHumanOfferDrawVsComputer({
      board,
      humanSide: "red",
      plyCount: 20,
      gameOver: true,
    }),
    false,
  );
  assert.equal(
    canHumanOfferDrawVsComputer({
      board,
      humanSide: "red",
      plyCount: 20,
      aiThinking: true,
    }),
    false,
  );
  assert.equal(
    canHumanOfferDrawVsComputer({
      board,
      humanSide: "red",
      plyCount: 20,
      animating: true,
    }),
    false,
  );
  assert.equal(
    canHumanOfferDrawVsComputer({
      board,
      humanSide: "red",
      plyCount: 20,
      offerPending: true,
    }),
    false,
  );
});

test("Computer accepts draw when equal / slightly worse", () => {
  const even = createInitialBoard();
  assert.equal(shouldComputerAcceptDraw(even, "black"), true);

  const losing = emptyBoard();
  place(losing, 2, 1, { side: "black", kind: "man" });
  place(losing, 5, 2, { side: "red", kind: "king" });
  place(losing, 5, 4, { side: "red", kind: "king" });
  assert.equal(shouldComputerAcceptDraw(losing, "black"), true);
});

test("Min stake 5 rejected below / accepted at 5", () => {
  assert.equal(DAMA_MIN_STAKE, 5);
  assert.equal(isValidDamaStake("1"), false);
  assert.equal(isValidDamaStake("4.99"), false);
  assert.equal(isValidDamaStake("5"), true);
  assert.equal(isValidDamaStake("10"), true);
  assert.equal(isValidDamaStake("0"), false);
  assert.equal(isValidDamaStake(""), false);
});

test("AI finds forced multi-ply capture opportunity", () => {
  const board = emptyBoard();
  place(board, 4, 1, { side: "black", kind: "king" });
  place(board, 3, 2, { side: "red", kind: "man" });
  place(board, 1, 4, { side: "red", kind: "man" });

  const result = searchBestMove(board, "black", {
    difficulty: "hard",
    maxDepth: 6,
    timeBudgetMs: 1500,
  });
  assert.ok(result.move);
  assert.ok(result.depth >= 3 || result.move!.captures.length > 0);
  assert.ok(
    result.score > 80 || result.move!.captures.length > 0,
    `weak tactical result score=${result.score} depth=${result.depth}`,
  );
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
