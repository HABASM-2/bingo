import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { translate, type TranslationKey } from "./translate";
import {
  DEFAULT_LOCALE,
  INTL_LOCALE,
  LOCALE_STORAGE_KEY,
  type Locale,
  type TranslationParams,
} from "./types";
import { isLocale, setLanguageStore } from "./store";
import { mapServerMessage } from "./serverMessages";
import { readTelegramLaunch } from "../utils/telegramLaunch";

export interface I18nContextValue {
  language: Locale;
  setLanguage: (locale: Locale) => void;
  t: (key: TranslationKey, params?: TranslationParams) => string;
  formatNumber: (value: number, options?: Intl.NumberFormatOptions) => string;
  formatDate: (
    value: Date | string | number,
    options?: Intl.DateTimeFormatOptions,
  ) => string;
  /** Map known English server messages; unknown text falls back generically. */
  ts: (serverMessage: string | null | undefined) => string;
  intlLocale: string;
}

export const I18nContext = createContext<I18nContextValue | null>(null);

function readStoredLocale(): Locale {
  try {
    const raw = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (isLocale(raw)) return raw;
  } catch {
    /* ignore */
  }
  return DEFAULT_LOCALE;
}

function readInitialLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  // Deep-link / bot `lang` query wins once on first open, then is persisted.
  const launchLang = readTelegramLaunch().lang;
  if (launchLang) {
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, launchLang);
    } catch {
      /* ignore */
    }
    return launchLang;
  }
  return readStoredLocale();
}

function applyDocumentLang(locale: Locale): void {
  const root = document.documentElement;
  root.lang = locale;
  root.dir = "ltr";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Locale>(() => {
    const initial = readInitialLocale();
    setLanguageStore(initial);
    return initial;
  });

  useEffect(() => {
    applyDocumentLang(language);
    setLanguageStore(language);
  }, [language]);

  const setLanguage = useCallback((locale: Locale) => {
    setLanguageState(locale);
    setLanguageStore(locale);
    applyDocumentLang(locale);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    } catch {
      /* ignore */
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, params?: TranslationParams) => translate(language, key, params),
    [language],
  );

  const intlLocale = INTL_LOCALE[language];

  const formatNumber = useCallback(
    (value: number, options?: Intl.NumberFormatOptions) =>
      new Intl.NumberFormat(intlLocale, options).format(value),
    [intlLocale],
  );

  const formatDate = useCallback(
    (value: Date | string | number, options?: Intl.DateTimeFormatOptions) => {
      const date = value instanceof Date ? value : new Date(value);
      if (Number.isNaN(date.getTime())) return "";
      return new Intl.DateTimeFormat(intlLocale, options).format(date);
    },
    [intlLocale],
  );

  const ts = useCallback(
    (serverMessage: string | null | undefined) => mapServerMessage(language, serverMessage),
    [language],
  );

  const value = useMemo<I18nContextValue>(
    () => ({
      language,
      setLanguage,
      t,
      formatNumber,
      formatDate,
      ts,
      intlLocale,
    }),
    [language, setLanguage, t, formatNumber, formatDate, ts, intlLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
