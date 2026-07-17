import { useContext, useMemo, useSyncExternalStore } from "react";
import { I18nContext } from "./I18nProvider";
import { translate, type TranslationKey } from "./translate";
import type { Locale, TranslationParams } from "./types";
import { INTL_LOCALE } from "./types";
import { getLanguage, subscribeLanguage } from "./store";

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return ctx;
}

/** Non-React translation using the live language store (hooks / callbacks). */
export function tGlobal(key: TranslationKey, params?: TranslationParams): string {
  return translate(getLanguage(), key, params);
}

export function useLanguage(): Locale {
  return useSyncExternalStore(subscribeLanguage, getLanguage, getLanguage);
}

export function useFormatters() {
  const { language } = useI18n();
  const intl = INTL_LOCALE[language];

  return useMemo(
    () => ({
      formatNumber: (value: number, options?: Intl.NumberFormatOptions) =>
        new Intl.NumberFormat(intl, options).format(value),
      formatDate: (value: Date | string | number, options?: Intl.DateTimeFormatOptions) => {
        const date = value instanceof Date ? value : new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        return new Intl.DateTimeFormat(intl, options).format(date);
      },
      intlLocale: intl,
    }),
    [intl],
  );
}

export function useT() {
  const { t } = useI18n();
  return t;
}

export type { TranslationKey, TranslationParams, Locale };
