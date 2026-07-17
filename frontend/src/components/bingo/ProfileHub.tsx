import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Crown, Loader2, Trophy, Wallet } from "lucide-react";
import { getBingoHistory } from "../../services/bingo";
import { getDamaHistory } from "../../services/dama";
import type { GameHistoryEntry } from "../../types/bingo";
import type { DamaHistoryEntry } from "../../types/dama";
import { useI18n } from "../../i18n";
import { LanguagePreference } from "./LanguagePreference";
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

export function ProfileHub({ firstName, balance, boardPrice }: ProfileHubProps) {
  const { t, formatDate } = useI18n();
  const [tab, setTab] = useState<HistoryTab>("bingo");
  const [bingoGames, setBingoGames] = useState<GameHistoryEntry[] | null>(null);
  const [damaGames, setDamaGames] = useState<DamaHistoryEntry[] | null>(null);
  const [bingoMeta, setBingoMeta] = useState({ total: 0, played: 0, wins: 0 });
  const [damaMeta, setDamaMeta] = useState({ total: 0, played: 0, wins: 0 });
  const [error, setError] = useState(false);
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
    setError(false);

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
          setError(true);
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
            <p className="text-xs font-semibold uppercase tracking-wider text-white/70">
              {t("profile.title")}
            </p>
            <h1 className="truncate text-xl font-black">{firstName}</h1>
          </div>
        </div>

        <div className="relative mt-4 grid grid-cols-2 gap-2">
          <div className="rounded-2xl bg-white/15 px-3 py-2.5 backdrop-blur-sm ring-1 ring-white/20">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/70">
              {tab === "bingo" ? t("profile.bingoPlayed") : t("profile.damaPlayed")}
            </p>
            <p className="text-lg font-extrabold tabular-nums">{meta.played}</p>
          </div>
          <div className="rounded-2xl bg-white/15 px-3 py-2.5 backdrop-blur-sm ring-1 ring-white/20">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/70">
              {t("profile.wins")}
            </p>
            <p className="text-lg font-extrabold tabular-nums">{meta.wins}</p>
          </div>
        </div>
      </div>

      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-500/15 text-violet-700 dark:text-violet-300">
            <Wallet size={16} />
          </div>
          <h2 className="text-sm font-bold text-purple-900 dark:text-white">{t("common.wallet")}</h2>
        </div>

        <p className="text-3xl font-black tabular-nums text-purple-950 dark:text-white">
          {formatBalance(balance)}
          <span className="ml-1.5 text-base font-bold text-purple-400">{t("common.etb")}</span>
        </p>
        <p className="mt-1 text-xs text-purple-500 dark:text-purple-300">
          {t("profile.walletHint", { price: boardPrice })}
        </p>
      </section>

      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <ThemePreference />
      </section>

      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <LanguagePreference />
      </section>

      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-orange-500/15 text-orange-600 dark:text-orange-300">
              <Trophy size={16} />
            </div>
            <h2 className="text-sm font-bold text-purple-900 dark:text-white">
              {t("profile.recentGames")}
            </h2>
          </div>

          {meta.total > PAGE_SIZE && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                disabled={page <= 0 || loading}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-100 text-purple-700 transition disabled:opacity-35 dark:bg-white/10 dark:text-purple-200"
                aria-label={t("profile.prevPage")}
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
                aria-label={t("profile.nextPage")}
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
            {t("nav.bingo")}
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
            {t("nav.dama")}
          </button>
        </div>

        {error && <p className="py-4 text-center text-sm text-red-500">{t("profile.historyError")}</p>}

        {!error && loading && (
          <div className="flex justify-center py-8">
            <Loader2 size={22} className="animate-spin text-purple-400" />
          </div>
        )}

        {!error && !loading && games && games.length === 0 && (
          <p className="py-6 text-center text-sm text-purple-500 dark:text-purple-300">
            {tab === "bingo" ? t("profile.noBingo") : t("profile.noDama")}
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
                      {t("profile.boardsStakePlayers", {
                        count: game.boards_count,
                        boards: game.boards_count,
                        stake: Number(game.stake).toFixed(0),
                        players: game.total_boards,
                      })}
                    </p>
                    {hasWinners ? (
                      <p className="truncate text-[11px] font-semibold text-orange-500 dark:text-orange-300">
                        {winnerNames.length > 0
                          ? t(winnerNames.length === 1 ? "profile.winnerNamed" : "profile.winnersNamed", {
                              names: winnerNames.join(", "),
                            })
                          : t("profile.winners")}
                        {" · "}
                        {t("profile.winnersTotal", { count: winnerCount })}
                      </p>
                    ) : (
                      <p className="text-[11px] text-purple-400">{t("profile.noWinner")}</p>
                    )}
                    <p className="text-[10px] text-purple-400">
                      {fee > 0
                        ? t("profile.potFeePrize", {
                            pot: Number.isFinite(gross) ? gross.toFixed(0) : game.derash,
                            fee: fee.toFixed(0),
                            prize: Number.isFinite(prize) ? prize.toFixed(0) : prize,
                          })
                        : t("profile.potOnly", {
                            pot: Number.isFinite(gross) ? gross.toFixed(0) : game.derash,
                          })}
                      {game.created_at
                        ? ` · ${formatDate(game.created_at, {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}`
                        : ""}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    {game.is_winner ? (
                      <>
                        <p className="text-sm font-extrabold text-green-600 dark:text-green-400">
                          +{Number.isFinite(wonAmount) ? wonAmount.toFixed(0) : game.amount_won}
                        </p>
                        <p className="text-[10px] font-medium text-green-600/80 dark:text-green-400/80">
                          {t("profile.netWin")}
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm font-semibold text-red-400">
                          -{Number(game.stake).toFixed(0)}
                        </p>
                        <p className="text-[10px] text-purple-400">
                          {t("profile.prizeAmount", {
                            prize: Number.isFinite(prize) ? prize.toFixed(0) : "—",
                          })}
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
                      {game.mode === "ai" ? t("profile.vsComputer") : t("profile.online")} ·{" "}
                      {t("common.stake")} {Number.isFinite(stake) ? stake.toFixed(0) : game.stake}{" "}
                      {t("common.etb")}
                    </p>
                    <p className="text-[10px] text-purple-400">
                      {Number(game.system_fee) > 0
                        ? t("profile.potFeePrize", {
                            pot: Number(game.pot).toFixed(0),
                            fee: Number(game.system_fee).toFixed(0),
                            prize: Number(game.prize_pool).toFixed(0),
                          })
                        : t("profile.potOnly", { pot: Number(game.pot).toFixed(0) })}
                      {game.created_at
                        ? ` · ${formatDate(game.created_at, {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}`
                        : ""}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    {game.outcome === "draw" ? (
                      <>
                        <p className="text-sm font-extrabold text-sky-600 dark:text-sky-300">
                          ±0
                        </p>
                        <p className="text-[10px] text-purple-400">{t("common.refund")}</p>
                      </>
                    ) : game.is_winner ? (
                      <>
                        <p className="text-sm font-extrabold text-green-600 dark:text-green-400">
                          +{Number.isFinite(wonAmount) ? wonAmount.toFixed(0) : game.amount_won}
                        </p>
                        <p className="text-[10px] font-medium text-green-600/80">{t("common.win")}</p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm font-semibold text-red-400">
                          -{Number.isFinite(stake) ? stake.toFixed(0) : game.stake}
                        </p>
                        <p className="text-[10px] text-purple-400">{t("common.loss")}</p>
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
