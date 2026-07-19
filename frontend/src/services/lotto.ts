import api from "../api/client";

export type LottoStatus = "open" | "countdown" | "drawing" | "completed" | "cancelled";

export interface LottoReservation {
  number: number;
  user_id: string;
  display_name: string;
  /** First 5 letters of display_name for compact board labels. */
  label5?: string;
  initials: string;
}

export interface LottoWinner {
  rank: number;
  number: number;
  user_id: string;
  display_name: string;
  prize: string;
  revealed_at: string | null;
}

export interface LottoRoom {
  id: string;
  round_code: string;
  stake: string;
  status: LottoStatus;
  capacity: number;
  occupied: number;
  total_pool: string;
  first_prize: string;
  second_prize: string;
  third_prize: string;
  reserve_amount: string;
  countdown_started_at: string | null;
  draw_scheduled_at: string | null;
  /** End of the pre-draw wait (= draw_scheduled_at). */
  pre_draw_ends_at?: string | null;
  drawing_started_at: string | null;
  completed_at: string | null;
  reservations: LottoReservation[];
  winners: LottoWinner[];
}

export interface LottoSnapshot {
  type: "snapshot";
  server_time: string;
  rooms: LottoRoom[];
}

export interface LottoHistoryItem {
  round_id: string;
  round_code: string;
  stake: string;
  numbers: number[];
  total_paid: string;
  winners: Array<{ rank: number; number: number; prize: string }>;
  total_prize: string;
  net: string;
  completed_at: string;
}

export interface LottoHistoryPage {
  items: LottoHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

export async function getLottoSnapshot(token: string): Promise<LottoSnapshot> {
  return (await api.get("/lotto/snapshot", auth(token))).data;
}

export async function reserveLotto(
  stakeRoom: string,
  numbers: number[],
  requestId: string,
  token: string,
): Promise<{
  round: LottoRoom;
  numbers: number[];
  charged_amount: string;
  balance: string;
  replayed: boolean;
}> {
  return (
    await api.post("/lotto/reserve", {
      stake_room: stakeRoom,
      numbers,
      request_id: requestId,
    }, auth(token))
  ).data;
}

export async function getLottoHistory(token: string, limit = 10, offset = 0): Promise<LottoHistoryPage> {
  return (await api.get("/lotto/history", { params: { limit, offset }, ...auth(token) })).data;
}

export function lottoWebSocketUrl(token: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/lotto?token=${encodeURIComponent(token)}`;
}
