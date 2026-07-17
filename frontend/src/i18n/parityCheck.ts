/**
 * Lightweight structural check for EN/AM key parity.
 * Run: npx tsx src/i18n/parityCheck.ts
 * (Also imported by vite build via assert in translate — call from a script.)
 */
import { assertTranslationParity } from "./translate";
import { DEFAULT_LOCALE } from "./types";
import { translate } from "./translate";

assertTranslationParity();

const sample = translate("am", "nav.home");
if (sample !== "መነሻ") {
  throw new Error(`Expected Amharic Home label, got: ${sample}`);
}

const interpolated = translate("en", "home.greeting", { name: "Ada" });
if (interpolated !== "Hi, Ada") {
  throw new Error(`Interpolation failed: ${interpolated}`);
}

const plural = translate("en", "aviator.playersInRound", { count: 3 });
if (plural !== "3 players in round") {
  throw new Error(`Plural failed: ${plural}`);
}

if (
  translate("en", "loading.title") !== "BRIGHT GAMES" ||
  translate("am", "loading.title") !== "BRIGHT GAMES"
) {
  throw new Error("Loading brand must remain BRIGHT GAMES in every locale");
}

if (translate("en", "loading.subtitle") !== "Connecting to games…") {
  throw new Error("English startup connection message is incorrect");
}

if (DEFAULT_LOCALE !== "en") {
  throw new Error("Default locale must be en");
}

console.log("i18n parity + interpolation OK");
