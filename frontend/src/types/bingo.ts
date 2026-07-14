export type RoomStatus = "lobby" | "in_progress" | "finished";

export type BingoCell = number | null;
export type BingoCardGrid = BingoCell[][];
export type BingoMarksGrid = boolean[][];

export interface BingoCard {
  card_id: string;
  numbers: BingoCardGrid;
  marks: BingoMarksGrid;
}

export interface RoomPlayer {
  user_id: string;
  display_name: string;
  cards_count: number;
  connected: boolean;
  is_host: boolean;
}

export interface WinnerInfo {
  user_id: string;
  name: string;
  card_id: string;
  pattern: string;
}

export interface RoomSummary {
  room_id: string;
  name: string;
  status: RoomStatus;
  player_count: number;
  max_cards_per_player: number;
  entry_fee: string;
  drawn_count: number;
  current_ball: number | null;
}

export interface GameHistoryEntry {
  game_id: string;
  status: string;
  total_boards: number;
  total_players: number;
  derash: string;
  boards_count: number;
  stake: string;
  is_winner: boolean;
  amount_won: string;
  winning_pattern: string | null;
  created_at: string | null;
}

export interface JoinRoomResponse {
  room_id: string;
  ws_path: string;
  entry_fee: string;
  player_balance: string;
  max_cards_per_player: number;
  status: RoomStatus;
  player_count: number;
}

// ---------------------------------------------------------------------------
// WebSocket - client -> server
// ---------------------------------------------------------------------------

export type BingoClientMessage =
  | { type: "join" }
  | { type: "select_board"; board_id: number }
  | { type: "deselect_board"; board_id: number }
  | { type: "deselect_all" }
  | { type: "claim_bingo"; card_id: string }
  | { type: "ping" };

// ---------------------------------------------------------------------------
// WebSocket - server -> client
// ---------------------------------------------------------------------------

export interface RoomStateMessage {
  type: "room_state";
  room_id: string;
  name: string;
  status: RoomStatus;
  players: RoomPlayer[];
  cards: BingoCard[];
  drawn: number[];
  current_ball: number | null;
  entry_fee: string;
  player_balance: string;
  max_cards_per_player: number;
  // Winner metadata is only sent while status === "finished"; omitted (and so
  // optional) during the lobby / in-progress phases to keep snapshots lean.
  winner?: string | null;
  winner_name?: string | null;
  winning_pattern?: string | null;
  winning_card_id?: string | null;
  winners?: WinnerInfo[];
  derash_share?: string;
  board_price: string;
  max_boards: number;
  board_pool_max: number;
  my_boards: number[];
  taken_boards: number[];
  seconds_left: number;
  lobby_ends_at?: number | null;
  server_now?: number;
  game_id: string | null;
  derash: string;
  projected_derash?: string;
  player_count?: number;
  players_in_round: number;
  selected_boards_count?: number;
  call_count: number;
}

export interface PlayerCountMessage {
  type: "player_count";
  count: number;
}

export interface LobbyTickMessage {
  type: "lobby_tick";
  seconds_left: number;
  lobby_ends_at?: number | null;
  server_now?: number;
}

export interface ToastMessage {
  type: "toast";
  message: string;
}

export interface BallMessage {
  type: "ball";
  number: number;
  drawn: number[];
}

export interface BingoResultMessage {
  type: "bingo_result";
  valid: boolean;
  winner?: string | null;
  pattern?: string | null;
  card_id?: string | null;
  reason?: string | null;
}

export interface GameOverMessage {
  type: "game_over";
  winner: string | null;
  winner_name?: string | null;
  pattern?: string | null;
  winning_card_id?: string | null;
  derash?: string;
  derash_share?: string;
  winners?: WinnerInfo[];
  winner_count?: number;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export interface PongMessage {
  type: "pong";
}

export type BingoServerMessage =
  | RoomStateMessage
  | PlayerCountMessage
  | LobbyTickMessage
  | ToastMessage
  | BallMessage
  | BingoResultMessage
  | GameOverMessage
  | ErrorMessage
  | PongMessage;

export const BINGO_COLUMN_LETTERS = ["B", "I", "N", "G", "O"] as const;

export function letterForNumber(n: number): string {
  if (n <= 15) return "B";
  if (n <= 30) return "I";
  if (n <= 45) return "N";
  if (n <= 60) return "G";
  return "O";
}
