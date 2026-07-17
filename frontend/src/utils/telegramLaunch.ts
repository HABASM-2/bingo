import type { NavTab } from "../components/bingo/BottomNav";
import { isLocale } from "../i18n/store";
import type { Locale } from "../i18n/types";

/** Games that can be opened via Mini App deep link / start_param. */
export const LAUNCH_GAMES = [
  "bingo",
  "dama",
  "aviator",
  "plinko",
  "lotto",
  "home",
  "admin",
] as const;

export type LaunchGame = (typeof LAUNCH_GAMES)[number];

const LAUNCH_GAME_SET = new Set<string>(LAUNCH_GAMES);

export function isLaunchGame(value: unknown): value is LaunchGame {
  return typeof value === "string" && LAUNCH_GAME_SET.has(value);
}

export function launchGameToTab(game: LaunchGame): NavTab {
  return game === "home" ? "home" : game;
}

function readQueryParam(name: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const fromSearch = new URLSearchParams(window.location.search).get(name);
    if (fromSearch) return fromSearch;
    // Telegram may put tgWebAppStartParam in the hash / query.
    const hash = window.location.hash.startsWith("#")
      ? window.location.hash.slice(1)
      : window.location.hash;
    if (hash.includes("=")) {
      const fromHash = new URLSearchParams(hash).get(name);
      if (fromHash) return fromHash;
    }
  } catch {
    /* ignore */
  }
  return null;
}

function parseStartParam(raw: string | null | undefined): {
  game: LaunchGame | null;
  lang: Locale | null;
} {
  if (!raw) return { game: null, lang: null };
  const parts = raw
    .trim()
    .toLowerCase()
    .replace(/-/g, "_")
    .split("_")
    .filter(Boolean);
  if (!parts.length) return { game: null, lang: null };

  let game: LaunchGame | null = null;
  let lang: Locale | null = null;

  if (parts[0] === "game" && parts[1] && isLaunchGame(parts[1])) {
    game = parts[1];
    if (parts[2] && isLocale(parts[2])) lang = parts[2];
    return { game, lang };
  }

  if (isLaunchGame(parts[0])) {
    game = parts[0];
    if (parts[1] && isLocale(parts[1])) lang = parts[1];
    return { game, lang };
  }

  if (isLocale(parts[0]) && parts[1] && isLaunchGame(parts[1])) {
    return { game: parts[1], lang: parts[0] };
  }

  return { game: null, lang: null };
}

/**
 * Read once-per-launch game + optional lang from:
 * - URL `?game=` / `?lang=`
 * - `tgWebAppStartParam`
 * - `Telegram.WebApp.initDataUnsafe.start_param`
 */
export function readTelegramLaunch(): {
  game: LaunchGame | null;
  lang: Locale | null;
} {
  const queryGame = readQueryParam("game");
  const queryLang = readQueryParam("lang");
  const startParam =
    readQueryParam("tgWebAppStartParam") ??
    window.Telegram?.WebApp?.initDataUnsafe?.start_param ??
    null;

  const fromStart = parseStartParam(startParam);

  const game = isLaunchGame(queryGame)
    ? queryGame
    : fromStart.game;

  const lang =
    (isLocale(queryLang) ? queryLang : null) ?? fromStart.lang;

  return { game, lang };
}
