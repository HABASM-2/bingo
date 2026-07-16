import api from "../api/client";

export function aviatorWebSocketUrl(token: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/aviator?token=${encodeURIComponent(token)}`;
}

export async function getAviatorPresets(): Promise<{
  presets: string[];
  min: string;
  max: string;
  betting_seconds: number;
  start_multiplier: string;
}> {
  const response = await api.get("/aviator/presets");
  return response.data;
}

export async function getAviatorHistory(limit = 10, offset = 0): Promise<{
  bets: AviatorHistoryBet[];
  total: number;
  played: number;
  wins: number;
}> {
  const response = await api.get("/aviator/history", { params: { limit, offset } });
  return response.data;
}

export interface AviatorHistoryBet {
  bet_id: string;
  round_code: string;
  stake: string;
  cashout_multiplier: string | null;
  amount_won: string;
  outcome: "won" | "lost";
  crash_multiplier: string | null;
  created_at: string | null;
}

export interface AviatorTopGainer {
  rank: number;
  user_id: string;
  display_name: string;
  net_gain: string;
  total_won: string;
  bets_count: number;
}

export async function getAviatorLeaderboard(limit = 20): Promise<{
  players: AviatorTopGainer[];
}> {
  const response = await api.get("/aviator/leaderboard", { params: { limit } });
  return response.data;
}
