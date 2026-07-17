import api from "../api/client";

export type PlinkoRisk = "low" | "medium" | "high";

export interface PlinkoPlay {
  play_id: string;
  slot_index: number;
  multiplier: string;
  stake: string;
  payout: string;
  net: string;
  is_demo: boolean;
  balance: string | null;
  risk: PlinkoRisk;
  rows: number;
  created_at: string | null;
}

export interface PlinkoHistoryPage {
  items: PlinkoPlay[];
  total: number;
  paid_count: number;
  demo_count: number;
}

export interface PlinkoPresets {
  rows: number[];
  risks: PlinkoRisk[];
  min: string;
  max: string;
  tables: Record<PlinkoRisk, Record<string, string[]>>;
  rtp: Record<PlinkoRisk, Record<string, string>>;
}

export async function playPlinko(
  amount: string,
  risk: PlinkoRisk,
  rows: number,
  playId = crypto.randomUUID(),
): Promise<PlinkoPlay> {
  const response = await api.post("/plinko/play", {
    play_id: playId,
    amount,
    risk,
    rows,
  });
  return response.data;
}

export async function getPlinkoHistory(
  limit = 10,
  offset = 0,
): Promise<PlinkoHistoryPage> {
  const response = await api.get("/plinko/history", { params: { limit, offset } });
  return response.data;
}

export async function getPlinkoPresets(): Promise<PlinkoPresets> {
  const response = await api.get("/plinko/presets");
  return response.data;
}
