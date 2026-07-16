export type DamaSide = "red" | "black";

export type DamaPlayerStatus = "idle" | "challenging" | "busy";

export interface DamaOnlinePlayer {
  user_id: string;
  display_name: string;
  photo_url?: string | null;
  status: DamaPlayerStatus;
  is_self?: boolean;
}

export interface DamaChallenge {
  id: string;
  from_user_id: string;
  from_name: string;
  to_user_id: string;
  to_name: string;
  stake: string;
  created_at: number;
}

export interface DamaMatchPlayer {
  user_id: string;
  display_name: string;
}

export interface DamaServerMove {
  from: number;
  to: number;
  captures: number[];
  path: number[];
  promote: boolean;
}

export interface DamaHistoryEntry {
  game_id: string;
  mode: "ai" | "online" | string;
  status: string;
  stake: string;
  pot: string;
  system_fee: string;
  prize_pool: string;
  is_winner: boolean;
  amount_won: string;
  outcome: "win" | "loss" | "draw" | string;
  created_at: string | null;
}

export interface DamaHistoryPage {
  games: DamaHistoryEntry[];
  total: number;
  played: number;
  wins: number;
}

export type DamaClientMessage =
  | { type: "ping" }
  | { type: "list_players" }
  | { type: "challenge"; to_user_id: string; stake: string }
  | { type: "accept_challenge"; challenge_id: string }
  | { type: "decline_challenge"; challenge_id: string }
  | { type: "cancel_challenge"; challenge_id: string }
  | { type: "move"; match_id: string; from: number; to: number }
  | { type: "resign"; match_id: string }
  | { type: "claim_timeout"; match_id: string }
  | { type: "offer_draw"; match_id: string }
  | { type: "accept_draw"; match_id: string }
  | { type: "decline_draw"; match_id: string }
  | { type: "offer_rematch"; match_id: string; stake?: string }
  | { type: "accept_rematch"; match_id: string; stake?: string };

export type DamaServerMessage =
  | { type: "players"; players: DamaOnlinePlayer[]; resume_match?: DamaMatchStateMessage }
  | { type: "presence"; action: "join" | "leave" | "update"; player?: DamaOnlinePlayer; user_id?: string }
  | { type: "challenge_sent"; challenge: DamaChallenge }
  | { type: "challenge_incoming"; challenge: DamaChallenge }
  | { type: "challenge_declined"; challenge_id: string; by_user_id?: string }
  | {
      type: "match_start" | "match_state";
      match_id: string;
      board: Array<{ side: DamaSide; kind: "man" | "king" } | null>;
      turn: DamaSide;
      status: "playing" | "finished";
      winner: DamaSide | "draw" | null;
      last_move: DamaServerMove | null;
      my_side: DamaSide | null;
      stake?: string;
      pot?: string;
      system_fee?: string;
      prize_pool?: string;
      game_code?: string | null;
      balance?: string;
      rematch?: boolean;
      ply_count?: number;
      quiet_plies?: number;
      draw_eligible?: boolean;
      draw_offer_by?: string | null;
      rematch_offer_by?: string | null;
      rematch_stake?: string | null;
      turn_deadline?: number | null;
      red: DamaMatchPlayer;
      black: DamaMatchPlayer;
    }
  | {
      type: "move_applied";
      match_id: string;
      move: DamaServerMove;
      board: Array<{ side: DamaSide; kind: "man" | "king" } | null>;
      turn: DamaSide;
      status: "playing" | "finished";
      winner: DamaSide | "draw" | null;
      stake?: string;
      prize_pool?: string;
      ply_count?: number;
      quiet_plies?: number;
      draw_eligible?: boolean;
      draw_offer_by?: string | null;
      turn_deadline?: number | null;
    }
  | {
      type: "match_over";
      match_id: string;
      winner: DamaSide | "draw" | null;
      reason?: string;
      board: Array<{ side: DamaSide; kind: "man" | "king" } | null>;
      turn: DamaSide;
      status: "finished";
      stake?: string;
      prize_pool?: string;
      system_fee?: string;
      amount_won?: string;
      balance?: string;
    }
  | {
      type: "draw_offered";
      match_id: string;
      by_user_id: string;
      draw_eligible?: boolean;
    }
  | {
      type: "draw_declined";
      match_id: string;
      by_user_id: string;
      was_offered_by?: string;
    }
  | {
      type: "rematch_offered";
      match_id: string;
      by_user_id: string;
      stake?: string;
      peer_online?: boolean;
      delivered?: boolean;
    }
  | {
      type: "rematch_peer_left";
      match_id: string;
      user_id: string;
      had_offer?: boolean;
      reason?: string;
    }
  | { type: "error"; message: string }
  | { type: "ping" }
  | { type: "pong" }
  | { type: "ok" };

export type DamaMatchStateMessage = Extract<
  DamaServerMessage,
  { type: "match_start" | "match_state" }
>;
