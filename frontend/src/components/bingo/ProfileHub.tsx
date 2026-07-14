import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2, Trophy, Wallet } from "lucide-react";
import { getBingoHistory } from "../../services/bingo";
import type { GameHistoryEntry } from "../../types/bingo";
import { ThemePreference } from "./ThemePreference";

const PAGE_SIZE = 4;

interface ProfileHubProps {
  firstName: string;
  balance: string | null;
  boardPrice: string;
}

function formatBalance(balance: string | null): string {
  if (balance == null) return "—";
  const n = Number(balance);
  return Number.isFinite(n) ? n.toFixed(2) : balance;
}

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function ProfileHub({ firstName, balance, boardPrice }: ProfileHubProps) {
  const [games, setGames] = useState<GameHistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  useEffect(() => {
    let cancelled = false;

    getBingoHistory()
      .then((rows) => {
        if (!cancelled) {
          setGames(rows);
          setPage(0);
        }
      })
      .catch(() => {
        if (!cancelled) setError("Could not load your game history.");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const totalPages = games ? Math.max(1, Math.ceil(games.length / PAGE_SIZE)) : 1;
  const safePage = Math.min(page, totalPages - 1);

  const pageRows = useMemo(() => {
    if (!games) return [];
    const start = safePage * PAGE_SIZE;
    return games.slice(start, start + PAGE_SIZE);
  }, [games, safePage]);

  const wins = games?.filter((g) => g.is_winner).length ?? 0;
  const played = games?.length ?? 0;
  const initial = (firstName.trim()[0] || "P").toUpperCase();

  return (
    <div className="flex flex-col gap-4 px-4 py-5 animate-[fadeIn_0.3s_ease-out]">
      {/* Identity */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#4C1D95] via-[#6D28D9] to-[#7C3AED] p-5 text-white shadow-lg">
        <div className="pointer-events-none absolute -right-6 -top-6 h-28 w-28 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -bottom-8 left-10 h-24 w-24 rounded-full bg-pink-400/20" />

        <div className="relative flex items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/20 text-2xl font-black backdrop-blur-sm ring-1 ring-white/30">
            {initial}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wider text-white/70">Profile</p>
            <h1 className="truncate text-xl font-black">{firstName}</h1>
          </div>
        </div>

        <div className="relative mt-4 grid grid-cols-2 gap-2">
          <div className="rounded-2xl bg-white/15 px-3 py-2.5 backdrop-blur-sm ring-1 ring-white/20">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/70">Played</p>
            <p className="text-lg font-extrabold tabular-nums">{played}</p>
          </div>
          <div className="rounded-2xl bg-white/15 px-3 py-2.5 backdrop-blur-sm ring-1 ring-white/20">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/70">Wins</p>
            <p className="text-lg font-extrabold tabular-nums">{wins}</p>
          </div>
        </div>
      </div>

      {/* Wallet */}
      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-500/15 text-violet-700 dark:text-violet-300">
            <Wallet size={16} />
          </div>
          <h2 className="text-sm font-bold text-purple-900 dark:text-white">Wallet</h2>
        </div>

        <p className="text-3xl font-black tabular-nums text-purple-950 dark:text-white">
          {formatBalance(balance)}
          <span className="ml-1.5 text-base font-bold text-purple-400">ETB</span>
        </p>
        <p className="mt-1 text-xs text-purple-500 dark:text-purple-300">
          Board stake · {boardPrice} ETB each
        </p>
      </section>

      {/* Appearance */}
      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <ThemePreference />
      </section>

      {/* History */}
      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-orange-500/15 text-orange-600 dark:text-orange-300">
              <Trophy size={16} />
            </div>
            <h2 className="text-sm font-bold text-purple-900 dark:text-white">Recent games</h2>
          </div>

          {games && games.length > PAGE_SIZE && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                disabled={safePage <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-100 text-purple-700 transition disabled:opacity-35 dark:bg-white/10 dark:text-purple-200"
                aria-label="Previous page"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="min-w-[3rem] text-center text-[11px] font-bold tabular-nums text-purple-500 dark:text-purple-300">
                {safePage + 1}/{totalPages}
              </span>
              <button
                type="button"
                disabled={safePage >= totalPages - 1}
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-100 text-purple-700 transition disabled:opacity-35 dark:bg-white/10 dark:text-purple-200"
                aria-label="Next page"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </div>

        {error && <p className="py-4 text-center text-sm text-red-500">{error}</p>}

        {!error && games === null && (
          <div className="flex justify-center py-8">
            <Loader2 size={22} className="animate-spin text-purple-400" />
          </div>
        )}

        {!error && games && games.length === 0 && (
          <p className="py-6 text-center text-sm text-purple-500 dark:text-purple-300">
            No rounds yet — pick a board in Bingo to start playing.
          </p>
        )}

        {!error && games && games.length > 0 && (
          <ul className="flex flex-col gap-2">
            {pageRows.map((game) => (
              <li
                key={game.game_id}
                className="flex items-center justify-between gap-3 rounded-2xl bg-purple-50/80 px-3.5 py-3 dark:bg-white/5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold text-purple-900 dark:text-white">
                    #{game.game_id}
                  </p>
                  <p className="text-[11px] text-purple-500 dark:text-purple-300">
                    {game.boards_count} board{game.boards_count === 1 ? "" : "s"} · Stake{" "}
                    {Number(game.stake).toFixed(0)}
                  </p>
                  {game.created_at && (
                    <p className="text-[10px] text-purple-400">{formatWhen(game.created_at)}</p>
                  )}
                </div>
                <div className="shrink-0 text-right">
                  {game.is_winner ? (
                    <p className="text-sm font-extrabold text-green-600 dark:text-green-400">
                      +{Number(game.amount_won).toFixed(0)}
                    </p>
                  ) : (
                    <p className="text-sm font-semibold text-red-400">
                      -{Number(game.stake).toFixed(0)}
                    </p>
                  )}
                  <p className="text-[10px] text-purple-400">
                    Pot {Number(game.derash).toFixed(0)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
