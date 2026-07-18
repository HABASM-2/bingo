import api from "../api/client";

export const ADMIN_PAGE_SIZE = 20;

export interface AdminMe {
  is_admin: boolean;
  username: string | null;
  permissions: string[];
}

export interface GameMetric {
  game: string;
  turnover: string;
  payouts: string;
  ggr: string;
  explicit_system_fee: string;
  unique_players: number;
  rounds_or_plays: number;
  bot_turnover?: string;
  bot_payouts?: string;
  bot_pnl?: string;
  bot_rounds?: number;
}

export interface Dashboard {
  total_users: number;
  new_users: number;
  active_users: number;
  wallet_liabilities: string;
  wallet_liabilities_without_bots?: string;
  wallet_liabilities_with_bots?: string;
  turnover: string;
  payouts: string;
  ggr: string;
  explicit_system_revenue: string;
  deposits: {
    pending_count: number;
    pending_amount: string;
    approved_count: number;
    approved_amount: string;
    workflow: string;
  };
  withdrawals: Record<string, { count: number; amount: string }>;
  action_queue: {
    pending_withdrawals: { count: number; amount: string };
  };
  games: GameMetric[];
}

export interface AdminUser {
  id: string;
  telegram_id: string;
  username: string | null;
  first_name: string;
  last_name: string | null;
  balance: string;
  joined_at: string;
  last_activity_at: string;
  games_played: number;
  deposit_total: string;
  withdraw_total: string;
  status: string;
  is_bot?: boolean;
}

export interface Payment {
  id: string;
  user_id: string;
  username: string | null;
  name: string;
  amount: string;
  method: string;
  status: string;
  created_at: string;
  completed_at?: string;
  reference?: string;
  provider?: string;
  fee?: string;
  account_name?: string;
  account_number_masked?: string;
}

export interface AuditItem {
  id: string;
  admin_username: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  reason: string | null;
  created_at: string;
}

export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
  workflow?: string;
  pending_supported?: boolean;
}

export const getAdminMe = async (): Promise<AdminMe> =>
  (await api.get("/admin/me")).data;

export const getDashboard = async (from?: string): Promise<Dashboard> =>
  (await api.get("/admin/dashboard", { params: from ? { from } : {} })).data;

export const getUsers = async (params: {
  search?: string;
  status?: string;
  offset?: number;
  limit?: number;
  sort?: string;
}): Promise<Page<AdminUser>> =>
  (await api.get("/admin/users", {
    params: {
      search: params.search || undefined,
      status: params.status,
      offset: params.offset ?? 0,
      limit: params.limit ?? ADMIN_PAGE_SIZE,
      sort: params.sort ?? "joined_desc",
    },
  })).data;

export const getUserDetail = async (id: string) =>
  (await api.get(`/admin/users/${id}`)).data;

export const adjustBalance = async (
  id: string,
  amount: string,
  reason: string,
  requestId: string,
) => (await api.post(`/admin/users/${id}/balance-adjustments`, {
  amount,
  reason,
  request_id: requestId,
})).data;

export const getDeposits = async (params: {
  status?: string;
  search?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Page<Payment>> =>
  (await api.get("/admin/deposits", {
    params: {
      status: params.status ?? "all",
      search: params.search,
      from: params.from,
      to: params.to,
      limit: params.limit ?? ADMIN_PAGE_SIZE,
      offset: params.offset ?? 0,
    },
  })).data;

export const getWithdrawals = async (params: {
  status?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Page<Payment>> =>
  (await api.get("/admin/withdrawals", {
    params: {
      status: params.status,
      limit: params.limit ?? ADMIN_PAGE_SIZE,
      offset: params.offset ?? 0,
    },
  })).data;

export const decideWithdrawal = async (
  id: string,
  action: "approve" | "reject",
  reason: string | null,
  requestId: string,
) => (await api.post(`/admin/withdrawals/${id}/${action}`, {
  reason,
  request_id: requestId,
})).data;

export const getGamePlayers = async (
  game: string,
  params: { from?: string; limit?: number; offset?: number } = {},
): Promise<Page<{
  user_id: string;
  username: string | null;
  first_name: string;
  is_bot?: boolean;
  plays: number;
  turnover: string;
  payouts: string;
  last_played_at?: string;
}>> =>
  (await api.get(`/admin/games/${game}/players`, {
    params: {
      from: params.from,
      limit: params.limit ?? ADMIN_PAGE_SIZE,
      offset: params.offset ?? 0,
    },
  })).data;

export const getAudit = async (params: {
  limit?: number;
  offset?: number;
} = {}): Promise<Page<AuditItem>> =>
  (await api.get("/admin/audit", {
    params: {
      limit: params.limit ?? ADMIN_PAGE_SIZE,
      offset: params.offset ?? 0,
    },
  })).data;

export interface BingoBotStatus {
  enabled: boolean;
  source: "redis" | "env";
  boards_held: number;
  status: "active" | "inactive" | "draining" | "in_round";
  room_id?: string;
  room_status?: string | null;
  idempotent?: boolean;
}

export const getBingoBot = async (): Promise<BingoBotStatus> =>
  (await api.get("/admin/bingo-bot")).data;

export const setBingoBot = async (
  enabled: boolean,
  requestId?: string,
): Promise<BingoBotStatus> =>
  (await api.post("/admin/bingo-bot", {
    enabled,
    request_id: requestId,
  })).data;

export type RetentionOption =
  | "all"
  | "games_only"
  | "7d"
  | "14d"
  | "21d"
  | "30d"
  | "60d"
  | "90d"
  | "120d"
  | "150d";

export interface RetentionPreview {
  option: RetentionOption;
  cutoff: string | null;
  confirmation_required: string;
  keeps_users: boolean;
  keeps_payments?: boolean;
  zeros_balances: boolean;
  flushes_redis_game_keys: boolean;
  users_kept: number;
  balances_to_zero: number;
  counts: Record<string, number>;
  total_rows: number;
}

export interface RetentionPurgeResult {
  idempotent: boolean;
  option: RetentionOption;
  deleted: Record<string, number>;
  balances_zeroed: number;
  redis_keys_deleted: number;
  users_kept: number;
  cutoff?: string | null;
}

export const previewDataRetention = async (
  option: RetentionOption,
): Promise<RetentionPreview> =>
  (await api.get("/admin/data-retention/preview", { params: { option } })).data;

export const purgeDataRetention = async (payload: {
  option: RetentionOption;
  confirmation: string;
  reason: string;
  requestId: string;
}): Promise<RetentionPurgeResult> =>
  (await api.post("/admin/data-retention/purge", {
    option: payload.option,
    confirmation: payload.confirmation,
    reason: payload.reason,
    request_id: payload.requestId,
  })).data;
