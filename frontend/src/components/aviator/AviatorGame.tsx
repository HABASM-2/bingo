import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Clock, LoaderCircle, Minus, Plus } from "lucide-react";
import { useAviator, AVIATOR_START_MULT } from "../../hooks/useAviator";
import type { AviatorBetRow, AviatorPhase } from "../../types/aviator";
import { getAviatorHistory } from "../../services/aviator";
import type { AviatorHistoryBet } from "../../services/aviator";
import { AviatorPlane } from "./AviatorPlane";
import { useI18n } from "../../i18n";

const QUICK_AMOUNTS = [1, 2, 5, 10] as const;
type BetsTab = "all" | "mine";

function pillColor(mult: number): string {
  if (mult >= 10) return "bg-fuchsia-600/90 text-white";
  if (mult >= 2) return "bg-purple-600/90 text-white";
  return "bg-sky-600/90 text-white";
}

function avatarColor(name: string): string {
  const hues = [210, 260, 320, 30, 160, 200];
  let h = 0;
  for (let i = 0; i < name.length; i++) h += name.charCodeAt(i);
  return `hsl(${hues[h % hues.length]} 65% 45%)`;
}

const CAM_W = 360;
const CAM_H = 200;
const ORIGIN_X = 5;
const ORIGIN_Y = CAM_H - 5;
const PLANE_BODY_ANGLE = -8;

function smoothstep(value: number): number {
  const t = Math.max(0, Math.min(1, value));
  return t * t * (3 - 2 * t);
}

interface FlightProfile {
  forwardPower: number;
  climbFinish: number;
  waveStart: number;
  waveAmplitude: number;
  waveCycles: number;
}

function flightProfileForRound(roundId?: string): FlightProfile {
  let hash = 2166136261;
  for (const char of roundId ?? "aviator") {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  const unit = (shift: number) => ((hash >>> shift) & 0xff) / 255;

  return {
    forwardPower: 1.12 + unit(0) * 0.3,
    climbFinish: 0.68 + unit(8) * 0.18,
    waveStart: 0.4 + unit(16) * 0.14,
    waveAmplitude: 10 + unit(4) * 10,
    waveCycles: 1.05 + unit(12) * 0.75,
  };
}

/**
 * Round-specific flight: natural takeoff followed by climb/descent cycles.
 * The graph and aircraft use this same function, so they never separate.
 */
function flightPosition(t: number, profile: FlightProfile): { x: number; y: number } {
  const clamped = Math.max(0, Math.min(1, t));
  const forward = 1 - Math.pow(1 - clamped, profile.forwardPower);
  const climb = smoothstep(clamped / profile.climbFinish);
  const waveBlend = smoothstep((clamped - profile.waveStart) / 0.18);
  const waveProgress = Math.max(0, clamped - profile.waveStart);
  const altitudeWave =
    Math.sin(waveProgress * Math.PI * 2 * profile.waveCycles) *
    profile.waveAmplitude *
    waveBlend;

  return {
    x: ORIGIN_X + (CAM_W * 0.86 - ORIGIN_X) * forward,
    y: ORIGIN_Y - (ORIGIN_Y - CAM_H * 0.2) * climb + altitudeWave,
  };
}

function cameraForFlight(x: number, y: number): { x: number; y: number } {
  // Do not move the camera during takeoff. Blend it in only as the aircraft
  // approaches the right side, then hold it slightly right of centre.
  const follow = smoothstep((x - CAM_W * 0.66) / (CAM_W * 0.14));
  const focusX = CAM_W * 0.62;
  const focusY = CAM_H * 0.47;

  return {
    x: Math.max(0, x - focusX) * follow,
    // Partial vertical tracking keeps the natural climb/bob visible.
    y: (y - focusY) * follow * 0.55,
  };
}

function cameraTransform(x: number, y: number): string {
  return `translate3d(${(-x / CAM_W) * 100}%, ${(-y / CAM_H) * 100}%, 0)`;
}

function buildCurvePath(t: number, profile: FlightProfile): string {
  const steps = Math.max(3, Math.ceil(t * 80));
  const pts: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const p = flightPosition((i / steps) * t, profile);
    pts.push(`${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`);
  }
  return pts.join(" ");
}

function buildAreaPath(t: number, profile: FlightProfile): string {
  const line = buildCurvePath(t, profile);
  const end = flightPosition(t, profile);
  return `${line} L ${end.x.toFixed(1)} ${ORIGIN_Y.toFixed(1)} L ${ORIGIN_X.toFixed(1)} ${ORIGIN_Y.toFixed(1)} Z`;
}

function progressForMult(mult: number): number {
  if (mult <= AVIATOR_START_MULT) return 0;
  // The path follows elapsed flight time, never the hidden crash point.
  // This prevents low-crash rounds from racing across the entire graph.
  const elapsed = Math.log(mult / AVIATOR_START_MULT) / 0.075;
  return Math.min(0.96, 1 - Math.exp(-elapsed / 11));
}

const MIN_CASHOUT_MULT = 1.01;
const BETTING_SECONDS = 5;
const HISTORY_PAGE_SIZE = 10;

interface AviatorGameProps {
  accessToken?: string;
  userId?: string;
  firstName?: string;
  walletBalance?: string | null;
  onBalanceChange?: (balance: string) => void;
  isActive?: boolean;
}

export function AviatorGame({
  accessToken = "",
  userId = "",
  walletBalance = null,
  onBalanceChange,
  isActive = true,
}: AviatorGameProps) {
  const { t, ts } = useI18n();
  const [betsTab, setBetsTab] = useState<BetsTab>("all");
  const [amount, setAmount] = useState(5);
  const [bettingLeft, setBettingLeft] = useState(0);
  const [pendingNextBet, setPendingNextBet] = useState(false);
  const [historyBets, setHistoryBets] = useState<AviatorHistoryBet[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const aviator = useAviator({
    token: accessToken || null,
    enabled: isActive && Boolean(accessToken),
    onBalance: onBalanceChange,
  });

  const displayBalance = aviator.balance ?? walletBalance;

  const phase: AviatorPhase = aviator.round?.phase ?? "waiting";
  const crash = aviator.round?.crash_multiplier ?? aviator.multiplier;
  const displayMult =
    phase === "crashed" ? crash : aviator.displayMultiplier;
  const progress =
    phase === "flying" || phase === "crashed" ? progressForMult(displayMult) : 0;

  const myBets = useMemo(
    () => (aviator.round?.bets ?? []).filter((b) => b.user_id === userId),
    [aviator.round?.bets, userId],
  );

  const flightProfile = useMemo(
    () => flightProfileForRound(aviator.round?.round_id),
    [aviator.round?.round_id],
  );

  useEffect(() => {
    if (phase !== "betting" || !aviator.round?.betting_ends_at) {
      setBettingLeft(0);
      return;
    }
    const tick = () => {
      setBettingLeft(Math.max(0, aviator.round!.betting_ends_at! - Date.now() / 1000));
    };
    tick();
    const id = window.setInterval(tick, 200);
    return () => clearInterval(id);
  }, [phase, aviator.round?.betting_ends_at]);

  // Auto-place a queued "next round" bet as soon as betting opens.
  useEffect(() => {
    if (!pendingNextBet) return;
    if (phase !== "betting" || bettingLeft <= 0) return;
    if (myBets.length > 0) {
      setPendingNextBet(false);
      return;
    }
    if (Number(displayBalance) < amount) {
      setPendingNextBet(false);
      return;
    }
    aviator.placeBet(String(amount), 0);
    setPendingNextBet(false);
  }, [pendingNextBet, phase, bettingLeft, myBets.length, displayBalance, amount, aviator.placeBet]);

  useEffect(() => {
    if (!isActive || betsTab !== "mine") return;

    let cancelled = false;
    setListLoading(true);
    setListError(null);

    const offset = historyPage * HISTORY_PAGE_SIZE;
    getAviatorHistory(HISTORY_PAGE_SIZE, offset)
      .then((data) => {
        if (cancelled) return;
        const maxPage = Math.max(0, Math.ceil(data.total / HISTORY_PAGE_SIZE) - 1);
        if (historyPage > maxPage) {
          setHistoryPage(maxPage);
          return;
        }
        setHistoryBets(data.bets);
        setHistoryTotal(data.total);
      })
      .catch(() => {
        if (!cancelled) setListError(t("aviator.listError"));
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [betsTab, isActive, historyPage, aviator.round?.round_id, t]);

  const historyPageCount = Math.max(1, Math.ceil(historyTotal / HISTORY_PAGE_SIZE));
  const historyFrom = historyTotal === 0 ? 0 : historyPage * HISTORY_PAGE_SIZE + 1;
  const historyTo = Math.min(historyTotal, (historyPage + 1) * HISTORY_PAGE_SIZE);

  const flightT = Math.min(progress, 0.998);
  const visualT = phase === "flying" ? Math.max(flightT, 0.012) : flightT;
  const rawPos = flightPosition(visualT, flightProfile);
  const camera = cameraForFlight(rawPos.x, rawPos.y);
  const isFlyingView = phase === "flying" || phase === "crashed";

  const playerCount = aviator.round?.player_count ?? 0;
  // After tab leave we clear round; show loader until the first reconnect snapshot.
  const awaitingRound = isActive && Boolean(accessToken) && aviator.round == null;

  if (awaitingRound) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center gap-3 bg-slate-100 text-slate-950 dark:bg-[#0b0e12] dark:text-white">
        <LoaderCircle
          className="h-8 w-8 animate-spin text-[#E50539]"
          aria-hidden
        />
        <p className="text-sm font-bold text-slate-600 dark:text-white/70">
          {t("common.connecting")}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-slate-100 text-slate-950 transition-colors duration-300 dark:bg-[#0b0e12] dark:text-white">
      <header className="flex shrink-0 items-center justify-between px-3 pb-1 pt-2">
        <h1 className="text-[1.65rem] font-black italic tracking-tight text-[#E50539]">
          {t("aviator.title")}
        </h1>
        <div className="flex items-center gap-1.5">
          <span className="rounded-lg bg-white px-2 py-1 text-[10px] font-bold tabular-nums text-slate-700 shadow-sm ring-1 ring-slate-200 dark:bg-white/10 dark:text-white/70 dark:shadow-none dark:ring-0">
            {displayBalance != null ? Number(displayBalance).toFixed(2) : "—"} {t("common.etb")}
          </span>
        </div>
      </header>

      {aviator.error && (
        <p className="mx-3 mb-1 rounded-lg bg-rose-100 px-2 py-1 text-center text-xs font-bold text-rose-700 dark:bg-rose-500/20 dark:text-rose-200">
          {ts(aviator.error)}
        </p>
      )}

      <div className="flex shrink-0 items-center gap-1.5 overflow-x-auto px-3 pb-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {(aviator.history.length ? aviator.history : [1.24, 1.43, 2.07]).map((h, i) => (
          <span
            key={`${h}-${i}`}
            className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-bold tabular-nums ${pillColor(h)}`}
          >
            {h.toFixed(2)}x
          </span>
        ))}
        <button type="button" className="shrink-0 rounded-md bg-white p-1 text-slate-500 shadow-sm ring-1 ring-slate-200 dark:bg-white/10 dark:text-white/60 dark:shadow-none dark:ring-0">
          <Clock size={14} />
        </button>
      </div>

      <div
        className="relative mx-3 shrink-0 overflow-hidden rounded-xl bg-slate-50 shadow-sm ring-1 ring-slate-200 dark:bg-[#0a0812] dark:shadow-none dark:ring-0"
        style={{ height: "min(58vw, 300px)", minHeight: 230 }}
      >
        <style>
          {`
            @keyframes aviator-fly-right {
              0% { transform: translate3d(0, 0, 0); opacity: 1; }
              100% { transform: translate3d(230px, -42px, 0); opacity: 0; }
            }
            @keyframes aviator-graph-clear {
              0% { opacity: 1; }
              100% { opacity: 0; }
            }
            .aviator-plane-exit {
              animation: aviator-fly-right 0.72s cubic-bezier(.35,.05,.75,.35) forwards;
            }
            .aviator-graph-clear {
              animation: aviator-graph-clear 0.68s ease-out forwards;
            }
            @keyframes aviator-ready-plane {
              0%, 14% { opacity: 0; transform: translate3d(-18px, 8px, 0); }
              30%, 100% { opacity: 1; transform: translate3d(0, 0, 0); }
            }
            .aviator-ready-plane {
              animation: aviator-ready-plane 0.8s ease-out forwards;
            }
            @keyframes aviator-progress-shine {
              from { transform: translateX(-120%); }
              to { transform: translateX(320%); }
            }
            .aviator-progress-shine {
              animation: aviator-progress-shine 1.15s ease-in-out infinite;
            }
          `}
        </style>
        {/* The backdrop is camera-independent, avoiding blank edges while following. */}
        <div
          className="absolute inset-0 bg-[repeating-conic-gradient(from_-8deg_at_0%_100%,#e2e8f0_0deg_6deg,#f8fafc_6deg_12deg)] dark:bg-[repeating-conic-gradient(from_-8deg_at_0%_100%,#221833_0deg_6deg,#120e1c_6deg_12deg)]"
        />
        <div
          className="absolute inset-0 bg-[radial-gradient(ellipse_70%_60%_at_50%_55%,rgba(244,63,94,0.10)_0%,transparent_70%)] dark:bg-[radial-gradient(ellipse_70%_60%_at_50%_55%,rgba(80,40,120,0.2)_0%,transparent_70%)]"
        />

        {/* Camera remains fixed for takeoff, then smoothly follows near the right edge. */}
        {isFlyingView && (
          <div
            className="absolute inset-0 will-change-transform"
            style={{ transform: cameraTransform(camera.x, camera.y) }}
          >
            <svg
              className="absolute inset-0 h-full w-full"
              preserveAspectRatio="none"
              viewBox={`0 0 ${CAM_W} ${CAM_H}`}
            >
              <defs>
                <linearGradient id="aviatorFill" x1="0" y1="1" x2="1" y2="0">
                  <stop offset="0%" stopColor="rgba(180,20,50,0.45)" />
                  <stop offset="100%" stopColor="rgba(229,5,57,0.12)" />
                </linearGradient>
                <filter id="curveGlow">
                  <feGaussianBlur stdDeviation="1.2" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              {visualT > 0.001 && (
                <g className={phase === "crashed" ? "aviator-graph-clear" : undefined}>
                  <path d={buildAreaPath(visualT, flightProfile)} fill="url(#aviatorFill)" />
                  <path
                    d={buildCurvePath(visualT, flightProfile)}
                    fill="none"
                    stroke="#E50539"
                    strokeWidth="3.75"
                    strokeLinecap="round"
                    filter="url(#curveGlow)"
                  />
                </g>
              )}
            </svg>

            {phase === "flying" || visualT > 0.001 ? (
              <div
                className="absolute pointer-events-none"
                style={{
                  left: `${(rawPos.x / CAM_W) * 100}%`,
                  top: `${(rawPos.y / CAM_H) * 100}%`,
                  // The graph endpoint is the aircraft's tail anchor.
                  transform: `translate(-14%, -58%) rotate(${PLANE_BODY_ANGLE}deg)`,
                  width: "30%",
                  minWidth: 88,
                  maxWidth: 132,
                }}
              >
                <div className={phase === "crashed" ? "aviator-plane-exit" : undefined}>
                  <AviatorPlane className="h-auto w-full drop-shadow-[0_2px_8px_rgba(229,5,57,0.5)]" />
                </div>
              </div>
            ) : null}
          </div>
        )}

        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-slate-200/70 via-transparent to-transparent dark:from-[#0a0812]/70" />

        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-10">
          {phase === "betting" ? (
            <div className="flex w-[72%] flex-col items-center">
              <p className="text-base font-extrabold uppercase tracking-[0.2em] text-slate-700 dark:text-white/85">
                {t("aviator.nextRoundIn")}
              </p>
              <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-slate-300/80 p-[2px] ring-1 ring-slate-400/30 shadow-[0_0_18px_rgba(229,5,57,0.15)] dark:bg-black/45 dark:ring-white/15">
                <div
                  className="relative h-full origin-left overflow-hidden rounded-full bg-gradient-to-r from-[#9e0329] via-[#E50539] to-[#ff4b70] will-change-transform"
                  style={{
                    transform: `scaleX(${Math.max(0, Math.min(1, bettingLeft / BETTING_SECONDS))})`,
                    transition: "transform 50ms linear",
                  }}
                >
                  <span className="aviator-progress-shine absolute inset-y-0 left-0 w-1/3 skew-x-[-22deg] bg-gradient-to-r from-transparent via-white/65 to-transparent" />
                </div>
              </div>
            </div>
          ) : (
            <>
              {phase === "crashed" && (
                <p className="mb-1 text-base font-extrabold uppercase tracking-[0.12em] text-[#E50539]">
                  {t("aviator.flewAway")}
                </p>
              )}
              <p
                className={`font-black tabular-nums leading-none tracking-tight ${
                  phase === "flying"
                    ? "text-[3.25rem] text-slate-950 drop-shadow-[0_0_20px_rgba(255,255,255,0.8)] dark:text-white dark:drop-shadow-[0_0_24px_rgba(255,255,255,0.15)]"
                    : phase === "crashed"
                      ? "text-[2.75rem] text-[#E50539]"
                      : "hidden"
                }`}
              >
                {displayMult.toFixed(2)}x
              </p>
              {phase === "flying" && playerCount > 0 && (
                <p className="mt-1 text-[10px] font-semibold text-slate-500 dark:text-white/40">
                  {t("aviator.playersInRound", { count: playerCount })}
                </p>
              )}
            </>
          )}
        </div>

        {phase === "betting" && (
          <div className="aviator-ready-plane absolute -bottom-3 left-1 z-20 w-[30%] min-w-[88px] max-w-[132px] pointer-events-none">
            <AviatorPlane className="h-auto w-full drop-shadow-[0_2px_8px_rgba(229,5,57,0.45)]" />
          </div>
        )}
      </div>

      <div className="mx-3 mt-2 shrink-0 rounded-xl bg-white shadow-sm ring-1 ring-slate-200 dark:bg-[#141820] dark:shadow-none dark:ring-white/5">
        <div className="p-2.5">
          <BetSlot
            amount={amount}
            onAmount={setAmount}
            phase={phase}
            bettingLeft={bettingLeft}
            myBet={myBets.find((b) => b.slot === 0) ?? myBets[0]}
            multiplier={aviator.displayMultiplier}
            balance={displayBalance}
            pendingNextBet={pendingNextBet}
            pendingAction={aviator.pendingAction}
            onBet={() => {
              setPendingNextBet(false);
              aviator.placeBet(String(amount), 0);
            }}
            onCashOut={() => aviator.cashOut(0)}
            onQueueNextRound={() => setPendingNextBet(true)}
            onCancelNextRound={() => setPendingNextBet(false)}
          />
        </div>
      </div>

      <div className="mt-2 flex min-h-0 flex-1 flex-col border-t border-slate-200 bg-white/70 dark:border-white/5 dark:bg-[#0d1015]">
        <div className="flex shrink-0 border-b border-slate-200 dark:border-white/5">
          {(
            [
              ["all", t("aviator.allBets", { count: aviator.round?.bets.length ?? 0 })],
              ["mine", t("aviator.myBets")],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => {
                setBetsTab(id);
                if (id === "mine") setHistoryPage(0);
              }}
              className={`flex-1 py-2.5 text-[11px] font-bold uppercase tracking-wide ${
                betsTab === id ? "border-b-2 border-[#28a909] text-slate-950 dark:text-white" : "text-slate-500 dark:text-white/40"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          {listLoading && betsTab !== "all" ? (
            <p className="py-6 text-center text-xs text-slate-500 dark:text-white/35">{t("common.loadingEllipsis")}</p>
          ) : listError && betsTab !== "all" ? (
            <p className="py-6 text-center text-xs text-rose-600 dark:text-rose-300/80">{listError}</p>
          ) : betsTab === "all" && (aviator.round?.bets.length ?? 0) === 0 ? (
            <p className="py-6 text-center text-xs text-slate-500 dark:text-white/35">{t("aviator.noBetsRound")}</p>
          ) : betsTab === "mine" && historyBets.length === 0 ? (
            <p className="py-6 text-center text-xs text-slate-500 dark:text-white/35">{t("aviator.noHistory")}</p>
          ) : betsTab === "all" ? (
            <ul className="space-y-0.5">
              {(aviator.round?.bets ?? []).map((bet) => (
                <BetRowItem
                  key={bet.bet_id}
                  bet={bet}
                  isYou={bet.user_id === userId}
                  compact={(aviator.round?.bets.length ?? 0) > 8}
                />
              ))}
            </ul>
          ) : (
            <>
              <ul className="space-y-1">
                {historyBets.map((bet) => (
                  <HistoryBetItem key={bet.bet_id} bet={bet} />
                ))}
              </ul>
              {historyTotal > HISTORY_PAGE_SIZE ? (
                <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-200 pt-2 dark:border-white/5">
                  <button
                    type="button"
                    disabled={historyPage <= 0 || listLoading}
                    onClick={() => setHistoryPage((p) => Math.max(0, p - 1))}
                    className="flex items-center gap-0.5 rounded-md px-2 py-1.5 text-[11px] font-semibold text-slate-700 disabled:opacity-30 dark:text-white/70"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                    {t("common.prev")}
                  </button>
                  <span className="text-[10px] tabular-nums text-slate-500 dark:text-white/45">
                    {historyFrom}–{historyTo} / {historyTotal}
                    <span className="text-slate-300 dark:text-white/25"> · </span>
                    {historyPage + 1}/{historyPageCount}
                  </span>
                  <button
                    type="button"
                    disabled={historyPage + 1 >= historyPageCount || listLoading}
                    onClick={() => setHistoryPage((p) => p + 1)}
                    className="flex items-center gap-0.5 rounded-md px-2 py-1.5 text-[11px] font-semibold text-slate-700 disabled:opacity-30 dark:text-white/70"
                  >
                    {t("common.next")}
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function BetRowItem({
  bet,
  isYou,
  compact,
}: {
  bet: AviatorBetRow;
  isYou: boolean;
  compact: boolean;
}) {
  const { t } = useI18n();
  return (
    <li
      className={`flex items-center gap-2 rounded-lg px-1.5 py-1.5 ${
        isYou ? "bg-emerald-50 ring-1 ring-[#28a909]/30 dark:bg-white/5" : ""
      }`}
    >
      <span
        className={`flex shrink-0 items-center justify-center rounded-full font-bold text-white ${
          compact ? "h-6 w-6 text-[10px]" : "h-8 w-8 text-xs"
        }`}
        style={{ background: avatarColor(bet.display_name) }}
      >
        {bet.display_name.slice(0, 1).toUpperCase()}
      </span>
      <span className={`min-w-0 flex-1 truncate font-semibold ${isYou ? "text-emerald-700 dark:text-emerald-300" : "text-slate-800 dark:text-white/80"} ${compact ? "text-xs" : "text-sm"}`}>
        {isYou ? t("common.you") : bet.display_name}
      </span>
      <div className={`shrink-0 text-right tabular-nums ${compact ? "text-[10px]" : "text-xs"}`}>
        <span className="text-slate-500 dark:text-white/55">{Number(bet.stake).toFixed(2)}</span>
        {bet.status === "cashed" && bet.cashout_at != null ? (
          <>
            <span className="text-slate-300 dark:text-white/25"> · </span>
            <span className="font-bold text-emerald-400">{bet.cashout_at.toFixed(2)}x</span>
            <span className="text-slate-300 dark:text-white/25"> · </span>
            <span className="font-bold text-slate-950 dark:text-white">{Number(bet.win).toFixed(2)}</span>
          </>
        ) : bet.status === "lost" ? (
          <span className="text-rose-400/80"> · —</span>
        ) : (
          <span className="text-slate-300 dark:text-white/25"> · …</span>
        )}
      </div>
    </li>
  );
}

function HistoryBetItem({ bet }: { bet: AviatorHistoryBet }) {
  const { t, formatDate } = useI18n();
  const won = bet.outcome === "won";
  const when = bet.created_at
    ? formatDate(bet.created_at, {
        month: "short",
        day: "numeric",
      })
    : "";

  return (
    <li className="flex items-center gap-2 rounded-lg bg-slate-100 px-2 py-2 dark:bg-white/[0.03]">
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-black ${
          won ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300" : "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300"
        }`}
      >
        {won ? "W" : "L"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-bold text-slate-800 dark:text-white/80">
          {bet.round_code || t("aviator.roundLabel")}
        </p>
        <p className="text-[10px] text-slate-500 dark:text-white/35">
          {t("aviator.crashedAt", { when, mult: Number(bet.crash_multiplier ?? 1).toFixed(2) })}
        </p>
      </div>
      <div className="shrink-0 text-right text-xs tabular-nums">
        <p className="text-slate-500 dark:text-white/55">{Number(bet.stake).toFixed(2)} {t("common.etb")}</p>
        <p className={won ? "font-bold text-emerald-400" : "font-bold text-rose-400"}>
          {won
            ? `${Number(bet.cashout_multiplier).toFixed(2)}x · ${Number(bet.amount_won).toFixed(2)}`
            : t("aviator.lost")}
        </p>
      </div>
    </li>
  );
}

function BetSlot({
  amount,
  onAmount,
  phase,
  bettingLeft,
  myBet,
  multiplier,
  balance,
  pendingNextBet,
  pendingAction,
  onBet,
  onCashOut,
  onQueueNextRound,
  onCancelNextRound,
}: {
  amount: number;
  onAmount: (n: number) => void;
  phase: AviatorPhase;
  bettingLeft: number;
  myBet?: AviatorBetRow;
  multiplier: number;
  balance: string | null;
  pendingNextBet: boolean;
  pendingAction: "bet" | "cashout" | null;
  onBet: () => void;
  onCashOut: () => void;
  onQueueNextRound: () => void;
  onCancelNextRound: () => void;
}) {
  const { t } = useI18n();
  const active = myBet?.status === "active";
  const cashed = myBet?.status === "cashed";
  const canBet = !myBet && phase === "betting" && bettingLeft > 0;
  const canCashOut = active && phase === "flying" && multiplier >= MIN_CASHOUT_MULT;
  const canQueueNext =
    !active &&
    !pendingNextBet &&
    (phase === "flying" || phase === "crashed" || phase === "waiting");
  const isLoading = pendingAction !== null || pendingNextBet;
  const stake = Number(myBet?.stake ?? amount);
  const potential = active ? stake * multiplier : null;

  let label = t("aviator.bet");
  if (canCashOut) label = t("aviator.cashOut");
  else if (pendingNextBet) label = t("aviator.cancelNext");
  else if (canQueueNext) label = t("aviator.nextRound");
  else if (phase === "betting" && bettingLeft <= 0) label = t("aviator.wait");
  else if (active && phase === "flying") label = t("aviator.inPlay");

  const disabled =
    pendingAction !== null ||
    (active && phase === "flying" && !canCashOut) ||
    (!canBet && !canCashOut && !canQueueNext && !pendingNextBet) ||
    (canBet && Number(balance) < amount) ||
    (canQueueNext && Number(balance) < amount);

  return (
    <div className="rounded-lg bg-slate-100 p-2 ring-1 ring-slate-200 dark:bg-[#1c2230] dark:ring-0">
      <div className="flex items-center gap-1">
        <button type="button" disabled={active || isLoading} onClick={() => onAmount(Math.max(1, amount - 1))} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-slate-600 ring-1 ring-slate-200 disabled:opacity-35 dark:bg-[#0f1318] dark:text-white/70 dark:ring-white/10">
          <Minus size={16} />
        </button>
        <div className={`flex-1 rounded-lg bg-white py-2 text-center ring-1 ring-slate-200 dark:bg-[#0f1318] dark:ring-white/10 ${active || isLoading ? "opacity-50" : ""}`}>
          <span className="text-lg font-bold tabular-nums">{amount.toFixed(2)}</span>
        </div>
        <button type="button" disabled={active || isLoading} onClick={() => onAmount(amount + 1)} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-slate-600 ring-1 ring-slate-200 disabled:opacity-35 dark:bg-[#0f1318] dark:text-white/70 dark:ring-white/10">
          <Plus size={16} />
        </button>
      </div>
      <div className="mt-1.5 flex gap-1">
        {QUICK_AMOUNTS.map((q) => (
          <button key={q} type="button" disabled={active || isLoading} onClick={() => onAmount(q)} className="flex-1 rounded-md bg-white py-1 text-[10px] font-bold text-slate-600 ring-1 ring-slate-200 disabled:opacity-35 dark:bg-[#0f1318] dark:text-white/50 dark:ring-white/5">
            {q}
          </button>
        ))}
      </div>
      {cashed && (
        <div className="mt-2 flex items-center justify-between rounded-lg bg-emerald-500/10 px-2.5 py-1.5 text-[11px] opacity-60 ring-1 ring-emerald-400/20">
          <span className="font-bold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
            {t("aviator.cashedOut")}
          </span>
          <span className="tabular-nums text-emerald-600 dark:text-emerald-200">
            {myBet?.cashout_at?.toFixed(2)}x · {Number(myBet?.win ?? 0).toFixed(2)} {t("common.etb")}
          </span>
        </div>
      )}
      <button
        type="button"
        disabled={disabled}
        aria-busy={isLoading}
        onClick={() => {
          if (canCashOut) onCashOut();
          else if (canBet) onBet();
          else if (pendingNextBet) onCancelNextRound();
          else if (canQueueNext) onQueueNextRound();
        }}
        className={`mt-2 w-full rounded-xl py-3 text-sm font-extrabold uppercase tracking-wide shadow-lg disabled:opacity-50 ${
          canCashOut
            ? "bg-[#d97706] text-white"
            : pendingNextBet
                ? "bg-[#1c3a5f] text-sky-200"
                : "bg-[#28a909] text-white"
        }`}
      >
        <span className="flex items-center justify-center gap-2">
          {isLoading && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {pendingAction === "bet"
            ? t("aviator.placingBet")
            : pendingAction === "cashout"
              ? t("aviator.cashingOut")
              : canCashOut && potential != null
                ? t("aviator.cashOutAmount", { amount: potential.toFixed(2) })
                : label}
        </span>
      </button>
    </div>
  );
}
