import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Crown, Loader2, Trophy, Wallet } from "lucide-react";
import { getBingoHistory } from "../../services/bingo";
import { getDamaHistory } from "../../services/dama";
import type { GameHistoryEntry } from "../../types/bingo";
import type { DamaHistoryEntry } from "../../types/dama";
import { ThemePreference } from "./ThemePreference";

const PAGE_SIZE = 10;

type HistoryTab = "bingo" | "dama";

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
  const [tab, setTab] = useState<HistoryTab>("bingo");
  const [bingoGames, setBingoGames] = useState<GameHistoryEntry[] | null>(null);
  const [damaGames, setDamaGames] = useState<DamaHistoryEntry[] | null>(null);
  const [bingoMeta, setBingoMeta] = useState({ total: 0, played: 0, wins: 0 });
  const [damaMeta, setDamaMeta] = useState({ total: 0, played: 0, wins: 0 });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);

  const meta = tab === "bingo" ? bingoMeta : damaMeta;
  const totalPages = Math.max(1, Math.ceil(meta.total / PAGE_SIZE));

  useEffect(() => {
    setPage(0);
  }, [tab]);

  useEffect(() => {
    if (page > totalPages - 1) {
      setPage(Math.max(0, totalPages - 1));
    }
  }, [page, totalPages]);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    const loader =
      tab === "bingo"
        ? getBingoHistory(PAGE_SIZE, page * PAGE_SIZE).then((payload) => {
            if (cancelled) return;
            setBingoGames(payload.games);
            setBingoMeta({
              total: payload.total,
              played: payload.played,
              wins: payload.wins,
            });
          })
        : getDamaHistory(PAGE_SIZE, page * PAGE_SIZE).then((payload) => {
            if (cancelled) return;
            setDamaGames(payload.games);
            setDamaMeta({
              total: payload.total,
              played: payload.played,
              wins: payload.wins,
            });
          });

    loader
      .catch(() => {
        if (!cancelled) {
          setError("Could not load your game history.");
          if (tab === "bingo") setBingoGames([]);
          else setDamaGames([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [page, tab]);

  const initial = (firstName.trim()[0] || "P").toUpperCase();
  const games = tab === "bingo" ? bingoGames : damaGames;

  return (
    <div className="flex flex-col gap-4 px-4 py-5 animate-[fadeIn_0.3s_ease-out]">
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
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/70">
              {tab === "bingo" ? "Bingo played" : "Dama played"}
            </p>
            <p className="text-lg font-extrabold tabular-nums">{meta.played}</p>
          </div>
          <div className="rounded-2xl bg-white/15 px-3 py-2.5 backdrop-blur-sm ring-1 ring-white/20">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/70">Wins</p>
            <p className="text-lg font-extrabold tabular-nums">{meta.wins}</p>
          </div>
        </div>
      </div>

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
          Bingo boards · {boardPrice} ETB · Dama stakes 5 / 10 / 15+
        </p>
      </section>

      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <ThemePreference />
      </section>

      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-orange-500/15 text-orange-600 dark:text-orange-300">
              <Trophy size={16} />
            </div>
            <h2 className="text-sm font-bold text-purple-900 dark:text-white">Recent games</h2>
          </div>

          {meta.total > PAGE_SIZE && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                disabled={page <= 0 || loading}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-100 text-purple-700 transition disabled:opacity-35 dark:bg-white/10 dark:text-purple-200"
                aria-label="Previous page"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="min-w-[3rem] text-center text-[11px] font-bold tabular-nums text-purple-500 dark:text-purple-300">
                {page + 1}/{totalPages}
              </span>
              <button
                type="button"
                disabled={page >= totalPages - 1 || loading}
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-100 text-purple-700 transition disabled:opacity-35 dark:bg-white/10 dark:text-purple-200"
                aria-label="Next page"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </div>

        <div className="mb-3 grid grid-cols-2 gap-1 rounded-2xl bg-purple-50 p-1 dark:bg-white/5">
          <button
            type="button"
            onClick={() => setTab("bingo")}
            className={`rounded-xl px-3 py-2 text-xs font-extrabold transition ${
              tab === "bingo"
                ? "bg-white text-purple-900 shadow dark:bg-[#2A2540] dark:text-white"
                : "text-purple-500"
            }`}
          >
            Bingo
          </button>
          <button
            type="button"
            onClick={() => setTab("dama")}
            className={`inline-flex items-center justify-center gap-1 rounded-xl px-3 py-2 text-xs font-extrabold transition ${
              tab === "dama"
                ? "bg-white text-purple-900 shadow dark:bg-[#2A2540] dark:text-white"
                : "text-purple-500"
            }`}
          >
            <Crown size={12} />
            Dama
          </button>
        </div>

        {error && <p className="py-4 text-center text-sm text-red-500">{error}</p>}

        {!error && loading && (
          <div className="flex justify-center py-8">
            <Loader2 size={22} className="animate-spin text-purple-400" />
          </div>
        )}

        {!error && !loading && games && games.length === 0 && (
          <p className="py-6 text-center text-sm text-purple-500 dark:text-purple-300">
            {tab === "bingo"
              ? "No Bingo rounds yet — pick a board to start."
              : "No Dama matches yet — stake vs computer or challenge online."}
          </p>
        )}

        {!error && !loading && tab === "bingo" && bingoGames && bingoGames.length > 0 && (
          <ul className="flex flex-col gap-2">
            {bingoGames.map((game) => {
              const winnerNames = game.winner_names ?? [];
              const winnerCount = game.winner_count ?? winnerNames.length;
              const hasWinners = winnerCount > 0 || winnerNames.length > 0;
              const gross = Number(game.derash);
              const fee = Number(game.system_fee ?? 0);
              const prize =
                game.prize_pool != null
                  ? Number(game.prize_pool)
                  : Number.isFinite(gross) && Number.isFinite(fee)
                    ? gross - fee
                    : gross;
              const wonAmount = Number(game.amount_won);

              return (
                <li
                  key={`${game.game_id}-${game.created_at ?? ""}`}
                  className="flex items-center justify-between gap-3 rounded-2xl bg-purple-50/80 px-3.5 py-3 dark:bg-white/5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-purple-900 dark:text-white">
                      #{game.game_id}
                    </p>
                    <p className="text-[11px] text-purple-500 dark:text-purple-300">
                      {game.boards_count} board{game.boards_count === 1 ? "" : "s"} · Stake{" "}
                      {Number(game.stake).toFixed(0)} · {game.total_boards} player
                      {game.total_boards === 1 ? "" : "s"}
                    </p>
                    {hasWinners ? (
                      <p className="truncate text-[11px] font-semibold text-orange-500 dark:text-orange-300">
                        {winnerNames.length > 0
                          ? `Winner${winnerNames.length === 1 ? "" : "s"}: ${winnerNames.join(", ")}`
                          : "Winners"}
                        {" · "}
                        {winnerCount} total
                      </p>
                    ) : (
                      <p className="text-[11px] text-purple-400">No winner</p>
                    )}
                    <p className="text-[10px] text-purple-400">
                      Pot {Number.isFinite(gross) ? gross.toFixed(0) : game.derash}
                      {fee > 0
                        ? ` · Fee -${fee.toFixed(0)} · Prize ${Number.isFinite(prize) ? prize.toFixed(0) : prize}`
                        : ""}
                      {game.created_at ? ` · ${formatWhen(game.created_at)}` : ""}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    {game.is_winner ? (
                      <>
                        <p className="text-sm font-extrabold text-green-600 dark:text-green-400">
                          +{Number.isFinite(wonAmount) ? wonAmount.toFixed(0) : game.amount_won}
                        </p>
                        <p className="text-[10px] font-medium text-green-600/80 dark:text-green-400/80">
                          net win
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm font-semibold text-red-400">
                          -{Number(game.stake).toFixed(0)}
                        </p>
                        <p className="text-[10px] text-purple-400">
                          Prize {Number.isFinite(prize) ? prize.toFixed(0) : "—"}
                        </p>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {!error && !loading && tab === "dama" && damaGames && damaGames.length > 0 && (
          <ul className="flex flex-col gap-2">
            {damaGames.map((game) => {
              const wonAmount = Number(game.amount_won);
              const stake = Number(game.stake);
              return (
                <li
                  key={`${game.game_id}-${game.created_at ?? ""}`}
                  className="flex items-center justify-between gap-3 rounded-2xl bg-orange-50/70 px-3.5 py-3 dark:bg-white/5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-purple-900 dark:text-white">
                      #{game.game_id}
                    </p>
                    <p className="text-[11px] text-purple-500 dark:text-purple-300">
                      {game.mode === "ai" ? "Vs Computer" : "Online"} · Stake{" "}
                      {Number.isFinite(stake) ? stake.toFixed(0) : game.stake} ETB
                    </p>
                    <p className="text-[10px] text-purple-400">
                      Pot {Number(game.pot).toFixed(0)}
                      {Number(game.system_fee) > 0
                        ? ` · Fee -${Number(game.system_fee).toFixed(0)} · Prize ${Number(game.prize_pool).toFixed(0)}`
                        : ""}
                      {game.created_at ? ` · ${formatWhen(game.created_at)}` : ""}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    {game.outcome === "draw" ? (
                      <>
                        <p className="text-sm font-extrabold text-sky-600 dark:text-sky-300">
                          ±0
                        </p>
                        <p className="text-[10px] text-purple-400">refund</p>
                      </>
                    ) : game.is_winner ? (
                      <>
                        <p className="text-sm font-extrabold text-green-600 dark:text-green-400">
                          +{Number.isFinite(wonAmount) ? wonAmount.toFixed(0) : game.amount_won}
                        </p>
                        <p className="text-[10px] font-medium text-green-600/80">win</p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm font-semibold text-red-400">
                          -{Number.isFinite(stake) ? stake.toFixed(0) : game.stake}
                        </p>
                        <p className="text-[10px] text-purple-400">loss</p>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
