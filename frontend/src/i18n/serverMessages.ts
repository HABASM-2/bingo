import { translate, type TranslationKey } from "./translate";
import type { Locale } from "./types";

/**
 * Map stable English server messages to translation keys.
 * Unknown messages fall back to a generic localized error (optionally keeping detail).
 */
const EXACT_MAP: Record<string, TranslationKey> = {
  "Insufficient balance": "server.Insufficient balance",
  "Insufficient wallet balance": "server.Insufficient wallet balance",
  "Not enough balance": "server.Not enough balance",
  "Board already taken": "server.Board already taken",
  "Game already in progress": "server.Game already in progress",
  "Room not found": "server.Room not found",
  "Invalid stake": "server.Invalid stake",
  "Opponent disconnected": "server.Opponent disconnected",
  "Bet too late": "server.Bet too late",
  "No active bet": "server.No active bet",
  "Already cashed out": "server.Already cashed out",
  "Round not betting": "server.Round not betting",
  Unauthorized: "server.Unauthorized",
  Forbidden: "server.Forbidden",
  "Not found": "server.Not found",
  "Internal server error": "server.Internal server error",
  "Not a winner yet - keep playing!": "bingo.notWinner",
};

export function mapServerMessage(
  locale: Locale,
  message: string | null | undefined,
): string {
  if (!message) return translate(locale, "common.errorGeneric");
  const trimmed = message.trim();
  const key = EXACT_MAP[trimmed];
  if (key) return translate(locale, key);

  // Case-insensitive exact match
  const lower = trimmed.toLowerCase();
  for (const [en, k] of Object.entries(EXACT_MAP)) {
    if (en.toLowerCase() === lower) return translate(locale, k);
  }

  // Partial contains for common balance phrases
  if (/insufficient\s+(wallet\s+)?balance/i.test(trimmed)) {
    return translate(locale, "server.Insufficient balance");
  }
  if (/not enough balance/i.test(trimmed)) {
    return translate(locale, "server.Not enough balance");
  }

  // Keep original technical text when English UI; otherwise generic + short detail
  if (locale === "en") return trimmed;
  return translate(locale, "common.errorGeneric");
}
