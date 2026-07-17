import { type Board, type Side } from "./engine";
import {
  type AiDifficulty,
  type AiStrength,
  type SearchResult,
  chooseAiMoveDetailed,
  hashPosition,
} from "./ai";
import type { AiWorkerInbound, AiWorkerResult } from "./aiMessages";

function normalizeDifficulty(strength: AiStrength = "hard"): AiDifficulty {
  if (strength === "smart") return "medium";
  if (strength === "sharp") return "hard";
  return strength;
}

let worker: Worker | null = null;
let nextId = 1;
let workerFailed = false;

type Pending = {
  resolve: (r: SearchResult) => void;
  reject: (e: unknown) => void;
};

const pending = new Map<number, Pending>();

function ensureWorker(): Worker | null {
  if (workerFailed) return null;
  if (worker) return worker;
  try {
    worker = new Worker(new URL("./ai.worker.ts", import.meta.url), {
      type: "module",
    });
    worker.onmessage = (event: MessageEvent<AiWorkerResult>) => {
      const msg = event.data;
      if (!msg || msg.type !== "result") return;
      const p = pending.get(msg.id);
      if (!p) return;
      pending.delete(msg.id);
      p.resolve(msg.result);
    };
    worker.onerror = () => {
      workerFailed = true;
      for (const [, p] of pending) {
        p.reject(new Error("Dama AI worker failed"));
      }
      pending.clear();
      worker?.terminate();
      worker = null;
    };
    return worker;
  } catch {
    workerFailed = true;
    return null;
  }
}

export function cancelAllAiSearches(): void {
  if (worker) {
    for (const id of pending.keys()) {
      const cancel: AiWorkerInbound = { type: "cancel", id };
      worker.postMessage(cancel);
    }
  }
  for (const [, p] of pending) {
    p.resolve({
      move: null,
      score: 0,
      depth: 0,
      nodes: 0,
      aborted: true,
    });
  }
  pending.clear();
}

export function cancelAiSearch(id: number): void {
  const p = pending.get(id);
  if (!p) return;
  pending.delete(id);
  if (worker) {
    const cancel: AiWorkerInbound = { type: "cancel", id };
    worker.postMessage(cancel);
  }
  p.resolve({
    move: null,
    score: 0,
    depth: 0,
    nodes: 0,
    aborted: true,
  });
}

export interface AsyncAiOptions {
  difficulty?: AiStrength;
  timeBudgetMs?: number;
  signal?: AbortSignal;
  historyHashes?: number[];
}

/**
 * Prefer Web Worker search; fall back to main-thread search if workers fail.
 * AbortSignal / cancel id ensure only the current position's result is applied.
 */
export function chooseAiMoveAsync(
  board: Board,
  side: Side,
  options: AsyncAiOptions = {},
): { promise: Promise<SearchResult>; id: number } {
  const difficulty = normalizeDifficulty(options.difficulty ?? "hard");
  const id = nextId++;
  const w = ensureWorker();

  if (!w) {
    const promise = runMainThreadAsync(board, side, difficulty, options);
    return { promise, id };
  }

  const promise = new Promise<SearchResult>((resolve, reject) => {
    if (options.signal?.aborted) {
      resolve({ move: null, score: 0, depth: 0, nodes: 0, aborted: true });
      return;
    }

    pending.set(id, { resolve, reject });

    const onAbort = () => cancelAiSearch(id);
    options.signal?.addEventListener("abort", onAbort, { once: true });

    const payload: AiWorkerInbound = {
      type: "search",
      id,
      board,
      side,
      difficulty,
      timeBudgetMs: options.timeBudgetMs,
      historyHashes: options.historyHashes,
    };
    w.postMessage(payload);
  });

  return { promise, id };
}

async function runMainThreadAsync(
  board: Board,
  side: Side,
  difficulty: AiDifficulty,
  options: AsyncAiOptions,
): Promise<SearchResult> {
  await new Promise<void>((r) => setTimeout(r, 0));
  if (options.signal?.aborted) {
    return { move: null, score: 0, depth: 0, nodes: 0, aborted: true };
  }
  return chooseAiMoveDetailed(board, side, difficulty, {
    timeBudgetMs: options.timeBudgetMs,
    historyHashes: options.historyHashes,
    shouldCancel: () => Boolean(options.signal?.aborted),
  });
}

export function positionHash(board: Board, side: Side): number {
  return hashPosition(board, side);
}

export type { SearchResult, AiDifficulty };
