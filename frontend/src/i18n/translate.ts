import type { Locale, TranslationParams } from "./types";
import { en } from "./locales/en";
import { am } from "./locales/am";

export type TranslationKey = keyof typeof en;

const dictionaries: Record<Locale, Record<TranslationKey, string>> = {
  en,
  am,
};

function interpolate(template: string, params?: TranslationParams): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = params[key];
    if (value == null) return "";
    return String(value);
  });
}

/**
 * Resolve a translation key for the given locale.
 * Plural: if `params.count` is present and not 1, prefer `${key}_plural` when defined.
 */
export function translate(
  locale: Locale,
  key: TranslationKey,
  params?: TranslationParams,
): string {
  const dict = dictionaries[locale] ?? dictionaries.en;
  let resolvedKey = key;

  if (params && "count" in params) {
    const count = Number(params.count);
    if (Number.isFinite(count) && count !== 1) {
      const pluralKey = `${key}_plural` as TranslationKey;
      if (pluralKey in dict) {
        resolvedKey = pluralKey;
      }
    }
  }

  const template = dict[resolvedKey] ?? dictionaries.en[resolvedKey] ?? String(key);
  return interpolate(template, params);
}

export function assertTranslationParity(): void {
  const enKeys = Object.keys(en).sort();
  const amKeys = Object.keys(am).sort();
  if (enKeys.length !== amKeys.length) {
    throw new Error(
      `i18n key count mismatch: en=${enKeys.length} am=${amKeys.length}`,
    );
  }
  for (let i = 0; i < enKeys.length; i += 1) {
    if (enKeys[i] !== amKeys[i]) {
      throw new Error(`i18n key mismatch at ${i}: en=${enKeys[i]} am=${amKeys[i]}`);
    }
  }
}
