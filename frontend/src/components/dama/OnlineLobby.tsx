import { useMemo, useState } from "react";
import { ArrowLeft, Search, Swords, UserRound, X } from "lucide-react";
import type { DamaChallenge, DamaOnlinePlayer } from "../../types/dama";
import type { WebSocketStatus } from "../../hooks/useWebSocket";
import { useI18n, type TranslationKey } from "../../i18n";
import { StakePicker, isValidDamaStake } from "./StakePicker";

interface OnlineLobbyProps {
  connectionStatus: WebSocketStatus;
  players: DamaOnlinePlayer[];
  selfUserId?: string;
  balance: string | null;
  stake: string;
  onStakeChange: (stake: string) => void;
  incoming: DamaChallenge | null;
  outgoing: DamaChallenge | null;
  error: string | null;
  onBack: () => void;
  onChallenge: (userId: string, stake: string) => void;
  onAccept: (challengeId: string) => void;
  onDecline: (challengeId: string) => void;
  onCancel: (challengeId: string) => void;
  onClearError: () => void;
}

function statusKey(status: DamaOnlinePlayer["status"]): TranslationKey {
  if (status === "idle") return "dama.available";
  if (status === "challenging") return "dama.challenging";
  return "dama.inGame";
}

export function OnlineLobby({
  connectionStatus,
  players,
  selfUserId,
  balance,
  stake,
  onStakeChange,
  incoming,
  outgoing,
  error,
  onBack,
  onChallenge,
  onAccept,
  onDecline,
  onCancel,
  onClearError,
}: OnlineLobbyProps) {
  const { t, ts } = useI18n();
  const [query, setQuery] = useState("");

  const others = useMemo(() => {
    const q = query.trim().toLowerCase();
    return players
      .filter((p) => !p.is_self && (!selfUserId || p.user_id !== selfUserId))
      .filter((p) => (q ? p.display_name.toLowerCase().includes(q) : true));
  }, [players, query, selfUserId]);

  const connected = connectionStatus === "open";
  const canAfford = isValidDamaStake(stake) && Number(balance) >= Number(stake);

  return (
    <div className="flex h-full flex-col overflow-hidden px-3 py-3 animate-[fadeIn_0.25s_ease-out]">
      <div className="mb-3 flex items-center gap-2">
        <button
          type="button"
          onClick={onBack}
          className="rounded-xl bg-white/80 p-2 text-purple-700 ring-1 ring-purple-100 dark:bg-white/10 dark:text-purple-200 dark:ring-white/10"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-extrabold text-purple-950 dark:text-white">
            {t("dama.onlinePlayers")}
          </h1>
          <p className="text-[11px] font-medium text-purple-500 dark:text-purple-300/75">
            {connected
              ? t("dama.onlineCount", { count: others.length })
              : t("common.connecting")}
          </p>
        </div>
      </div>

      <div className="mb-3 shrink-0">
        <StakePicker
          balance={balance}
          stake={stake}
          onStakeChange={onStakeChange}
          title={t("dama.matchStake")}
          subtitle={t("dama.matchStakeHint")}
        />
      </div>

      <label className="relative mb-3 block shrink-0">
        <Search
          size={15}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-purple-400"
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("dama.searchPlaceholder")}
          className="w-full rounded-2xl border-0 bg-white/90 py-2.5 pl-9 pr-3 text-sm font-medium text-purple-950 shadow-sm ring-1 ring-purple-100 outline-none placeholder:text-purple-300 focus:ring-2 focus:ring-orange-300 dark:bg-[#1E1B2E] dark:text-white dark:ring-white/10"
        />
      </label>

      {error && (
        <div className="mb-2 flex items-start justify-between gap-2 rounded-2xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 ring-1 ring-rose-100 dark:bg-rose-950/40 dark:text-rose-200 dark:ring-rose-900/50">
          <span>{ts(error)}</span>
          <button type="button" onClick={onClearError} aria-label={t("common.dismiss")}>
            <X size={14} />
          </button>
        </div>
      )}

      {incoming && (
        <div className="mb-3 shrink-0 rounded-2xl bg-gradient-to-r from-orange-500 to-amber-400 p-3 text-white shadow-md">
          <p className="text-xs font-semibold uppercase tracking-wide text-white/80">
            {t("dama.challengeStake", { stake: incoming.stake })}
          </p>
          <p className="mt-0.5 text-base font-extrabold">
            {t("dama.wantsToPlay", { name: incoming.from_name })}
          </p>
          <p className="mt-1 text-xs text-white/85">
            {t("dama.acceptStake", { stake: incoming.stake })}
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => onAccept(incoming.id)}
              className="flex-1 rounded-xl bg-white px-3 py-2 text-sm font-bold text-orange-700"
            >
              {t("common.accept")}
            </button>
            <button
              type="button"
              onClick={() => onDecline(incoming.id)}
              className="flex-1 rounded-xl bg-black/20 px-3 py-2 text-sm font-bold text-white"
            >
              {t("common.decline")}
            </button>
          </div>
        </div>
      )}

      {outgoing && (
        <div className="mb-3 shrink-0 rounded-2xl bg-white/90 p-3 shadow-sm ring-1 ring-violet-100 dark:bg-[#1E1B2E] dark:ring-white/10">
          <p className="text-sm font-bold text-purple-900 dark:text-white">
            {t("dama.waitingName", { name: outgoing.to_name })}
          </p>
          <p className="text-xs font-medium text-purple-500">
            {t("dama.stakeCharged", { stake: outgoing.stake })}
          </p>
          <button
            type="button"
            onClick={() => onCancel(outgoing.id)}
            className="mt-2 rounded-xl bg-purple-100 px-3 py-1.5 text-xs font-bold text-purple-800 dark:bg-white/10 dark:text-purple-100"
          >
            {t("dama.cancelChallenge")}
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto rounded-2xl bg-white/70 p-2 shadow-sm ring-1 ring-purple-100 dark:bg-[#1E1B2E]/80 dark:ring-white/10">
        {!connected ? (
          <p className="px-2 py-8 text-center text-sm font-medium text-purple-500">
            {t("dama.connectingLobby")}
          </p>
        ) : others.length === 0 ? (
          <p className="px-2 py-8 text-center text-sm font-medium text-purple-500">
            {query.trim() ? t("dama.noSearchMatch") : t("dama.noPlayersOnline")}
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {others.map((player) => {
              const canChallenge =
                player.status === "idle" &&
                !incoming &&
                !outgoing &&
                connected &&
                canAfford;
              return (
                <li
                  key={player.user_id}
                  className="flex items-center gap-2 rounded-xl bg-white/90 px-2.5 py-2 ring-1 ring-purple-50 dark:bg-white/5 dark:ring-white/5"
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white">
                    {player.photo_url ? (
                      <img
                        src={player.photo_url}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <UserRound size={18} />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-extrabold text-purple-950 dark:text-white">
                      {player.display_name}
                    </p>
                    <p
                      className={`text-[11px] font-semibold ${
                        player.status === "idle"
                          ? "text-emerald-600"
                          : "text-amber-600"
                      }`}
                    >
                      {t(statusKey(player.status))}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={!canChallenge}
                    onClick={() => onChallenge(player.user_id, stake)}
                    className="inline-flex items-center gap-1 rounded-xl bg-orange-500 px-2.5 py-1.5 text-xs font-bold text-white shadow disabled:opacity-40"
                  >
                    <Swords size={13} />
                    {stake}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
