import api from "../api/client";
import type { Board, Side } from "../games/dama/engine";
import type { DamaHistoryPage } from "../types/dama";

export function damaWebSocketUrl(token: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/dama?token=${encodeURIComponent(token)}`;
}

export interface DamaAiStartResult {
  game_code: string;
  stake: string;
  pot: string;
  system_fee: string;
  prize_pool: string;
  balance: string;
  turn_deadline?: number;
  session?: DamaAiSession;
  resumed?: boolean;
}

export interface DamaAiSession {
  game_code: string;
  stake: string;
  pot: string;
  system_fee: string;
  prize_pool: string;
  board: Board;
  turn: Side;
  ply_count: number;
  quiet_plies: number;
  status: string;
  winner: Side | "draw" | null;
  turn_deadline: number;
  created_at?: number;
  updated_at?: number;
}

export async function startDamaAiGame(stake: string): Promise<DamaAiStartResult> {
  const response = await api.post("/dama/ai/start", { stake });
  return response.data;
}

export async function getActiveDamaAiSession(): Promise<{
  active: boolean;
  session?: DamaAiSession;
  timed_out?: boolean;
  timeout_outcome?: "win" | "loss";
  settled?: {
    balances?: Record<string, string>;
    prize_pool?: string;
  };
}> {
  const response = await api.get("/dama/ai/active");
  return response.data;
}

export async function syncDamaAiSession(payload: {
  game_code: string;
  board: Board;
  turn: Side;
  ply_count: number;
  quiet_plies: number;
  status?: string;
  winner?: Side | "draw" | null;
  turn_deadline?: number;
}): Promise<{ ok: boolean; turn_deadline: number }> {
  const response = await api.post("/dama/ai/sync", payload);
  return response.data;
}

export async function finishDamaAiGame(
  gameCode: string,
  outcome: "win" | "loss" | "draw",
): Promise<{
  game_code: string;
  status: string;
  outcome?: string;
  prize_pool: string;
  amount_won?: string;
  balances?: Record<string, string>;
  already_finished?: boolean;
}> {
  const response = await api.post("/dama/ai/finish", {
    game_code: gameCode,
    outcome,
  });
  return response.data;
}

export async function getDamaHistory(
  limit = 10,
  offset = 0,
): Promise<DamaHistoryPage> {
  const response = await api.get("/dama/history", {
    params: { limit, offset },
  });
  return response.data;
}
