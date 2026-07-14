import { useEffect, useState } from "react";
import { getMe, telegramLogin } from "../services/auth";
import type { AuthUser } from "../services/auth";

/**
 * Telegram Mini App WebViews persist `localStorage` across opens (and can
 * even survive account switches on the same device). Blindly trusting a
 * cached JWT makes every phone show the *first* user who ever logged in.
 *
 * Rule: when `Telegram.WebApp.initData` is present, that identity wins —
 * always exchange it for a fresh token. Cached JWT is only used as a
 * browser/dev fallback outside Telegram.
 */
export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function authenticate() {
      try {
        const tg = window.Telegram?.WebApp;
        const initData = tg?.initData?.trim() ?? "";

        if (initData) {
          try {
            tg?.ready();
            tg?.expand?.();
          } catch {
            // ready/expand are best-effort on older Telegram clients.
          }

          // Drop any sticky JWT *before* login so we never briefly attach the
          // previous user's Authorization header (or Bingo WS) to this launch.
          localStorage.removeItem("token");
          setToken(null);

          const data = await telegramLogin(initData);
          setToken(data.access_token);

          try {
            const me = await getMe();
            // Belt-and-suspenders: if Telegram exposed the user id in
            // initDataUnsafe, refuse to proceed when /me doesn't match.
            const tgId = tg?.initDataUnsafe?.user?.id;
            if (
              tgId != null &&
              me.telegram_id != null &&
              String(me.telegram_id) !== String(tgId)
            ) {
              localStorage.removeItem("token");
              setToken(null);
              setUser(null);
              console.error("Auth mismatch: JWT user != Telegram initData user");
              return;
            }

            setUser(me);
          } catch {
            setUser(data.user);
          }

          return;
        }

        // Outside Telegram (desktop browser testing): reuse a valid token.
        const cached = localStorage.getItem("token");

        if (cached) {
          try {
            const me = await getMe();
            setToken(cached);
            setUser(me);
            return;
          } catch {
            localStorage.removeItem("token");
            setToken(null);
          }
        }

        setUser(null);
      } catch (error) {
        console.error("Authentication failed", error);
        localStorage.removeItem("token");
        setToken(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    }

    authenticate();
  }, []);

  return {
    user,
    token,
    loading,
  };
}
