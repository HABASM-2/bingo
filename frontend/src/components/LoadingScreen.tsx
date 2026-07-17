import { Gamepad2, Sparkles } from "lucide-react";
import { useI18n } from "../i18n";

export default function LoadingScreen() {
  const { t } = useI18n();

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#faf7ff] via-[#eee7fb] to-[#e2d5f6] dark:from-black dark:via-slate-900 dark:to-purple-950">
      <div className="flex flex-col items-center">
        <div className="relative h-28 w-28">
          <div className="absolute inset-0 animate-pulse rounded-full bg-fuchsia-500 opacity-40 blur-xl" />

          <div className="absolute inset-0 flex items-center justify-center rounded-[2rem] border border-violet-300/50 bg-gradient-to-br from-white/80 to-fuchsia-100/50 shadow-2xl shadow-fuchsia-900/20 backdrop-blur-xl dark:border-white/20 dark:from-violet-500/25 dark:to-fuchsia-500/10 dark:shadow-fuchsia-950/40">
            <Gamepad2
              size={50}
              strokeWidth={1.8}
              className="text-violet-600 dark:text-violet-300"
              aria-hidden
            />
            <Sparkles
              size={24}
              className="absolute right-2 top-2 text-amber-300 drop-shadow-[0_0_8px_rgba(253,224,71,0.75)]"
              aria-hidden
            />
          </div>

          <div
            className="absolute -inset-2 animate-spin rounded-[2.25rem] border-[3px] border-fuchsia-400/20 border-t-fuchsia-300"
            role="status"
            aria-label={t("loading.aria")}
          />
        </div>

        <h1 className="mt-8 text-2xl font-black tracking-[0.14em] text-slate-900 dark:text-white">
          {t("loading.title")}
        </h1>
        <p className="mt-2 animate-pulse text-slate-600 dark:text-gray-400">
          {t("loading.subtitle")}
        </p>
      </div>
    </div>
  );
}
