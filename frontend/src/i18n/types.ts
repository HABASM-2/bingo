export type Locale = "am" | "en";

export const LOCALES: readonly Locale[] = ["am", "en"] as const;

export const DEFAULT_LOCALE: Locale = "en";

export const LOCALE_STORAGE_KEY = "bright-games:locale";

/** BCP 47 tags for Intl formatters. */
export const INTL_LOCALE: Record<Locale, string> = {
  am: "am-ET",
  en: "en-ET",
};

export type TranslationParams = Record<
  string,
  string | number | boolean | null | undefined
>;
