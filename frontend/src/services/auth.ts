import api from "../api/client";

// `balance` is the user's real Postgres wallet balance, always returned as a
// decimal string (see `/auth/me` and `/auth/telegram` on the backend). It is
// the single source of truth for wallet displays - never assume a shape that
// omits it, and never substitute a hardcoded/shared number in its place.
export interface AuthUser {
  id: string;
  telegram_id?: number | string;
  username?: string | null;
  first_name?: string;
  last_name?: string | null;
  photo_url?: string | null;
  balance: string;
  /** Unique invite code; used as Telegram `?start=` payload. */
  referral_code?: string | null;
  /** Prefabricated `https://t.me/<bot>?start=<code>` when bot username is configured. */
  invite_link?: string | null;
}

export interface TelegramLoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export async function telegramLogin(initData: string): Promise<TelegramLoginResponse> {

  const response = await api.post("/auth/telegram", {
    init_data: initData,
  });

  localStorage.setItem(
    "token",
    response.data.access_token
  );

  return response.data;
}


export async function getMe(): Promise<AuthUser> {

  const response = await api.get("/auth/me");

  return response.data;
}