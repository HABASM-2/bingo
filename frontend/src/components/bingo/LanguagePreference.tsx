import type { Locale } from "../../i18n";
import { useI18n } from "../../i18n";

const OPTIONS: { id: Locale; labelKey: "language.amharic" | "language.english" }[] = [
  { id: "am", labelKey: "language.amharic" },
  { id: "en", labelKey: "language.english" },
];

/** Compact language control for the Profile tab — English is the app default. */
export function LanguagePreference() {
  const { language, setLanguage, t } = useI18n();

  return (
    <div className="w-full max-w-sm">
      <p className="mb-2 text-left text-xs font-semibold uppercase tracking-wide text-purple-500 dark:text-purple-300">
        {t("language.label")}
      </p>
      <div className="grid grid-cols-2 gap-2 rounded-2xl bg-white/80 p-1.5 ring-1 ring-purple-100 dark:bg-white/5 dark:ring-white/10">
        {OPTIONS.map(({ id, labelKey }) => {
          const selected = language === id;

          return (
            <button
              key={id}
              type="button"
              onClick={() => setLanguage(id)}
              className={`rounded-xl px-2 py-2.5 text-xs font-bold transition-all duration-200 ${
                selected
                  ? "bg-[#4C1D95] text-white shadow dark:bg-violet-600"
                  : "text-purple-700 hover:bg-purple-50 dark:text-purple-200 dark:hover:bg-white/10"
              }`}
            >
              {t(labelKey)}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] font-medium text-purple-400 dark:text-purple-300/70">
        {t("language.hint")}
      </p>
    </div>
  );
}
