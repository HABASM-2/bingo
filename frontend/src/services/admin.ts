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
}

export interface Dashboard {
  total_users: number;
  new_users: number;
  active_users: number;
  wallet_liabilities: string;
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
