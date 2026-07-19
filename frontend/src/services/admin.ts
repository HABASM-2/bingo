import api from "../api/client";

export const ADMIN_PAGE_SIZE = 20;

export interface AdminPermissions {
  is_admin: boolean;
  is_super: boolean;
  can_maintenance: boolean;
  can_adjust_balance: boolean;
  can_manage_admins: boolean;
  list?: string[];
}

export interface AdminMe {
  is_admin: boolean;
  is_super: boolean;
  username: string | null;
  permissions: AdminPermissions | string[];
  can_maintenance: boolean;
  can_adjust_balance: boolean;
  can_manage_admins: boolean;
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
  paid_from_account_id?: string | null;
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
  paidFromAccountId?: string | null,
) => (await api.post(`/admin/withdrawals/${id}/${action}`, {
  reason,
  request_id: requestId,
  paid_from_account_id: paidFromAccountId || undefined,
})).data;

export type PaymentAccountKind = "deposit" | "withdraw";

export interface PaymentAccount {
  id: string;
  kind: PaymentAccountKind;
  bank: string;
  account_name: string;
  account_number: string;
  is_enabled: boolean;
  sort_order: number;
  created_at?: string | null;
  updated_at?: string | null;
  idempotent?: boolean;
}

export const listPaymentAccounts = async (
  kind?: PaymentAccountKind,
): Promise<{ items: PaymentAccount[]; total: number }> =>
  (await api.get("/admin/payment-accounts", {
    params: kind ? { kind } : undefined,
  })).data;

export const createPaymentAccount = async (payload: {
  kind: PaymentAccountKind;
  bank: string;
  account_name: string;
  account_number: string;
  is_enabled?: boolean;
  sort_order?: number;
  requestId: string;
}): Promise<PaymentAccount> =>
  (await api.post("/admin/payment-accounts", {
    kind: payload.kind,
    bank: payload.bank,
    account_name: payload.account_name,
    account_number: payload.account_number,
    is_enabled: payload.is_enabled ?? true,
    sort_order: payload.sort_order ?? 0,
    request_id: payload.requestId,
  })).data;

export const updatePaymentAccount = async (
  id: string,
  payload: {
    bank?: string;
    account_name?: string;
    account_number?: string;
    is_enabled?: boolean;
    sort_order?: number;
    requestId: string;
  },
): Promise<PaymentAccount> =>
  (await api.patch(`/admin/payment-accounts/${id}`, {
    bank: payload.bank,
    account_name: payload.account_name,
    account_number: payload.account_number,
    is_enabled: payload.is_enabled,
    sort_order: payload.sort_order,
    request_id: payload.requestId,
  })).data;

export const deletePaymentAccount = async (
  id: string,
  requestId: string,
): Promise<{ id: string; deleted: boolean; idempotent?: boolean }> =>
  (await api.delete(`/admin/payment-accounts/${id}`, {
    params: { request_id: requestId },
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
  reserve_min: number;
  reserve_max: number;
  /** @deprecated Prefer reserve_min/max; kept for legacy clients. */
  reserve_count?: number;
  reserve_source?: "redis" | "default" | "legacy";
  allowed_min?: number;
  allowed_max?: number;
  boards_held: number;
  status: "active" | "inactive" | "draining" | "in_round";
  room_id?: string;
  room_status?: string | null;
  idempotent?: boolean;
}

export const getBingoBot = async (): Promise<BingoBotStatus> =>
  (await api.get("/admin/bingo-bot")).data;

export const setBingoBot = async (
  payload: {
    enabled?: boolean;
    reserve_min?: number;
    reserve_max?: number;
    /** @deprecated Accepts as min=max for one release. */
    reserve_count?: number;
  },
  requestId?: string,
): Promise<BingoBotStatus> =>
  (await api.post("/admin/bingo-bot", {
    ...payload,
    request_id: requestId,
  })).data;

export interface LottoBotStatus {
  enabled: boolean;
  source: "redis" | "env";
  reserve_min: number;
  reserve_max: number;
  reserve_source?: "redis" | "default";
  allowed_min?: number;
  allowed_max?: number;
  numbers_held: number;
  real_player_threshold?: number;
  status: "active" | "inactive" | "draining";
  rooms?: Array<{
    stake: string;
    round_id?: string;
    numbers_held: number;
    real_holders: number;
    occupied: number;
  }>;
  idempotent?: boolean;
}

export const getLottoBot = async (): Promise<LottoBotStatus> =>
  (await api.get("/admin/lotto-bot")).data;

export const setLottoBot = async (
  payload: { enabled?: boolean; reserve_min?: number; reserve_max?: number },
  requestId?: string,
): Promise<LottoBotStatus> =>
  (await api.post("/admin/lotto-bot", {
    ...payload,
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

export interface DeleteUserResult {
  idempotent: boolean;
  mode?: string;
  deleted_user?: Record<string, unknown>;
  deleted_count?: number;
  deleted_ids?: string[];
  skipped?: Array<Record<string, unknown>>;
  dependents?: Record<string, number>;
  force?: boolean;
}

export const deleteAdminUser = async (payload: {
  query: string;
  confirmation: string;
  reason: string;
  requestId: string;
  force?: boolean;
}): Promise<DeleteUserResult> =>
  (await api.post("/admin/users/delete", {
    query: payload.query,
    confirmation: payload.confirmation,
    reason: payload.reason,
    request_id: payload.requestId,
    force: payload.force ?? false,
  })).data;

export const deleteAllAdminUsers = async (payload: {
  confirmation: string;
  reason: string;
  requestId: string;
  force?: boolean;
}): Promise<DeleteUserResult> =>
  (await api.post("/admin/users/delete-all", {
    confirmation: payload.confirmation,
    reason: payload.reason,
    request_id: payload.requestId,
    force: payload.force ?? false,
  })).data;

export interface BroadcastResult {
  idempotent?: boolean;
  intended: number;
  succeeded: number;
  failed: number;
  errors: Array<{ telegram_id: number; error: string }>;
  has_button?: boolean;
  game?: string | null;
}

export const sendAdminBroadcast = async (payload: {
  message: string;
  buttonUrl?: string;
  buttonLabel?: string;
  game?: string;
  requestId: string;
}): Promise<BroadcastResult> =>
  (await api.post("/admin/broadcast", {
    message: payload.message,
    button_url: payload.buttonUrl || null,
    button_label: payload.buttonLabel || null,
    game: payload.game || null,
    request_id: payload.requestId,
  })).data;

export interface ManagedAdmin {
  username: string;
  is_super: boolean;
  created_by: string | null;
  created_at: string | null;
  managed: boolean;
}

export const listAdmins = async (): Promise<{ items: ManagedAdmin[]; total: number }> =>
  (await api.get("/admin/admins")).data;

export const addAdmin = async (username: string, requestId: string) =>
  (await api.post("/admin/admins", {
    username,
    request_id: requestId,
  })).data;

export const removeAdmin = async (username: string, requestId: string) =>
  (await api.delete(`/admin/admins/${encodeURIComponent(username)}`, {
    params: { request_id: requestId },
  })).data;
