import { useState } from "react";
import { Crown, Frown, Handshake, Sparkles, Trophy, WifiOff } from "lucide-react";
import { StakePicker } from "./StakePicker";

export type ResultKind = "win" | "loss" | "draw";

interface ResultOverlayProps {
  kind: ResultKind;
  title: string;
  subtitle: string;
  stake: string | null;
  prizePool?: string | null;
  balance: string | null;
  rematchStake: string;
  onRematchStakeChange: (stake: string) => void;
  /** Online: waiting for / offering rematch */
  rematchStatus?: "idle" | "offered_by_me" | "offered_by_them" | "peer_left" | null;
  onProposeRematch?: () => void;
  onAcceptRematch?: () => void;
  onClose: () => void;
  busy?: boolean;
}

export function ResultOverlay({
  kind,
  title,
  subtitle,
  stake,
  prizePool,
  balance,
  rematchStake,
  onRematchStakeChange,
  rematchStatus = "idle",
  onProposeRematch,
  onAcceptRematch,
  onClose,
  busy = false,
}: ResultOverlayProps) {
  const [showStake, setShowStake] = useState(false);

  const shell =
    kind === "win"
      ? "from-[#7C2D12] via-[#C2410C] to-[#F59E0B]"
      : kind === "loss"
        ? "from-[#1e1b4b] via-[#4c1d95] to-[#6d28d9]"
        : "from-[#0f766e] via-[#0d9488] to-[#2dd4bf]";

  const Icon = kind === "win" ? Trophy : kind === "loss" ? Frown : Handshake;
  const rematchAlert =
    rematchStatus === "offered_by_them" || rematchStatus === "offered_by_me";
  const peerLeft = rematchStatus === "peer_left";

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/50 p-3 backdrop-blur-sm sm:items-center">
      <div
        className={`w-full max-w-md overflow-hidden rounded-[28px] bg-white shadow-2xl dark:bg-[#16122A] ${
          rematchAlert
            ? "animate-[damaRematchGlow_1.4s_ease-in-out_infinite] ring-4 ring-orange-400 ring-offset-2 ring-offset-black/20 dark:ring-offset-[#0b0914]"
            : peerLeft
              ? "ring-4 ring-rose-400 ring-offset-2 ring-offset-black/20"
              : ""
        }`}
      >
        <div className={`relative bg-gradient-to-br ${shell} px-5 pb-8 pt-6 text-white`}>
          <div className="pointer-events-none absolute -right-8 -top-10 h-36 w-36 rounded-full bg-white/15 blur-2xl" />
          <div className="pointer-events-none absolute -bottom-10 left-8 h-28 w-28 rounded-full bg-black/10 blur-2xl" />
          <div className="relative flex flex-col items-center text-center">
            <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-3xl bg-white/20 ring-1 ring-white/35 backdrop-blur-sm">
              <Icon size={32} strokeWidth={2.2} />
            </div>
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-white/75">
              {kind === "win" ? "Victory" : kind === "loss" ? "Defeat" : "Draw"}
            </p>
            <h2 className="mt-1 text-2xl font-black leading-tight">{title}</h2>
            <p className="mt-1.5 max-w-xs text-sm font-medium text-white/90">{subtitle}</p>
            {(stake || prizePool) && (
              <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                {stake && (
                  <span className="rounded-full bg-black/20 px-3 py-1 text-xs font-bold">
                    Stake {stake} ETB
                  </span>
                )}
                {kind === "win" && prizePool && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-white/25 px-3 py-1 text-xs font-extrabold">
                    <Sparkles size={12} />
                    +{prizePool} ETB
                  </span>
                )}
                {kind === "draw" && stake && (
                  <span className="rounded-full bg-white/25 px-3 py-1 text-xs font-bold">
                    Stake refunded
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-3 px-4 py-4">
          {rematchStatus === "offered_by_them" && (
            <div className="rounded-2xl bg-orange-500 px-3 py-2.5 text-center text-sm font-extrabold text-white shadow animate-pulse">
              Rematch offer · {rematchStake} ETB — respond now
            </div>
          )}

          {peerLeft && (
            <div className="flex items-start gap-2 rounded-2xl bg-rose-50 px-3 py-3 text-sm font-bold text-rose-700 dark:bg-rose-950/50 dark:text-rose-200">
              <WifiOff size={18} className="mt-0.5 shrink-0" />
              <span>
                Opponent left this session. Your rematch offer was not delivered — find
                them again in the lobby when they return.
              </span>
            </div>
          )}

          {onProposeRematch && (
            <>
              <button
                type="button"
                onClick={() => setShowStake((v) => !v)}
                className="w-full rounded-2xl bg-purple-50 py-2 text-xs font-bold text-purple-700 dark:bg-white/5 dark:text-purple-200"
              >
                {showStake ? "Hide stake options" : `Rematch stake · ${rematchStake} ETB`}
              </button>
              {showStake && (
                <StakePicker
                  balance={balance}
                  stake={rematchStake}
                  onStakeChange={onRematchStakeChange}
                  title="Rematch stake"
                  subtitle="Both players must agree. You can change the amount."
                />
              )}
              {rematchStatus === "offered_by_them" && onAcceptRematch ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={onAcceptRematch}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-orange-500 py-3.5 text-sm font-extrabold text-white shadow ring-2 ring-orange-300 ring-offset-2 disabled:opacity-40 dark:ring-offset-[#16122A]"
                >
                  <Crown size={16} />
                  Accept rematch · {rematchStake} ETB
                </button>
              ) : rematchStatus === "offered_by_me" ? (
                <p className="rounded-2xl bg-amber-50 py-3 text-center text-xs font-bold text-amber-800 ring-2 ring-amber-300 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-600/50">
                  Rematch sent — waiting for opponent…
                </p>
              ) : (
                <button
                  type="button"
                  disabled={busy || Number(balance) < Number(rematchStake)}
                  onClick={onProposeRematch}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-orange-500 py-3.5 text-sm font-extrabold text-white shadow disabled:opacity-40"
                >
                  <Crown size={16} />
                  {peerLeft ? "Propose rematch again" : `Propose rematch · ${rematchStake} ETB`}
                </button>
              )}
            </>
          )}

          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-2xl bg-stone-100 py-3 text-sm font-bold text-stone-700 dark:bg-white/10 dark:text-purple-100"
          >
            Back to modes
          </button>
        </div>
      </div>

      <style>{`
        @keyframes damaRematchGlow {
          0%, 100% {
            box-shadow: 0 0 0 0 rgba(251, 146, 60, 0.55), 0 25px 50px -12px rgba(0,0,0,0.35);
          }
          50% {
            box-shadow: 0 0 0 10px rgba(251, 146, 60, 0.15), 0 25px 50px -12px rgba(0,0,0,0.35);
          }
        }
      `}</style>
    </div>
  );
}
