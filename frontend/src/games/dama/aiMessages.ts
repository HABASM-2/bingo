import type { Board, Move, Side } from "./engine";
import type { AiDifficulty, SearchResult } from "./ai";

export interface AiWorkerRequest {
  type: "search";
  id: number;
  board: Board;
  side: Side;
  difficulty: AiDifficulty;
  timeBudgetMs?: number;
  historyHashes?: number[];
}

export interface AiWorkerCancel {
  type: "cancel";
  id: number;
}

export type AiWorkerInbound = AiWorkerRequest | AiWorkerCancel;

export interface AiWorkerResult {
  type: "result";
  id: number;
  result: SearchResult;
}

export type { Move, SearchResult, AiDifficulty };
