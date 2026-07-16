import type { LucideIcon } from "lucide-react";
import { Crown, Gamepad2, Lock, Plane, Play, Sparkles, Users } from "lucide-react";

export type HomeGameId = "bingo" | "dama" | "aviator";

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
  live: boolean;
  playersLabel: string;
  accent: string;
  cover: string;
};

export function HomeView({
  firstName,
  balance,
  bingoPlayers,
  bingoLive,
  bingoSecondsLeft,
  onOpenGame,
}: HomeViewProps) {
  const games: CatalogGame[] = [
    {
      id: "bingo",
      name: "Bingo",
      tagline: bingoLive
        ? "Round in progress — jump back in"
        : `Next round in ${Math.max(0, bingoSecondsLeft)}s`,
      icon: Gamepad2,
      live: true,
      playersLabel:
        bingoPlayers > 0
          ? `${bingoPlayers} live now`
          : "Waiting for players",
      accent: "from-violet-600 via-fuchsia-500 to-orange-400",
      cover: "from-[#5B21B6] via-[#7C3AED] to-[#DB2777]",
    },
    {
      id: "dama",
      name: "Dama",
      tagline: "Dalamax checkers — online opponents or AI",
      icon: Crown,
      live: true,
      playersLabel: "Play now",
      accent: "from-orange-500 to-amber-400",
      cover: "from-[#9A3412] via-[#C2410C] to-[#F59E0B]",
    },
    {
      id: "aviator",
      name: "Aviator",
      tagline: "Cash out before the plane flies away.",
      icon: Plane,
      live: true,
      playersLabel: "Single & multiplayer",
      accent: "from-rose-500 to-red-600",
      cover: "from-[#1a0508] via-[#9f1239] to-[#E50539]",
    },
  ];

  return (
    <div className="flex h-full flex-col overflow-y-auto px-3 py-3 animate-[fadeIn_0.35s_ease-out]">
      <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#4C1D95] via-[#6D28D9] to-[#DB2777] px-4 py-4 text-white shadow-lg shadow-purple-900/20">
        <div className="absolute -right-6 -top-8 h-28 w-28 rounded-full bg-white/15 blur-2xl" />
        <div className="absolute -bottom-10 left-8 h-24 w-24 rounded-full bg-orange-300/25 blur-2xl" />

        <div className="relative flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/70">
              Bright Games
            </p>
            <h1 className="mt-1 text-2xl font-black leading-tight">
              Hi, {firstName}
            </h1>
            <p className="mt-1 max-w-[16rem] text-sm text-white/80">
              Choose a game. Live rooms and upcoming titles live here.
            </p>
          </div>
          <div className="rounded-2xl bg-white/15 px-3 py-2 text-right backdrop-blur-sm ring-1 ring-white/20">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/70">
              Wallet
            </p>
            <p className="text-lg font-extrabold tabular-nums">{balance}</p>
            <p className="text-[10px] text-white/65">ETB</p>
          </div>
        </div>

        <div className="relative mt-3 inline-flex items-center gap-1.5 rounded-full bg-black/20 px-2.5 py-1 text-[11px] font-semibold text-white/90 ring-1 ring-white/15">
          <Sparkles size={12} />
          {bingoLive ? "Bingo is live right now" : "Lobby open — pick boards"}
        </div>
      </header>

      <div className="mt-4 flex items-end justify-between px-0.5">
        <div>
          <h2 className="text-base font-extrabold text-purple-950 dark:text-white">
            Games
          </h2>
          <p className="text-[11px] font-medium text-purple-500 dark:text-purple-300/70">
            Live player counts update as rooms fill
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-3 pb-2">
        {games.map((game) => {
          const Icon = game.icon;
          const locked = !game.live;

          return (
            <button
              key={game.id}
              type="button"
              disabled={locked}
              onClick={() => onOpenGame(game.id)}
              className={`group relative overflow-hidden rounded-3xl text-left shadow-md ring-1 transition-all duration-200 ${
                locked
                  ? "bg-white/70 ring-purple-100/80 opacity-90 dark:bg-[#1A1726] dark:ring-white/10"
                  : "bg-white/95 ring-purple-100 active:scale-[0.985] dark:bg-[#1E1B2E] dark:ring-white/10"
              }`}
            >
              <div className="flex gap-0">
                <div
                  className={`relative flex w-[5.5rem] shrink-0 items-center justify-center bg-gradient-to-br ${game.cover}`}
                >
                  <Icon size={34} className="text-white drop-shadow" />
                  {game.live && (
                    <span className="absolute left-2 top-2 rounded-full bg-emerald-400 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wide text-emerald-950 shadow">
                      Live
                    </span>
                  )}
                </div>

                <div className="flex min-w-0 flex-1 flex-col justify-between px-3 py-3">
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="text-lg font-extrabold text-purple-950 dark:text-white">
                        {game.name}
                      </h3>
                      {!locked && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-bold text-purple-700 dark:bg-white/10 dark:text-purple-200">
                          <Play size={10} fill="currentColor" />
                          Open
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs font-medium text-purple-500 dark:text-purple-300/75">
                      {game.tagline}
                    </p>
                  </div>

                  <div className="mt-2.5 flex items-center justify-between">
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-purple-600 dark:text-purple-300">
                      <Users size={13} />
                      {game.playersLabel}
                    </span>
                    {locked ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-stone-400">
                        <Lock size={12} />
                        Soon
                      </span>
                    ) : (
                      <span
                        className={`h-2 w-2 rounded-full bg-gradient-to-r ${game.accent} shadow`}
                        aria-hidden
                      />
                    )}
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ComingSoonGame({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
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
        Template · Coming soon
      </span>
    </div>
  );
}
