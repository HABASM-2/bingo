import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  History,
  Loader2,
  RotateCw,
  ShieldCheck,
  Sparkles,
  Users,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useWebSocket } from "../../hooks/useWebSocket";
import {
  getLottoHistory,
  getLottoSnapshot,
  lottoWebSocketUrl,
  reserveLotto,
} from "../../services/lotto";
import type {
  LottoHistoryPage,
  LottoRoom,
  LottoSnapshot,
  LottoWinner,
} from "../../services/lotto";
import { useI18n, tGlobal } from "../../i18n";

export interface LottoSpinGameProps {
  isActive?: boolean;
  accessToken: string;
  userId: string;
  firstName: string;
  walletBalance: string | null;
  onBalanceChange: (balance: string) => void;
}

type ServerMessage =
  | LottoSnapshot
  | { type: "room_updated"; room: LottoRoom; server_time: string }
  | { type: "rooms_updated"; rooms: LottoRoom[]; server_time: string }
  | { type: "wallet"; balance: string }
  | { type: "ping" | "pong" };

type SpinPhase = "idle" | "anticipation" | "spinning" | "settled";

const STAKES = [10, 25, 50, 100] as const;
const CAPACITY = 25;
const SEGMENT = 360 / CAPACITY;
const COLORS = [
  "#0f766e", "#1d4ed8", "#be123c", "#b45309", "#047857",
  "#4338ca", "#9f1239", "#0369a1", "#a16207", "#15803d",
  "#1e40af", "#be123c", "#a21caf", "#047857", "#b45309",
  "#1d4ed8", "#9f1239", "#0f766e", "#7e22ce", "#c2410c",
  "#0e7490", "#b91c1c", "#4d7c0f", "#6d28d9", "#c2410c",
] as const;
const PAGE_SIZE = 10;

/** Premium spin pacing (ms). Rank 1 is longest; reduced-motion halves durations. */
const SPIN_PACING = {
  1: { anticipation: 1200, spin: 6500, gap: 2600, turns: 8 },
  2: { anticipation: 1000, spin: 5500, gap: 2400, turns: 7 },
  3: { anticipation: 900, spin: 4800, gap: 2200, turns: 6 },
} as const;

const SPIN_EASING = "cubic-bezier(0.12, 0.75, 0.08, 1)";
const CONTESTED_SELECTION_MSG_KEY = "lotto.numbersTaken" as const;

const money = (value: string | number) =>
  Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const polar = (angle: number, radius: number) => {
  const radians = (angle * Math.PI) / 180;
  return { x: 150 + Math.cos(radians) * radius, y: 160 + Math.sin(radians) * radius };
};

const segmentPath = (index: number) => {
  const start = -90 - SEGMENT / 2 + index * SEGMENT;
  const a = polar(start, 132);
  const b = polar(start + SEGMENT, 132);
  return `M 150 160 L ${a.x} ${a.y} A 132 132 0 0 1 ${b.x} ${b.y} Z`;
};

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const rankLabel = (rank: number) =>
  tGlobal(
    rank === 1
      ? "lotto.prize1"
      : rank === 2
        ? "lotto.prize2"
        : rank === 3
          ? "lotto.prize3"
          : "lotto.prize",
  );

const winnerAngle = (number: number) =>
  ((-(number - 1) * SEGMENT) % 360 + 360) % 360;

function playWinnerTone(enabled: boolean) {
  if (!enabled) return;
  try {
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.setValueAtTime(620, context.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(900, context.currentTime + 0.25);
    gain.gain.setValueAtTime(0.06, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.4);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.42);
    oscillator.addEventListener("ended", () => void context.close());
  } catch { /* optional audio */ }
}

function pruneUnavailable(
  selected: number[],
  room: LottoRoom,
  submittingNumbers: ReadonlySet<number> | null,
): number[] {
  if (room.status !== "open") return [];
  const reserved = new Map(room.reservations.map((item) => [item.number, item.user_id]));
  return selected.filter((number) => {
    if (submittingNumbers?.has(number)) return true;
    return !reserved.has(number);
  });
}

function parseContestedNumbers(detail: string | undefined): number[] {
  if (!detail) return [];
  const match = detail.match(/Number\(s\) already reserved:\s*([\d,\s]+)/i);
  if (!match) return [];
  return match[1]
    .split(",")
    .map((part) => Number(part.trim()))
    .filter((value) => Number.isInteger(value) && value >= 1 && value <= CAPACITY);
}

export function LottoSpinGame({
  isActive = true,
  accessToken,
  userId,
  firstName,
  walletBalance,
  onBalanceChange,
}: LottoSpinGameProps) {
  const { t, ts } = useI18n();
  const [rooms, setRooms] = useState<Record<number, LottoRoom>>({});
  const [activeStake, setActiveStake] = useState(10);
  const [selected, setSelected] = useState<number[]>([]);
  const [view, setView] = useState<"game" | "history">("game");
  const [history, setHistory] = useState<LottoHistoryPage | null>(null);
  const [historyPage, setHistoryPage] = useState(0);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [soundOn, setSoundOn] = useState(true);
  const [rotation, setRotation] = useState(0);
  const [spinPhase, setSpinPhase] = useState<SpinPhase>("idle");
  const [spinMs, setSpinMs] = useState<number>(SPIN_PACING[1].spin);
  const [drawNotice, setDrawNotice] = useState<string | null>(null);
  const [displayWinner, setDisplayWinner] = useState<LottoWinner | null>(null);
  const [now, setNow] = useState(Date.now());

  const previousRoundRef = useRef<Record<number, string>>({});
  const animatedRanksRef = useRef<Record<string, number>>({});
  const animatingRankRef = useRef<{ roomId: string; rank: number } | null>(null);
  const rotationRef = useRef(0);
  const activeStakeRef = useRef(activeStake);
  const isActiveRef = useRef(isActive);
  const soundOnRef = useRef(soundOn);
  const spinPhaseRef = useRef<SpinPhase>("idle");
  const submittingNumbersRef = useRef<Set<number> | null>(null);
  const spinChainIdRef = useRef(0);
  const timersRef = useRef<number[]>([]);
  const reducedMotionRef = useRef(false);

  activeStakeRef.current = activeStake;
  isActiveRef.current = isActive;
  soundOnRef.current = soundOn;
  spinPhaseRef.current = spinPhase;

  /** Record revealed winners without running wheel ceremony (background rooms / inactive tab). */
  const markRevealsApplied = useCallback((room: LottoRoom) => {
    if (!room.winners.length) return;
    const maxRank = Math.max(...room.winners.map((winner) => winner.rank));
    animatedRanksRef.current[room.id] = Math.max(
      animatedRanksRef.current[room.id] ?? 0,
      maxRank,
    );
  }, []);

  const clearSpinTimers = useCallback(() => {
    for (const id of timersRef.current) window.clearTimeout(id);
    timersRef.current = [];
  }, []);

  const schedule = useCallback((fn: () => void, ms: number) => {
    const id = window.setTimeout(fn, ms);
    timersRef.current.push(id);
    return id;
  }, []);

  const snapWheelToNumber = useCallback((number: number) => {
    const normalized = ((rotationRef.current % 360) + 360) % 360;
    const desired = winnerAngle(number);
    const next = rotationRef.current + ((desired - normalized + 360) % 360);
    rotationRef.current = next;
    setSpinMs(0);
    setRotation(next);
  }, []);

  const runWinnerReveal = useCallback((
    roomId: string,
    winner: LottoWinner,
    chainId: number,
  ) => {
    const pacing = SPIN_PACING[winner.rank as 1 | 2 | 3] ?? SPIN_PACING[3];
    const scale = reducedMotionRef.current ? 0.45 : 1;
    const anticipation = Math.max(400, Math.round(pacing.anticipation * scale));
    const duration = Math.max(1800, Math.round(pacing.spin * scale));
    const gap = Math.max(900, Math.round(pacing.gap * scale));
    const turns = reducedMotionRef.current ? Math.max(3, pacing.turns - 3) : pacing.turns;

    animatingRankRef.current = { roomId, rank: winner.rank };
    setDisplayWinner(null);
    setDrawNotice(tGlobal("lotto.drawing", { rank: rankLabel(winner.rank) }));
    setSpinPhase("anticipation");

    schedule(() => {
      if (spinChainIdRef.current !== chainId) return;
      const normalized = ((rotationRef.current % 360) + 360) % 360;
      const desired = winnerAngle(winner.number);
      const next = rotationRef.current + turns * 360 + ((desired - normalized + 360) % 360);
      rotationRef.current = next;
      setSpinMs(duration);
      setSpinPhase("spinning");
      setDrawNotice(null);
      setRotation(next);

      schedule(() => {
        if (spinChainIdRef.current !== chainId) return;
        setSpinPhase("settled");
        setDisplayWinner(winner);
        playWinnerTone(soundOnRef.current);
        animatedRanksRef.current[roomId] = Math.max(
          animatedRanksRef.current[roomId] ?? 0,
          winner.rank,
        );
        animatingRankRef.current = null;

        schedule(() => {
          if (spinChainIdRef.current !== chainId) return;
          setSpinPhase("idle");
        }, gap);
      }, duration);
    }, anticipation);
  }, [schedule]);

  const syncSpinFromRoom = useCallback((room: LottoRoom) => {
    const stake = Number(room.stake);
    if (stake !== activeStakeRef.current) {
      markRevealsApplied(room);
      return;
    }

    // Tab hidden / another app screen: keep logical reveals, skip ceremony.
    if (!isActiveRef.current) {
      markRevealsApplied(room);
      if (room.winners.length) {
        const latest = room.winners[room.winners.length - 1];
        setDisplayWinner(latest);
        snapWheelToNumber(latest.number);
        setSpinPhase("idle");
        setDrawNotice(null);
      } else if (room.status === "open" || room.status === "countdown") {
        setDisplayWinner(null);
        setDrawNotice(null);
      }
      return;
    }

    const winners = room.winners;
    if (!winners.length) {
      if (room.status === "open" || room.status === "countdown") {
        setDisplayWinner(null);
        setDrawNotice(null);
      }
      return;
    }

    const already = animatedRanksRef.current[room.id] ?? 0;
    const animating =
      animatingRankRef.current?.roomId === room.id
        ? animatingRankRef.current.rank
        : 0;
    const covered = Math.max(already, animating);
    const latest = winners[winners.length - 1];

    // Ceremony already running or finished for this rank — do not restart.
    if (latest.rank <= covered) {
      const phase = spinPhaseRef.current;
      if (phase === "idle" && already >= latest.rank) {
        setDisplayWinner(latest);
        snapWheelToNumber(latest.number);
      }
      return;
    }

    // Catch-up: snap past older unplayed ranks; animate only the newest.
    for (const winner of winners) {
      if (winner.rank <= covered) continue;
      if (winner.rank < latest.rank) {
        animatedRanksRef.current[room.id] = winner.rank;
        snapWheelToNumber(winner.number);
        continue;
      }

      const revealedAt = winner.revealed_at
        ? new Date(winner.revealed_at).getTime()
        : Date.now();
      const age = Date.now() - revealedAt;
      const pacing = SPIN_PACING[winner.rank as 1 | 2 | 3] ?? SPIN_PACING[3];
      const ceremonyBudget = pacing.anticipation + pacing.spin + pacing.gap;
      // Too late for full ceremony (reconnect / backgrounded tab).
      if (age > ceremonyBudget + 500) {
        animatedRanksRef.current[room.id] = winner.rank;
        animatingRankRef.current = null;
        setDisplayWinner(winner);
        snapWheelToNumber(winner.number);
        setSpinPhase("idle");
        setDrawNotice(null);
        return;
      }

      clearSpinTimers();
      const chainId = ++spinChainIdRef.current;
      animatingRankRef.current = { roomId: room.id, rank: winner.rank };
      const waitForReveal = Math.max(0, revealedAt - Date.now());
      schedule(() => {
        if (spinChainIdRef.current !== chainId) return;
        runWinnerReveal(room.id, winner, chainId);
      }, waitForReveal);
    }
  }, [clearSpinTimers, markRevealsApplied, runWinnerReveal, schedule, snapWheelToNumber]);

  const applyRoom = useCallback((room: LottoRoom) => {
    const stake = Number(room.stake);
    const previousId = previousRoundRef.current[stake];
    previousRoundRef.current[stake] = room.id;
    // Keep only fingerprints for the four live stake rooms + prior ids.
    const keep = new Set(Object.values(previousRoundRef.current));
    for (const id of Object.keys(animatedRanksRef.current)) {
      if (!keep.has(id) && id !== room.id) {
        delete animatedRanksRef.current[id];
      }
    }
    const roundChanged = Boolean(previousId && previousId !== room.id);
    const viewing =
      stake === activeStakeRef.current && isActiveRef.current;

    if (roundChanged) {
      animatedRanksRef.current[room.id] = 0;
      // Only reset the visible wheel UI when this is the room being shown.
      if (viewing) {
        clearSpinTimers();
        spinChainIdRef.current += 1;
        animatingRankRef.current = null;
        setDisplayWinner(null);
        setDrawNotice(null);
        setSpinPhase("idle");
      }
    }

    // Always keep per-stake room store current (including non-selected rooms).
    setRooms((current) => ({ ...current, [stake]: room }));

    if (stake === activeStakeRef.current) {
      setSelected((items) => {
        if (roundChanged) return [];
        return pruneUnavailable(items, room, submittingNumbersRef.current);
      });
    }

    if (viewing) {
      syncSpinFromRoom(room);
    } else {
      // Background stake or inactive tab: apply reveals to memory, no ceremony.
      markRevealsApplied(room);
    }

    if (room.status === "completed") setHistoryRevision((value) => value + 1);
  }, [clearSpinTimers, markRevealsApplied, syncSpinFromRoom]);

  const onMessage = useCallback((message: ServerMessage) => {
    if (message.type === "snapshot") message.rooms.forEach(applyRoom);
    else if (message.type === "room_updated") applyRoom(message.room);
    else if (message.type === "rooms_updated") message.rooms.forEach(applyRoom);
    else if (message.type === "wallet") onBalanceChange(message.balance);
  }, [applyRoom, onBalanceChange]);

  // Stay connected while authenticated — draw follow-along must not depend on the Lotto tab.
  const wsUrl = useMemo(
    () => (accessToken ? lottoWebSocketUrl(accessToken) : null),
    [accessToken],
  );
  const { status: socketStatus } = useWebSocket<ServerMessage, { type: "ping" }>({
    url: wsUrl,
    onMessage,
  });

  useEffect(() => {
    reducedMotionRef.current = prefersReducedMotion();
  }, []);

  // Initial / token refresh snapshot — independent of tab visibility.
  useEffect(() => {
    if (!accessToken) return;
    getLottoSnapshot(accessToken)
      .then((snapshot) => snapshot.rooms.forEach(applyRoom))
      .catch(() => setError(t("lotto.roomsError")));
  }, [accessToken, applyRoom, t]);

  // Pause local ceremony only when leaving the Lotto tab; keep room state + WS.
  useEffect(() => {
    if (!isActive) {
      clearSpinTimers();
      spinChainIdRef.current += 1;
      animatingRankRef.current = null;
      setSpinPhase("idle");
      setDrawNotice(null);
      const current = rooms[activeStakeRef.current];
      if (current) markRevealsApplied(current);
      return;
    }
    // Returning: reconstruct wheel/notifier from authoritative room store.
    const current = rooms[activeStakeRef.current];
    if (current) syncSpinFromRoom(current);
    // rooms intentionally omitted — only re-sync on visibility regain
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, clearSpinTimers, markRevealsApplied, syncSpinFromRoom]);

  useEffect(() => () => {
    clearSpinTimers();
    spinChainIdRef.current += 1;
  }, [clearSpinTimers]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 200);
    return () => window.clearInterval(timer);
  }, []);

  const loadHistory = useCallback((page: number) => {
    setLoadingHistory(true);
    getLottoHistory(accessToken, PAGE_SIZE, page * PAGE_SIZE)
      .then(setHistory)
      .catch(() => setError(t("lotto.historyError")))
      .finally(() => setLoadingHistory(false));
  }, [accessToken]);

  useEffect(() => {
    if (isActive && view === "history") loadHistory(historyPage);
  }, [historyPage, historyRevision, isActive, loadHistory, view]);

  const room = rooms[activeStake];
  const owners = useMemo(
    () => new Map((room?.reservations ?? []).map((item) => [item.number, item])),
    [room],
  );
  const open = room?.status === "open";
  const countdown = room?.draw_scheduled_at
    ? Math.max(0, Math.ceil((new Date(room.draw_scheduled_at).getTime() - now) / 1000))
    : 0;
  const spinning = spinPhase === "spinning";
  const showWinnerOverlay =
    (spinPhase === "settled" || spinPhase === "idle") && displayWinner != null;
  const wheelTransition =
    spinning && spinMs > 0 ? `transform ${spinMs}ms ${SPIN_EASING}` : "none";

  const toggleNumber = (number: number) => {
    if (!open || owners.has(number) || submitting) return;
    setSelected((current) =>
      current.includes(number)
        ? current.filter((item) => item !== number)
        : [...current, number].sort((a, b) => a - b),
    );
    setError(null);
  };

  const submit = async () => {
    if (!room || !open || !selected.length || submitting) return;
    const requested = [...selected];
    setSubmitting(true);
    submittingNumbersRef.current = new Set(requested);
    setError(null);
    const requestId = crypto.randomUUID();
    try {
      const response = await reserveLotto(room.stake, requested, requestId, accessToken);
      submittingNumbersRef.current = null;
      applyRoom(response.round);
      onBalanceChange(response.balance);
      const reserved = new Set(response.numbers);
      setSelected((current) => current.filter((number) => !reserved.has(number)));
    } catch (reason) {
      submittingNumbersRef.current = null;
      const detail = (reason as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      const contested = parseContestedNumbers(detail);
      try {
        const snapshot = await getLottoSnapshot(accessToken);
        snapshot.rooms.forEach(applyRoom);
        const refreshed = snapshot.rooms.find((item) => Number(item.stake) === activeStake);
        if (refreshed) {
          setSelected((current) => {
            const pruned = pruneUnavailable(current, refreshed, null);
            const forceDrop = contested.length
              ? pruned.filter((number) => !contested.includes(number))
              : pruned;
            return forceDrop;
          });
        }
      } catch { /* keep original error */ }
      const contestedLike =
        contested.length > 0 ||
        /already reserved|reserved by another|just taken/i.test(detail ?? "");
      setError(contestedLike ? t(CONTESTED_SELECTION_MSG_KEY) : (detail ? ts(detail) : t("lotto.reserveFailed")));
    } finally {
      submittingNumbersRef.current = null;
      setSubmitting(false);
    }
  };

  if (!room) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-[#eef3f8] dark:bg-[#070d1a]">
        <Loader2 className="animate-spin text-sky-500" />
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-[#eef3f8] text-slate-950 [scrollbar-width:none] dark:bg-[#070d1a] dark:text-white">
      <style>{`
        @keyframes lotto-pop { 0% { transform: scale(.75); opacity: 0 } 100% { transform: scale(1); opacity: 1 } }
        .lotto-pop { animation: lotto-pop .45s ease-out both; }
        @media (prefers-reduced-motion: reduce) {
          .lotto-pop { animation: none; opacity: 1; transform: none; }
        }
      `}</style>
      <div className="mx-auto flex min-h-full w-full max-w-[460px] flex-col px-3 pb-5 pt-2">
        <header className="flex h-11 items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-300 to-amber-500 text-[#342006]">
              <RotateCw size={19} strokeWidth={2.5} />
            </span>
            <div>
              <h1 className="text-sm font-black tracking-[.12em]">{t("lotto.title")}</h1>
              <p className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">
                {t("lotto.serverVerified")}{socketStatus === "open" ? t("common.live") : t("lotto.reconnecting")}
              </p>
            </div>
          </div>
          <button type="button" onClick={() => setSoundOn((value) => !value)} className="flex h-9 w-9 items-center justify-center rounded-xl bg-white shadow-sm dark:bg-[#10192b]">
            {soundOn ? <Volume2 size={16} /> : <VolumeX size={16} />}
          </button>
        </header>

        <div className="mt-2 grid grid-cols-2 rounded-xl bg-white p-1 shadow-sm dark:bg-[#10192b]">
          {(["game", "history"] as const).map((item) => (
            <button key={item} type="button" onClick={() => setView(item)} className={`flex h-8 items-center justify-center gap-1.5 rounded-lg text-[10px] font-black uppercase ${view === item ? "bg-[#0b3158] text-white" : "text-slate-500"}`}>
              {item === "game" ? <RotateCw size={12} /> : <History size={12} />}
              {item === "game" ? t("lotto.game") : t("lotto.myHistory")}
            </button>
          ))}
        </div>

        {view === "history" ? (
          <section className="mt-2 rounded-xl border border-slate-200 bg-white p-2.5 dark:border-white/8 dark:bg-[#10192b]">
            {loadingHistory ? (
              <Loader2 className="mx-auto my-10 animate-spin text-sky-500" />
            ) : history?.items.length ? (
              <div className="space-y-2">
                {history.items.map((item) => (
                  <article key={item.round_id} className={`rounded-lg border p-2.5 ${Number(item.total_prize) > 0 ? "border-emerald-300 bg-emerald-50 dark:bg-emerald-400/8" : "border-slate-200 dark:border-white/8"}`}>
                    <div className="flex justify-between text-[10px] font-black">
                      <span>{t("lotto.roomHistory", { stake: money(item.stake), code: item.round_code })}</span>
                      <span className={Number(item.net) >= 0 ? "text-emerald-600" : "text-rose-500"}>{Number(item.net) >= 0 ? "+" : ""}{money(item.net)} {t("common.etb")}</span>
                    </div>
                    <p className="mt-1 text-[9px] text-slate-500">{t("lotto.numbersPaid", { numbers: item.numbers.join(", "), paid: money(item.total_paid) })}</p>
                    <p className="mt-1 text-[9px] font-bold">{item.winners.length ? t("lotto.won", { detail: item.winners.map((winner) => `${winner.rank}${winner.rank === 1 ? "st" : winner.rank === 2 ? "nd" : "rd"} #${winner.number}`).join(", "), prize: money(item.total_prize) }) : t("lotto.noWinning")}</p>
                    <p className="mt-1 text-[8px] text-slate-400">{new Date(item.completed_at).toLocaleString()}</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="py-12 text-center text-xs text-slate-500">{t("lotto.noHistory")}</p>
            )}
            <div className="mt-3 flex items-center justify-between">
              <button disabled={historyPage === 0} onClick={() => setHistoryPage((page) => page - 1)} className="flex items-center gap-1 text-[10px] font-black disabled:opacity-30"><ChevronLeft size={14} /> {t("common.prev")}</button>
              <span className="text-[9px] text-slate-500">{t("lotto.page", { page: historyPage + 1 })}</span>
              <button disabled={!history || (historyPage + 1) * PAGE_SIZE >= history.total} onClick={() => setHistoryPage((page) => page + 1)} className="flex items-center gap-1 text-[10px] font-black disabled:opacity-30">{t("common.next")} <ChevronRight size={14} /></button>
            </div>
          </section>
        ) : (
          <>
            <div className="mt-2 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]">
              {STAKES.map((stake) => {
                const candidate = rooms[stake];
                return (
                  <button key={stake} type="button" onClick={() => {
                    if (stake === activeStakeRef.current) return;
                    // Stop local wheel ceremony only — do not discard other rooms' draw state.
                    const leaving = rooms[activeStakeRef.current];
                    if (leaving) markRevealsApplied(leaving);
                    clearSpinTimers();
                    spinChainIdRef.current += 1;
                    animatingRankRef.current = null;
                    activeStakeRef.current = stake;
                    setActiveStake(stake);
                    setSelected([]);
                    setDisplayWinner(null);
                    setDrawNotice(null);
                    setSpinPhase("idle");
                    const nextRoom = rooms[stake];
                    if (nextRoom) syncSpinFromRoom(nextRoom);
                  }} className={`min-w-[7.25rem] rounded-xl border px-2.5 py-2 text-left ${stake === activeStake ? "border-sky-500 bg-[#0b3158] text-white" : "border-slate-200 bg-white dark:border-white/8 dark:bg-[#10192b]"}`}>
                    <div className="flex justify-between text-xs font-black"><span>{stake} ETB</span><span className="text-[8px] uppercase opacity-60">{candidate?.status ?? "…"}</span></div>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-slate-200/40"><div className="h-full bg-emerald-400" style={{ width: `${((candidate?.occupied ?? 0) / (candidate?.capacity ?? CAPACITY)) * 100}%` }} /></div>
                    <p className="mt-1 text-[8px] font-semibold opacity-70">{candidate?.occupied ?? 0}/{candidate?.capacity ?? CAPACITY} · {money(candidate?.total_pool ?? stake * CAPACITY)} pool</p>
                  </button>
                );
              })}
            </div>

            <section className="relative mt-2 overflow-hidden rounded-2xl border border-slate-200 bg-[radial-gradient(circle_at_50%_35%,#fff_0%,#dce7f2_100%)] p-2 shadow-xl dark:border-white/8 dark:bg-[radial-gradient(circle_at_50%_35%,#17233b_0%,#070d18_100%)]">
              <div className="flex justify-between px-1 text-[9px] font-bold text-slate-500">
                <span className="flex items-center gap-1"><Users size={12} /> {room.occupied}/{room.capacity}</span>
                <span>{money(room.total_pool)} ETB pool</span>
                <span className="flex items-center gap-1"><Clock3 size={12} /> {room.status}</span>
              </div>
              <div className="relative mx-auto aspect-[300/310] w-full max-w-[350px]">
                {(room.status === "countdown" || room.status === "drawing") && (
                  <div className="pointer-events-none absolute left-1/2 top-[52%] z-20 w-44 -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-sky-300/50 bg-[#07172d]/90 px-3 py-3 text-center text-white shadow-2xl backdrop-blur">
                    {room.status === "countdown" ? (
                      <><p className="text-[8px] font-black uppercase text-sky-200">{t("lotto.roomFull")}</p><p className="text-4xl font-black">{countdown}</p><p className="text-[8px]">{t("lotto.drawPending")}</p></>
                    ) : spinPhase === "anticipation" || drawNotice ? (
                      <div className="lotto-pop">
                        <Sparkles className="mx-auto text-amber-300" size={18} />
                        <p className="mt-1 text-[10px] font-black uppercase tracking-wide text-amber-100">
                          {drawNotice ?? t("lotto.preparingDraw")}
                        </p>
                      </div>
                    ) : showWinnerOverlay && displayWinner ? (
                      <div className="lotto-pop"><p className="text-[9px] font-black uppercase">{[t("lotto.first"), t("lotto.second"), t("lotto.third")][displayWinner.rank - 1]} {t("lotto.winner")}</p><p className="text-3xl font-black">#{displayWinner.number}</p><p className="truncate text-[10px] font-bold">{displayWinner.user_id === userId ? t("lotto.youLabel", { name: firstName }) : displayWinner.display_name}</p><p className="text-[10px] font-black">{money(displayWinner.prize)} {t("common.etb")}</p></div>
                    ) : spinning ? (
                      <><RotateCw className="mx-auto animate-spin text-sky-300" /><p className="mt-1 text-[9px] font-black uppercase">{t("lotto.revealing")}</p></>
                    ) : (
                      <><p className="text-[9px] font-black uppercase text-sky-200">{t("lotto.drawInProgress")}</p><p className="mt-1 text-[8px] opacity-70">{t("lotto.waitingReveal")}</p></>
                    )}
                  </div>
                )}
                <svg viewBox="0 0 300 310" className="h-full w-full drop-shadow-[0_16px_18px_rgba(15,23,42,.25)]" aria-label={t("lotto.wheelAria")}>
                  <circle cx="150" cy="160" r="145" fill="#071426" stroke="#d5a62d" strokeWidth="6" />
                  <g style={{ transform: `rotate(${rotation}deg)`, transformOrigin: "150px 160px", transition: wheelTransition }}>
                    {Array.from({ length: CAPACITY }, (_, index) => {
                      const label = polar(-90 + index * SEGMENT, 103);
                      const won = room.winners.find((winner) => winner.number === index + 1);
                      return <g key={index}><path d={segmentPath(index)} fill={COLORS[index]} stroke={won ? "#fde68a" : "rgba(255,255,255,.32)"} strokeWidth={won ? 5 : 1} /><text x={label.x} y={label.y} fill="white" fontSize="10" fontWeight="900" textAnchor="middle" dominantBaseline="central" style={{ transform: `rotate(${-rotation}deg)`, transformOrigin: `${label.x}px ${label.y}px`, transition: wheelTransition }}>{index + 1}</text></g>;
                    })}
                  </g>
                  <circle cx="150" cy="160" r="35" fill="#09111f" stroke="#d9aa34" strokeWidth="4" />
                  <path d="M 150 3 L 164 24 L 155 42 L 145 42 L 136 24 Z" fill="#f3c84b" stroke="#5e3908" strokeWidth="2" />
                </svg>
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                {[1, 2, 3].map((rank) => {
                  const winner = room.winners.find((item) => item.rank === rank);
                  const highlighted = displayWinner?.rank === rank && (spinPhase === "settled" || spinPhase === "idle");
                  return <div key={rank} className={`rounded-lg border p-1.5 text-center ${highlighted ? "border-amber-400 bg-amber-50 dark:bg-amber-400/10" : "border-slate-300 bg-white/70 dark:border-white/10 dark:bg-white/5"}`}><p className="text-[8px] font-black uppercase opacity-50">{rank === 1 ? t("lotto.rank1Short") : rank === 2 ? t("lotto.rank2Short") : t("lotto.rank3Short")} {t("lotto.winner")}</p><p className="text-xs font-black">{winner ? `#${winner.number} · ${winner.user_id === userId ? t("common.you") : winner.display_name}` : "—"}</p></div>;
                })}
              </div>
            </section>

            <section className="mt-2 rounded-xl border border-slate-200 bg-white p-2.5 shadow-sm dark:border-white/8 dark:bg-[#10192b]">
              <div className="flex justify-between"><div><h2 className="text-xs font-black">{t("lotto.reserveNumbers")}</h2><p className="text-[9px] text-slate-500">{t("lotto.chooseOpen", { stake: money(room.stake) })}</p></div><ShieldCheck size={18} className="text-emerald-600" /></div>
              <div className="mt-2 grid grid-cols-5 gap-1.5">
                {Array.from({ length: CAPACITY }, (_, index) => {
                  const number = index + 1;
                  const owner = owners.get(number);
                  const chosen = !owner && selected.includes(number);
                  const winner = room.winners.find((item) => item.number === number);
                  return (
                    <button
                      key={number}
                      type="button"
                      disabled={!open || !!owner || submitting}
                      onClick={() => toggleNumber(number)}
                      className={`relative flex h-12 flex-col items-center justify-center rounded-lg border ${
                        winner
                          ? "border-amber-400 bg-amber-100"
                          : chosen
                            ? "border-sky-500 bg-sky-100 text-sky-950"
                            : owner?.user_id === userId
                              ? "border-cyan-400 bg-cyan-50 text-cyan-900"
                              : owner
                                ? "border-slate-200 bg-slate-100 text-slate-500 dark:bg-white/5"
                                : "border-emerald-200 bg-emerald-50 text-emerald-900 dark:bg-emerald-400/8 dark:text-emerald-200"
                      }`}
                    >
                      <span className="text-sm font-black">{number}</span>
                      <span className="max-w-full truncate px-1 text-[7px] font-black uppercase opacity-60">
                        {winner ? t("lotto.rank", { rank: winner.rank }) : chosen ? t("lotto.selected") : owner?.user_id === userId ? t("common.you") : owner?.initials ?? t("lotto.open")}
                      </span>
                      {chosen && <Check size={9} className="absolute right-1 top-1" />}
                    </button>
                  );
                })}
              </div>
              {error && <p className="mt-2 rounded-md bg-rose-50 p-2 text-[9px] font-semibold text-rose-700 dark:bg-rose-400/10 dark:text-rose-200">{ts(error)}</p>}
              <button type="button" disabled={!open || !selected.length || submitting} onClick={() => void submit()} className="mt-2 flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-[#0d6b55] text-[10px] font-black uppercase tracking-wide text-white disabled:opacity-40">
                {submitting ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                {selected.length ? t("lotto.reserveCount", { count: selected.length, total: money(selected.length * Number(room.stake)) }) : t("lotto.selectOpen")}
              </button>
              <p className="mt-1.5 text-center text-[8px] text-slate-400">{t("lotto.walletHint", { balance: walletBalance === null ? "—" : `${money(walletBalance)} ${t("common.etb")}` })}</p>
            </section>

            <section className="mt-2 grid grid-cols-5 rounded-xl border border-slate-200 bg-white p-2 dark:border-white/8 dark:bg-[#10192b]">
              {[[t("lotto.pool"), room.total_pool], [t("lotto.pool1"), room.first_prize], [t("lotto.pool2"), room.second_prize], [t("lotto.pool3"), room.third_prize], [t("lotto.system"), room.reserve_amount]].map(([label, value]) => <div key={String(label)} className="text-center"><Sparkles size={10} className="mx-auto text-amber-500" /><p className="mt-0.5 text-[7px] font-black uppercase text-slate-400">{label}</p><p className="text-[9px] font-black">{money(value)}</p></div>)}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
