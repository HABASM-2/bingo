import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  CircleDot,
  Coins,
  Crown,
  Gamepad2,
  Lock,
  Plane,
  Play,
  RotateCw,
  Sparkles,
  Users,
} from "lucide-react";
import { useI18n } from "../../i18n";

export type HomeGameId = "bingo" | "dama" | "aviator" | "plinko" | "lotto";

interface HomeViewProps {
  firstName: string;
  balance: string;
  bingoPlayers: number;
  bingoLive: boolean;
  bingoSecondsLeft: number;
  onOpenGame: (game: HomeGameId) => void;
}

type CatalogGame = {
  id: HomeGameId;
  name: string;
  tagline: string;
  icon: LucideIcon;
  playersLabel: string;
  cover: string;
  glow: string;
};

export function HomeView({
  firstName,
  balance,
  bingoPlayers,
  bingoLive,
  bingoSecondsLeft,
  onOpenGame,
}: HomeViewProps) {
  const { t, formatNumber } = useI18n();
  const numericBalance = Number(balance);
  const balanceLabel =
    balance !== "—" && Number.isFinite(numericBalance)
      ? formatNumber(numericBalance, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })
      : balance;
  const walletReady = balance !== "—" && Number.isFinite(numericBalance);

  const games: CatalogGame[] = [
    {
      id: "bingo",
      name: t("home.bingo.name"),
      tagline: bingoLive
        ? t("home.bingo.taglineLive")
        : t("home.bingo.taglineWait", { seconds: Math.max(0, bingoSecondsLeft) }),
      icon: Gamepad2,
      playersLabel:
        bingoPlayers > 0
          ? t("home.bingo.playersLive", { count: bingoPlayers })
          : t("home.bingo.playersWait"),
      cover: "from-[#5B21B6] via-[#7C3AED] to-[#DB2777]",
      glow: "bg-fuchsia-300/35",
    },
    {
      id: "dama",
      name: t("home.dama.name"),
      tagline: t("home.dama.tagline"),
      icon: Crown,
      playersLabel: t("home.dama.players"),
      cover: "from-[#9A3412] via-[#C2410C] to-[#F59E0B]",
      glow: "bg-amber-300/30",
    },
    {
      id: "aviator",
      name: t("home.aviator.name"),
      tagline: t("home.aviator.tagline"),
      icon: Plane,
      playersLabel: t("home.aviator.players"),
      cover: "from-[#1a0508] via-[#9f1239] to-[#E50539]",
      glow: "bg-rose-300/35",
    },
    {
      id: "plinko",
      name: t("home.plinko.name"),
      tagline: t("home.plinko.tagline"),
      icon: CircleDot,
      playersLabel: t("home.plinko.players"),
      cover: "from-[#020817] via-[#1245a8] to-[#db2777]",
      glow: "bg-cyan-300/30",
    },
    {
      id: "lotto",
      name: t("home.lotto.name"),
      tagline: t("home.lotto.tagline"),
      icon: RotateCw,
      playersLabel: t("home.lotto.players"),
      cover: "from-[#071426] via-[#0b5fa5] to-[#d59a21]",
      glow: "bg-amber-200/30",
    },
  ];
  const featuredGames = games.filter(({ id }) =>
    ["lotto", "aviator", "plinko"].includes(id),
  );

  return (
    <main className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-3 pb-5 pt-[max(0.75rem,env(safe-area-inset-top))] animate-[fadeIn_0.35s_ease-out] motion-reduce:animate-none">
      <header className="rounded-[1.4rem] border border-white/70 bg-white/70 p-3 shadow-[0_10px_30px_rgba(76,29,149,0.1)] backdrop-blur-xl dark:border-white/10 dark:bg-[#201c2e]/80 dark:shadow-[0_12px_30px_rgba(0,0,0,0.25)]">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-fuchsia-500 text-white shadow-md shadow-violet-500/25">
            <Sparkles size={18} aria-hidden />
          </div>
          <p className="min-w-0 text-[13px] font-black tracking-[0.12em] text-violet-950 dark:text-white">
            {t("home.brand")}
          </p>
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-extrabold text-emerald-800 dark:bg-emerald-400/10 dark:text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden />
            {t("common.online")}
          </span>
        </div>

        <div className="mt-3 flex min-w-0 flex-col gap-2.5 min-[380px]:flex-row min-[380px]:items-stretch">
          <div className="min-w-0 flex-1 px-0.5 py-1">
            <p className="text-[11px] font-bold uppercase tracking-wider text-violet-500 dark:text-violet-300/75">
              {t("home.welcomeBack")}
            </p>
            <h1 className="mt-0.5 break-words text-xl font-black leading-[1.3] text-violet-950 dark:text-white">
              {firstName}
            </h1>
            <p className="mt-1 text-xs font-medium leading-relaxed text-violet-600/80 dark:text-violet-200/70">
              {t("home.tagline")}
            </p>
          </div>

          <div
            className="flex min-w-0 items-center gap-2.5 rounded-2xl border border-violet-200/80 bg-gradient-to-br from-violet-50 to-fuchsia-50 px-3 py-2.5 min-[380px]:w-[9.5rem] min-[380px]:shrink-0 dark:border-violet-400/20 dark:from-violet-500/15 dark:to-fuchsia-500/10"
            aria-label={t("home.balanceAria", { amount: balanceLabel })}
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-violet-600 text-white shadow-sm">
              <Coins size={16} aria-hidden />
            </div>
            <div className="min-w-0">
              <p className="text-[9px] font-extrabold uppercase tracking-wider text-violet-500 dark:text-violet-300/70">
                {t("common.wallet")}
              </p>
              <p className="break-all text-sm font-black tabular-nums leading-tight text-violet-950 dark:text-white min-[400px]:text-base">
                {balanceLabel}
              </p>
              <p className="text-[9px] font-bold text-violet-500 dark:text-violet-300/70">
                {t("common.etb")}
              </p>
            </div>
          </div>
        </div>
      </header>

      <section
        aria-label={t("home.status")}
        className="mt-2.5 grid grid-cols-3 divide-x divide-violet-200/70 rounded-2xl border border-white/70 bg-white/55 px-1 py-2 shadow-sm dark:divide-white/10 dark:border-white/10 dark:bg-white/[0.045]"
      >
        <div className="min-w-0 px-2 text-center">
          <p className="text-sm font-black text-violet-950 dark:text-white">5</p>
          <p className="break-words text-[9px] font-bold uppercase leading-[1.35] tracking-wide text-violet-500 dark:text-violet-300/65">
            {t("home.statusGames")}
          </p>
        </div>
        <div className="min-w-0 px-2 text-center">
          <p className={`text-sm font-black ${bingoLive ? "text-emerald-600 dark:text-emerald-300" : "text-violet-950 dark:text-white"}`}>
            {bingoLive ? t("common.live") : `${Math.max(0, bingoSecondsLeft)}s`}
          </p>
          <p className="break-words text-[9px] font-bold uppercase leading-[1.35] tracking-wide text-violet-500 dark:text-violet-300/65">
            {t("home.statusBingo")}
          </p>
        </div>
        <div className="min-w-0 px-2 text-center">
          <p className="text-sm font-black text-violet-950 dark:text-white">
            {walletReady ? "✓" : "…"}
          </p>
          <p className="break-words text-[9px] font-bold uppercase leading-[1.35] tracking-wide text-violet-500 dark:text-violet-300/65">
            {walletReady ? t("home.walletReady") : t("home.walletSyncing")}
          </p>
        </div>
      </section>

      <section className="mt-4" aria-labelledby="featured-games-heading">
        <div className="flex items-end justify-between gap-3 px-0.5">
          <div className="min-w-0">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-fuchsia-600 dark:text-fuchsia-300">
              {t("home.featured")}
            </p>
            <h2 id="featured-games-heading" className="text-base font-black text-violet-950 dark:text-white">
              {t("home.playSomethingNew")}
            </h2>
          </div>
          <p className="shrink-0 text-[10px] font-semibold text-violet-500 dark:text-violet-300/65">
            {t("home.swipe")}
          </p>
        </div>

        <div className="-mx-3 mt-2 flex snap-x snap-mandatory gap-2.5 overflow-x-auto overscroll-x-contain px-3 pb-1 [-ms-overflow-style:none] [-webkit-overflow-scrolling:touch] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {featuredGames.map((game) => {
            const Icon = game.icon;
            return (
              <button
                key={game.id}
                type="button"
                onClick={() => onOpenGame(game.id)}
                aria-label={t("home.openGame", { game: game.name })}
                className={`group relative min-h-[8.25rem] w-[84%] min-w-[15rem] shrink-0 snap-center overflow-hidden rounded-[1.35rem] bg-gradient-to-br ${game.cover} p-4 text-left text-white shadow-lg outline-none ring-1 ring-black/5 transition-[transform,box-shadow] duration-200 active:scale-[0.985] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2 motion-reduce:transition-none`}
              >
                <div className={`absolute -right-5 -top-8 h-28 w-28 rounded-full ${game.glow} blur-2xl`} aria-hidden />
                <div className="absolute bottom-3 right-4 opacity-20 transition-transform duration-200 group-hover:scale-105 motion-reduce:transition-none" aria-hidden>
                  <Icon size={78} strokeWidth={1.35} />
                </div>
                <div className="relative flex h-full max-w-[75%] flex-col items-start">
                  <span className="rounded-full bg-white/15 px-2 py-1 text-[9px] font-black uppercase tracking-wider ring-1 ring-white/20 backdrop-blur-sm">
                    {t("home.featured")}
                  </span>
                  <h3 className="mt-2 text-xl font-black leading-tight">{game.name}</h3>
                  <p className="mt-1 line-clamp-2 text-[11px] font-medium leading-relaxed text-white/75">
                    {game.tagline}
                  </p>
                  <span className="mt-auto inline-flex items-center gap-1.5 text-[11px] font-extrabold">
                    {t("home.playNow")}
                    <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" aria-hidden />
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <section className="mt-4" aria-labelledby="all-games-heading">
        <div className="flex items-end justify-between gap-3 px-0.5">
          <div>
            <h2 id="all-games-heading" className="text-base font-black text-violet-950 dark:text-white">
              {t("home.allGames")}
            </h2>
            <p className="text-[10px] font-medium text-violet-500 dark:text-violet-300/65">
              {t("home.gamesHint")}
            </p>
          </div>
          <span className="shrink-0 rounded-full bg-white/60 px-2 py-1 text-[10px] font-bold text-violet-600 ring-1 ring-violet-200/70 dark:bg-white/[0.06] dark:text-violet-200 dark:ring-white/10">
            {t("home.gameCount", { count: games.length })}
          </span>
        </div>

        <div className="mt-2.5 grid grid-cols-2 gap-2.5 pb-1">
          {games.map((game) => {
          const Icon = game.icon;

          return (
            <button
              key={game.id}
              type="button"
              onClick={() => onOpenGame(game.id)}
              aria-label={t("home.openGame", { game: game.name })}
              className="group relative min-h-[9.25rem] overflow-hidden rounded-[1.2rem] border border-white/80 bg-white/75 p-2.5 text-left shadow-[0_7px_18px_rgba(76,29,149,0.07)] outline-none transition-[transform,border-color,box-shadow] duration-200 hover:border-violet-300 hover:shadow-[0_10px_24px_rgba(124,58,237,0.13)] active:scale-[0.975] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2 motion-reduce:transition-none dark:border-white/10 dark:bg-[#201c2e]/80 dark:hover:border-violet-400/35"
            >
              <div className="flex items-start justify-between gap-2">
                <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${game.cover} text-white shadow-md`}>
                  <Icon size={21} aria-hidden />
                </div>
                <span className={`rounded-full px-1.5 py-0.5 text-[8px] font-black uppercase tracking-wide ${
                  game.id === "bingo" && bingoLive
                    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300"
                    : "bg-violet-100 text-violet-700 dark:bg-violet-400/10 dark:text-violet-200"
                }`}>
                  {game.id === "bingo" && bingoLive ? t("common.live") : t("common.open")}
                </span>
              </div>
              <h3 className="mt-2 text-[15px] font-black leading-tight text-violet-950 dark:text-white">
                {game.name}
              </h3>
              <p className="mt-1 line-clamp-2 break-words text-[10px] font-medium leading-relaxed text-violet-500 dark:text-violet-300/70">
                {game.tagline}
              </p>
              <div className="mt-2 flex items-end justify-between gap-1.5">
                <span className="min-w-0 text-[9px] font-bold leading-snug text-violet-600 dark:text-violet-300">
                  <Users size={11} className="mr-1 inline-block align-[-2px]" aria-hidden />
                  {game.playersLabel}
                </span>
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-100 text-violet-700 transition-colors group-hover:bg-violet-600 group-hover:text-white dark:bg-white/10 dark:text-violet-200" aria-hidden>
                  <Play size={10} fill="currentColor" />
                </span>
              </div>
            </button>
          );
        })}
        </div>
      </section>
    </main>
  );
}

export function ComingSoonGame({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  const { t } = useI18n();

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center animate-[fadeIn_0.3s_ease-out]">
      <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-purple-500/20 to-orange-400/20 ring-1 ring-purple-200 dark:ring-white/10">
        <Lock className="text-purple-500" size={28} />
      </div>
      <h2 className="text-xl font-extrabold text-purple-950 dark:text-white">{title}</h2>
      <p className="max-w-xs text-sm font-medium text-purple-500 dark:text-purple-300/70">
        {description}
      </p>
      <span className="mt-1 rounded-full bg-purple-100 px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-purple-700 dark:bg-white/10 dark:text-purple-200">
        {t("home.comingSoonBadge")}
      </span>
    </div>
  );
}
