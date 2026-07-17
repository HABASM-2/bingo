import { DEFAULT_LOCALE, type Locale } from "./types";
import { LOCALES } from "./types";

type Listener = () => void;

let current: Locale = DEFAULT_LOCALE;
const listeners = new Set<Listener>();

export function getLanguage(): Locale {
  return current;
}

export function setLanguageStore(locale: Locale): void {
  if (current === locale) return;
  current = locale;
  listeners.forEach((l) => l());
}

export function subscribeLanguage(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}
