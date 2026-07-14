/**
 * Deterministic 5x5 cartela generation, mirroring the backend
 * (`backend/app/bingo/cards.py`) byte-for-byte so the client can render
 * lobby previews and auto-dab live cards without a round-trip. The server
 * remains authoritative for win validation.
 *
 * Column ranges (Bingo 75): B 1-15, I 16-30, N 31-45 (FREE center),
 * G 46-60, O 61-75.
 */

export type CartelaCell = number | null;
export type CartelaGrid = CartelaCell[][];

export const BINGO_COLUMN_LETTERS = ["B", "I", "N", "G", "O"] as const;

const CARD_SIZE = 5;
const FREE_ROW = 2;
const FREE_COL = 2;

const COLUMN_RANGES: [number, number][] = [
  [1, 15],
  [16, 30],
  [31, 45],
  [46, 60],
  [61, 75],
];

/** Tiny LCG (Numerical Recipes constants), identical to the Python side. */
function makeRng(seed: number): () => number {
  let state = Math.imul(seed, 2654435761) >>> 0;

  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function shuffledPool(low: number, high: number, rnd: () => number): number[] {
  const pool: number[] = [];
  for (let n = low; n <= high; n++) pool.push(n);

  for (let i = 0; i < pool.length - 1; i++) {
    const j = i + Math.floor(rnd() * (pool.length - i));
    const tmp = pool[i];
    pool[i] = pool[j];
    pool[j] = tmp;
  }

  return pool;
}

export function cartelaForBoard(boardId: number): CartelaGrid {
  const rnd = makeRng(boardId);
  const grid: CartelaGrid = Array.from({ length: CARD_SIZE }, () =>
    Array.from({ length: CARD_SIZE }, () => null as CartelaCell),
  );

  for (let col = 0; col < CARD_SIZE; col++) {
    const [low, high] = COLUMN_RANGES[col];
    const pool = shuffledPool(low, high, rnd);
    let idx = 0;

    for (let row = 0; row < CARD_SIZE; row++) {
      if (row === FREE_ROW && col === FREE_COL) {
        grid[row][col] = null;
        continue;
      }

      grid[row][col] = pool[idx];
      idx += 1;
    }
  }

  return grid;
}

export function letterForNumber(n: number): string {
  if (n <= 15) return "B";
  if (n <= 30) return "I";
  if (n <= 45) return "N";
  if (n <= 60) return "G";
  return "O";
}

/** Called-number label like "N-34" / "B-3". */
export function callLabel(n: number): string {
  return `${letterForNumber(n)}-${n}`;
}

/**
 * Cells (row, col) that make up a winning pattern, mirroring the backend
 * pattern names (row_N / col_N / diagonal_top_left / diagonal_top_right).
 * Used by the winner dialog to paint the winning line solid green.
 */
export function patternCells(pattern: string | null | undefined): [number, number][] {
  if (!pattern) return [];

  if (pattern.startsWith("row_")) {
    const r = Number(pattern.slice(4));
    return Array.from({ length: CARD_SIZE }, (_, c) => [r, c] as [number, number]);
  }

  if (pattern.startsWith("col_")) {
    const c = Number(pattern.slice(4));
    return Array.from({ length: CARD_SIZE }, (_, r) => [r, c] as [number, number]);
  }

  if (pattern === "diagonal_top_left") {
    return Array.from({ length: CARD_SIZE }, (_, i) => [i, i] as [number, number]);
  }

  if (pattern === "diagonal_top_right") {
    return Array.from({ length: CARD_SIZE }, (_, i) => [i, CARD_SIZE - 1 - i] as [number, number]);
  }

  return [];
}

/** The 15 numbers belonging to a B-I-N-G-O column index (0..4). */
export function columnNumbers(colIndex: number): number[] {
  const [low, high] = COLUMN_RANGES[colIndex];
  const out: number[] = [];
  for (let n = low; n <= high; n++) out.push(n);
  return out;
}
