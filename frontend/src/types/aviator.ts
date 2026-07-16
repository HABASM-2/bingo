export type AviatorPhase = "waiting" | "betting" | "flying" | "crashed";

export interface AviatorBetRow {
  bet_id: string;
  user_id: string;
  display_name: string;
  stake: string;
  slot: number;
  status: "active" | "cashed" | "lost";
  cashout_at?: number | null;
  win?: string | null;
}

export interface AviatorRoundState {
  round_id?: string;
  round_code?: string;
  phase: AviatorPhase;
  crash_multiplier?: number | null;
  multiplier?: number;
  betting_ends_at?: number | null;
  betting_seconds_left?: number;
  flying_started_at?: number | null;
  total_stake?: string;
  total_payout?: string;
  pool_remaining?: string;
  player_count?: number;
  bets: AviatorBetRow[];
  history?: number[];
}

export type AviatorClientMessage =
  | { type: "ping" }
  | { type: "snapshot" }
  | { type: "bet"; stake: string; slot?: number }
  | { type: "cashout"; bet_id?: string; slot?: number };

export type AviatorServerMessage =
  | (AviatorRoundState & { type: "round_state" | "phase"; balance?: string })
  | {
      type: "tick";
      round_id: string;
      multiplier: number;
      phase: AviatorPhase;
    }
  | {
      type: "bet_placed";
      bet: AviatorBetRow;
      round: AviatorRoundState;
      balance: string;
    }
  | {
      type: "cashout";
      bet_id: string;
      user_id: string;
      cashout_at: number;
      win: string;
      multiplier: number;
      round: AviatorRoundState;
      balance: string;
    }
  | { type: "error"; message: string }
  | { type: "ping" }
  | { type: "pong" };
