import api from "../api/client";
import type { AviatorHistoryBet } from "./aviator";
import type { GameHistoryEntry } from "../types/bingo";
import type { DamaHistoryEntry } from "../types/dama";

export type ProfileGameKey = "bingo" | "dama" | "aviator" | "plinko" | "lotto";
export type ProfilePaymentType = "deposit" | "withdraw";

export interface ProfilePaymentItem {
  id: string;
  amount: string;
  method: string;
  status: string;
  fee?: string;
  account_masked?: string | null;
  created_at: string | null;
}

export interface ProfilePlinkoItem {
  play_id: string;
  stake: string;
  payout: string;
  net: string;
  multiplier: string;
  is_demo: boolean;
  risk: string;
  rows: number;
  created_at: string | null;
}

export interface ProfileLottoItem {
  round_id: string;
  round_code: string;
  stake: string;
  numbers: number[];
  total_paid: string;
  total_prize: string;
  net: string;
  completed_at: string | null;
}

export interface HistoryPage<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type ProfilePaymentPage = HistoryPage<ProfilePaymentItem>;

export type ProfileGameItem =
  | GameHistoryEntry
  | DamaHistoryEntry
  | AviatorHistoryBet
  | ProfilePlinkoItem
  | ProfileLottoItem;

export interface ProfileGameHistoryPage extends HistoryPage<ProfileGameItem> {}

const DEFAULT_LIMIT = 5;

export async function getGameHistory(
  game: ProfileGameKey,
  limit = DEFAULT_LIMIT,
  offset = 0,
  signal?: AbortSignal,
): Promise<ProfileGameHistoryPage> {
  const response = await api.get("/me/history", {
    params: { game, limit, offset },
    signal,
  });
  return response.data;
}

export async function getMyPayments(
  type: ProfilePaymentType,
  limit = DEFAULT_LIMIT,
  offset = 0,
  signal?: AbortSignal,
): Promise<ProfilePaymentPage> {
  const response = await api.get("/me/payments", {
    params: { type, limit, offset },
    signal,
  });
  return response.data;
}
