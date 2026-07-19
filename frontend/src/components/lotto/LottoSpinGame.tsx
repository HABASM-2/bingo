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
import {
  playLottoStart,
  playLottoWinnerReveal,
  primeLottoAudioUnlock,
  stopLottoAudio,
  unlockLottoAudio,
  warmLottoAudio,
} from "../../utils/lottoAudio";

/** Persist mute only when user explicitly turns sound off. Missing key = ON. */
const LOTTO_SOUND_STORAGE_KEY = "lotto-sound-on";

function readLottoSoundOn(): boolean {
  try {
    const raw = window.localStorage.getItem(LOTTO_SOUND_STORAGE_KEY);
    // Default unmuted. Only explicit "0" / "false" means muted.
    if (raw == null || raw === "") return true;
    return raw !== "0" && raw !== "false";
  } catch {
    return true;
  }
}

function writeLottoSoundOn(on: boolean): void {
  try {
    window.localStorage.setItem(LOTTO_SOUND_STORAGE_KEY, on ? "1" : "0");
  } catch {
    /* ignore quota / private mode */
  }
}

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

type SpinPhase = "idle" | "anticipation" | "cruising" | "decelerating" | "settled";

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

/** Premium two-phase spin (ms). Cruise ~8s then decelerate ~5s; settle gap for bounce. */
const SPIN_PACING = {
  1: { anticipation: 1000, cruise: 8000, decelerate: 5000, gap: 2200, cruiseTurns: 7, decelerateTurns: 2 },
  2: { anticipation: 900, cruise: 8000, decelerate: 5000, gap: 2000, cruiseTurns: 6, decelerateTurns: 2 },
  3: { anticipation: 800, cruise: 8000, decelerate: 5000, gap: 2000, cruiseTurns: 6, decelerateTurns: 2 },
} as const;

/**
 * If a reveal’s `revealed_at` is older than this while we are supposedly “live”,
 * treat it as missed (UI only, no audio/ceremony). Covers WS gaps / tab blur.
 */
const LIVE_REVEAL_STALE_MS = 2500;

function documentIsVisible(): boolean {
  return typeof document === "undefined" || document.visibilityState === "visible";
}

const CRUISE_EASING = "linear";
const DECEL_EASING = "cubic-bezier(0.05, 0.85, 0.15, 1)";
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
  // Default sound ON. localStorage only mutes when the user previously chose off.
  const [soundOn, setSoundOn] = useState(readLottoSoundOn);
  const [rotation, setRotation] = useState(0);
  const [spinPhase, setSpinPhase] = useState<SpinPhase>("idle");
  const [spinMs, setSpinMs] = useState<number>(SPIN_PACING[1].cruise);
  const [spinEasing, setSpinEasing] = useState(DECEL_EASING);
  const [drawNotice, setDrawNotice] = useState<string | null>(null);
  const [displayWinner, setDisplayWinner] = useState<LottoWinner | null>(null);
  /** Numbers whose reveal has fully settled (glow + bounce allowed). */
  const [settledNumbers, setSettledNumbers] = useState<number[]>([]);
  /** Lucky number currently mid-spin — never style until settle completes. */
  const [spinningNumber, setSpinningNumber] = useState<number | null>(null);
  const [bounceNumber, setBounceNumber] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());

  const previousRoundRef = useRef<Record<number, string>>({});
  const animatedRanksRef = useRef<Record<string, number>>({});
  const animatingRankRef = useRef<{ roomId: string; rank: number } | null>(null);
  /** Room ids that already played `start.wav` for the first spin of the round. */
  const startAudioRoomRef = useRef<string | null>(null);
  /**
   * After the first sync for a room while the user is present, further ranks
   * may play live audio. First contact (rejoin / mid-round join) is always silent.
   */
  const liveAudioArmedRef = useRef<Record<string, boolean>>({});
  const roomsRef = useRef<Record<number, LottoRoom>>({});
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

  /** Present on Lotto tab with a visible document — only then is audio eligible. */
  const isLiveAudience = useCallback(
    () => isActiveRef.current && documentIsVisible(),
    [],
  );

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

  /** Show winners that already happened — no ceremony, no audio. */
  const restoreWinnersUi = useCallback((room: LottoRoom) => {
    clearSpinTimers();
    spinChainIdRef.current += 1;
    animatingRankRef.current = null;
    stopLottoAudio();
    if (!room.winners.length) {
      if (room.status === "open" || room.status === "countdown") {
        setDisplayWinner(null);
        setSettledNumbers([]);
        setSpinningNumber(null);
        setBounceNumber(null);
        setDrawNotice(null);
        setSpinPhase("idle");
      }
      return;
    }
    const latest = room.winners[room.winners.length - 1];
    markRevealsApplied(room);
    setDisplayWinner(latest);
    setSettledNumbers(room.winners.map((item) => item.number));
    setSpinningNumber(null);
    setBounceNumber(null);
    setDrawNotice(null);
    setSpinPhase("idle");
    snapWheelToNumber(latest.number);
  }, [clearSpinTimers, markRevealsApplied, snapWheelToNumber]);

  const runWinnerReveal = useCallback((
    roomId: string,
    winner: LottoWinner,
    chainId: number,
  ) => {
    // Audience left mid-wait / mid-spin — never blast audio for a missed land.
    if (!isLiveAudience()) {
      animatedRanksRef.current[roomId] = Math.max(
        animatedRanksRef.current[roomId] ?? 0,
        winner.rank,
      );
      animatingRankRef.current = null;
      setSpinningNumber(null);
      setDisplayWinner(winner);
      setSettledNumbers((current) =>
        current.includes(winner.number) ? current : [...current, winner.number],
      );
      snapWheelToNumber(winner.number);
      setSpinPhase("idle");
      setDrawNotice(null);
      stopLottoAudio();
      return;
    }

    const pacing = SPIN_PACING[winner.rank as 1 | 2 | 3] ?? SPIN_PACING[3];
    const scale = reducedMotionRef.current ? 0.4 : 1;
    const anticipation = Math.max(350, Math.round(pacing.anticipation * scale));
    const cruiseMs = Math.max(2200, Math.round(pacing.cruise * scale));
    const decelerateMs = Math.max(1600, Math.round(pacing.decelerate * scale));
    const gap = Math.max(800, Math.round(pacing.gap * scale));
    const cruiseTurns = reducedMotionRef.current
      ? Math.max(2, pacing.cruiseTurns - 4)
      : pacing.cruiseTurns;
    const decelerateTurns = reducedMotionRef.current
      ? Math.max(1, pacing.decelerateTurns - 1)
      : pacing.decelerateTurns;

    animatingRankRef.current = { roomId, rank: winner.rank };
    setDisplayWinner(null);
    setBounceNumber(null);
    setSpinningNumber(winner.number);
    setDrawNotice(tGlobal("lotto.drawing", { rank: rankLabel(winner.rank) }));
    setSpinPhase("anticipation");

    schedule(() => {
      if (spinChainIdRef.current !== chainId) return;
      if (!isLiveAudience()) {
        animatedRanksRef.current[roomId] = Math.max(
          animatedRanksRef.current[roomId] ?? 0,
          winner.rank,
        );
        animatingRankRef.current = null;
        setSpinningNumber(null);
        setDisplayWinner(winner);
        setSettledNumbers((current) =>
          current.includes(winner.number) ? current : [...current, winner.number],
        );
        snapWheelToNumber(winner.number);
        setSpinPhase("idle");
        setDrawNotice(null);
        stopLottoAudio();
        return;
      }
      // Phase 1: high-speed cruise — do not land on the winner yet.
      // Keep the lucky slice unstyled for the entire cruise + decelerate window.
      // `start.wav` once per round when the first spin action actually begins.
      if (soundOnRef.current && startAudioRoomRef.current !== roomId) {
        startAudioRoomRef.current = roomId;
        playLottoStart();
      }
      const cruiseTarget = rotationRef.current + cruiseTurns * 360;
      rotationRef.current = cruiseTarget;
      setSpinMs(cruiseMs);
      setSpinEasing(CRUISE_EASING);
      setSpinPhase("cruising");
      setDrawNotice(null);
      setRotation(cruiseTarget);

      schedule(() => {
        if (spinChainIdRef.current !== chainId) return;
        if (!isLiveAudience()) {
          animatedRanksRef.current[roomId] = Math.max(
            animatedRanksRef.current[roomId] ?? 0,
            winner.rank,
          );
          animatingRankRef.current = null;
          setSpinningNumber(null);
          setDisplayWinner(winner);
          setSettledNumbers((current) =>
            current.includes(winner.number) ? current : [...current, winner.number],
          );
          snapWheelToNumber(winner.number);
          setSpinPhase("idle");
          stopLottoAudio();
          return;
        }
        // Phase 2: decelerate onto the winning segment (still no glow/color).
        const normalized = ((rotationRef.current % 360) + 360) % 360;
        const desired = winnerAngle(winner.number);
        const next =
          rotationRef.current
          + decelerateTurns * 360
          + ((desired - normalized + 360) % 360);
        rotationRef.current = next;
        setSpinMs(decelerateMs);
        setSpinEasing(DECEL_EASING);
        setSpinPhase("decelerating");
        setRotation(next);

        schedule(() => {
          if (spinChainIdRef.current !== chainId) return;
          // Only now: winning mark + bounce after the wheel has fully stopped.
          setSpinPhase("settled");
          setSpinningNumber(null);
          setDisplayWinner(winner);
          setSettledNumbers((current) =>
            current.includes(winner.number) ? current : [...current, winner.number],
          );
          setBounceNumber(winner.number);
          animatedRanksRef.current[roomId] = Math.max(
            animatedRanksRef.current[roomId] ?? 0,
            winner.rank,
          );
          animatingRankRef.current = null;

          // Bounce ends on the short gap; audio/hold can run longer (esp. 3rd→next).
          schedule(() => {
            if (spinChainIdRef.current !== chainId) return;
            setBounceNumber(null);
          }, gap);

          void (async () => {
            const playAudio =
              soundOnRef.current && isLiveAudience();
            if (playAudio) {
              // Interrupt leftover start/prior clips so place→number match the land.
              stopLottoAudio();
              await playLottoWinnerReveal(winner.rank, winner.number);
            } else {
              // Same structural delay when muted / away so the next round is not rushed.
              stopLottoAudio();
              await playLottoWinnerReveal(winner.rank, winner.number, {
                silent: true,
              });
            }
            if (spinChainIdRef.current !== chainId) return;
            setBounceNumber(null);
            setSpinPhase("idle");
          })();
        }, decelerateMs);
      }, cruiseMs);
    }, anticipation);
  }, [isLiveAudience, schedule, snapWheelToNumber]);

  const syncSpinFromRoom = useCallback((room: LottoRoom) => {
    const stake = Number(room.stake);
    if (stake !== activeStakeRef.current) {
      markRevealsApplied(room);
      return;
    }

    // Not watching Lotto (or document hidden): restore UI only, never audio.
    if (!isLiveAudience()) {
      restoreWinnersUi(room);
      liveAudioArmedRef.current[room.id] = false;
      return;
    }

    const winners = room.winners;

    // First contact for this room while present: catch-up UI only, then arm for future.
    if (!liveAudioArmedRef.current[room.id]) {
      restoreWinnersUi(room);
      liveAudioArmedRef.current[room.id] = true;
      return;
    }

    if (!winners.length) {
      if (room.status === "open" || room.status === "countdown") {
        setDisplayWinner(null);
        setSettledNumbers([]);
        setSpinningNumber(null);
        setBounceNumber(null);
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

    // Ceremony already running or finished for this rank — keep UI in sync.
    if (latest.rank <= covered) {
      const phase = spinPhaseRef.current;
      if (phase === "idle" && already >= latest.rank) {
        setDisplayWinner(latest);
        setSettledNumbers(room.winners.map((item) => item.number));
        snapWheelToNumber(latest.number);
      }
      return;
    }

    // Live path: silent-snap missed/stale ranks; ceremony only for a fresh latest.
    for (const winner of winners) {
      if (winner.rank <= covered) continue;
      if (winner.rank < latest.rank) {
        animatedRanksRef.current[room.id] = winner.rank;
        setSettledNumbers((current) =>
          current.includes(winner.number) ? current : [...current, winner.number],
        );
        snapWheelToNumber(winner.number);
        continue;
      }

      const revealedAt = winner.revealed_at
        ? new Date(winner.revealed_at).getTime()
        : Date.now();
      const age = Date.now() - revealedAt;
      // Reveal moment already passed while we weren't eligible — UI only.
      if (age > LIVE_REVEAL_STALE_MS) {
        animatedRanksRef.current[room.id] = winner.rank;
        animatingRankRef.current = null;
        setSpinningNumber(null);
        setDisplayWinner(winner);
        setSettledNumbers(room.winners.map((item) => item.number));
        snapWheelToNumber(winner.number);
        setSpinPhase("idle");
        setDrawNotice(null);
        stopLottoAudio();
        return;
      }

      clearSpinTimers();
      const chainId = ++spinChainIdRef.current;
      animatingRankRef.current = { roomId: room.id, rank: winner.rank };
      // Track the lucky number as soon as ceremony is queued so server
      // winners data cannot amber-highlight the slice / pad mid-spin.
      setSpinningNumber(winner.number);
      const waitForReveal = Math.max(0, revealedAt - Date.now());
      schedule(() => {
        if (spinChainIdRef.current !== chainId) return;
        runWinnerReveal(room.id, winner, chainId);
      }, waitForReveal);
    }
  }, [
    clearSpinTimers,
    isLiveAudience,
    markRevealsApplied,
    restoreWinnersUi,
    runWinnerReveal,
    schedule,
    snapWheelToNumber,
  ]);

  const applyRoom = useCallback((room: LottoRoom) => {
    const stake = Number(room.stake);
    const previousId = previousRoundRef.current[stake];
    previousRoundRef.current[stake] = room.id;
    // Keep only fingerprints for the four live stake rooms + prior ids.
    const keep = new Set(Object.values(previousRoundRef.current));
    for (const id of Object.keys(animatedRanksRef.current)) {
      if (!keep.has(id) && id !== room.id) {
        delete animatedRanksRef.current[id];
        delete liveAudioArmedRef.current[id];
      }
    }
    const roundChanged = Boolean(previousId && previousId !== room.id);
    const onActiveStake = stake === activeStakeRef.current;
    const live = onActiveStake && isLiveAudience();

    if (roundChanged) {
      animatedRanksRef.current[room.id] = 0;
      liveAudioArmedRef.current[room.id] = false;
      if (previousId) {
        delete liveAudioArmedRef.current[previousId];
      }
      if (startAudioRoomRef.current === previousId) {
        startAudioRoomRef.current = null;
      }
      // Only reset the visible wheel UI when this is the room being shown live.
      if (live) {
        clearSpinTimers();
        spinChainIdRef.current += 1;
        animatingRankRef.current = null;
        setDisplayWinner(null);
        setSettledNumbers([]);
        setSpinningNumber(null);
        setBounceNumber(null);
        setDrawNotice(null);
        setSpinPhase("idle");
        stopLottoAudio();
      }
    }

    // Always keep per-stake room store current (including non-selected rooms).
    setRooms((current) => {
      const next = { ...current, [stake]: room };
      roomsRef.current = next;
      return next;
    });

    if (onActiveStake) {
      setSelected((items) => {
        if (roundChanged) return [];
        return pruneUnavailable(items, room, submittingNumbersRef.current);
      });
    }

    if (onActiveStake && isActiveRef.current) {
      // Active Lotto tab (visible or hidden): sync UI; audio only when visible.
      syncSpinFromRoom(room);
    } else {
      // Other stake / left Lotto: memory only, no ceremony.
      markRevealsApplied(room);
      liveAudioArmedRef.current[room.id] = false;
    }

    if (room.status === "completed") setHistoryRevision((value) => value + 1);
  }, [clearSpinTimers, isLiveAudience, markRevealsApplied, syncSpinFromRoom]);

  const onMessage = useCallback((message: ServerMessage) => {
    if (message.type === "snapshot") message.rooms.forEach(applyRoom);
    else if (message.type === "room_updated") applyRoom(message.room);
    else if (message.type === "rooms_updated") message.rooms.forEach(applyRoom);
    else if (message.type === "wallet") onBalanceChange(message.balance);
  }, [applyRoom, onBalanceChange]);

  // Connect only while the Lotto tab is active — disconnect on leave to save load.
  const wsUrl = useMemo(
    () => (isActive && accessToken ? lottoWebSocketUrl(accessToken) : null),
    [isActive, accessToken],
  );
  const { status: socketStatus } = useWebSocket<ServerMessage, { type: "ping" }>({
    url: wsUrl,
    onMessage,
  });

  useEffect(() => {
    reducedMotionRef.current = prefersReducedMotion();
  }, []);

  // Prefetch WAVs + unlock HTMLAudio on first tap (staking / mute / anywhere).
  // Default remains unmuted; silent estimates only run when the user mutes.
  useEffect(() => {
    if (!isActive) return;
    const disposeWarm = warmLottoAudio({ numbers: true });
    const disposeUnlock = unlockLottoAudio();
    return () => {
      disposeWarm();
      disposeUnlock();
      stopLottoAudio();
    };
  }, [isActive]);

  useEffect(() => {
    writeLottoSoundOn(soundOn);
    if (!soundOn) stopLottoAudio();
  }, [soundOn]);

  // Clear stale UI when leaving so return shows a connecting loader.
  useEffect(() => {
    if (isActive) return;
    clearSpinTimers();
    spinChainIdRef.current += 1;
    animatingRankRef.current = null;
    previousRoundRef.current = {};
    animatedRanksRef.current = {};
    liveAudioArmedRef.current = {};
    startAudioRoomRef.current = null;
    submittingNumbersRef.current = null;
    roomsRef.current = {};
    setRooms({});
    setSelected([]);
    setDisplayWinner(null);
    setSettledNumbers([]);
    setSpinningNumber(null);
    setBounceNumber(null);
    setDrawNotice(null);
    setSpinPhase("idle");
    setError(null);
    setSubmitting(false);
    stopLottoAudio();
  }, [isActive, clearSpinTimers]);

  // Document blur while on Lotto: freeze ceremony, keep winners on screen, skip audio forever for those ranks.
  useEffect(() => {
    if (!isActive) return;
    const onVisibility = () => {
      const room = roomsRef.current[activeStakeRef.current];
      if (document.visibilityState === "hidden") {
        if (room) restoreWinnersUi(room);
        else {
          clearSpinTimers();
          spinChainIdRef.current += 1;
          animatingRankRef.current = null;
          stopLottoAudio();
        }
        return;
      }
      // Return to tab: show current state silently; re-arm only after catch-up.
      if (room) {
        liveAudioArmedRef.current[room.id] = false;
        syncSpinFromRoom(room);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [isActive, clearSpinTimers, restoreWinnersUi, syncSpinFromRoom]);

  // Snapshot + WS catch-up only while the tab is active.
  useEffect(() => {
    if (!isActive || !accessToken) return;
    let cancelled = false;
    getLottoSnapshot(accessToken)
      .then((snapshot) => {
        if (cancelled) return;
        snapshot.rooms.forEach(applyRoom);
      })
      .catch(() => {
        if (!cancelled) setError(t("lotto.roomsError"));
      });
    return () => {
      cancelled = true;
    };
  }, [isActive, accessToken, applyRoom, t]);

  useEffect(() => () => {
    clearSpinTimers();
    spinChainIdRef.current += 1;
  }, [clearSpinTimers]);

  useEffect(() => {
    if (!isActive) return;
    const timer = window.setInterval(() => setNow(Date.now()), 200);
    return () => window.clearInterval(timer);
  }, [isActive]);

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
  const spinning = spinPhase === "cruising" || spinPhase === "decelerating";
  const showWinnerOverlay =
    (spinPhase === "settled" || spinPhase === "idle") && displayWinner != null;
  const wheelTransition =
    spinning && spinMs > 0 ? `transform ${spinMs}ms ${spinEasing}` : "none";
  const settledSet = useMemo(() => new Set(settledNumbers), [settledNumbers]);

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
      // Store a user-facing message once — do not wrap again with ts() in JSX.
      const text = detail ?? "";
      if (
        contested.length > 0 ||
        /already reserved|reserved by another|just taken/i.test(text)
      ) {
        setError(t(CONTESTED_SELECTION_MSG_KEY));
      } else if (/no longer open|countdown|drawing/i.test(text)) {
        setError(t("lotto.roundClosed"));
      } else if (/not enough open positions|room full/i.test(text)) {
        setError(t("lotto.roomFull"));
      } else if (/insufficient balance/i.test(text)) {
        setError(ts(text));
      } else {
        setError(detail ? ts(detail) : t("lotto.reserveFailed"));
      }
    } finally {
      submittingNumbersRef.current = null;
      setSubmitting(false);
    }
  };

  if (!room) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 bg-[#eef3f8] dark:bg-[#070d1a]">
        <Loader2 className="h-8 w-8 animate-spin text-sky-500" aria-hidden />
        <p className="text-sm font-bold text-slate-600 dark:text-white/70">
          {socketStatus === "open" ? t("common.loadingEllipsis") : t("common.connecting")}
        </p>
      </div>
    );
  }

  return (
    <div
      className="min-h-0 flex-1 overflow-y-auto bg-[#eef3f8] text-slate-950 [scrollbar-width:none] dark:bg-[#070d1a] dark:text-white"
      onPointerDownCapture={() => {
        if (soundOn) primeLottoAudioUnlock();
      }}
    >
      <style>{`
        @keyframes lotto-pop { 0% { transform: scale(.75); opacity: 0 } 100% { transform: scale(1); opacity: 1 } }
        .lotto-pop { animation: lotto-pop .45s ease-out both; }
        @keyframes lotto-slice-bounce {
          0% { transform: scale(1); }
          35% { transform: scale(1.07); }
          65% { transform: scale(0.96); }
          100% { transform: scale(1); }
        }
        .lotto-slice-bounce { transform-box: fill-box; transform-origin: center; animation: lotto-slice-bounce .55s ease-out both; }
        @media (prefers-reduced-motion: reduce) {
          .lotto-pop { animation: none; opacity: 1; transform: none; }
          .lotto-slice-bounce { animation: none; }
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
          <button
            type="button"
            onClick={() => {
              setSoundOn((value) => {
                const next = !value;
                if (next) primeLottoAudioUnlock();
                return next;
              });
            }}
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-white shadow-sm dark:bg-[#10192b]"
            aria-label={soundOn ? "Mute sound" : "Unmute sound"}
          >
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
                    if (leaving) {
                      markRevealsApplied(leaving);
                      liveAudioArmedRef.current[leaving.id] = false;
                    }
                    clearSpinTimers();
                    spinChainIdRef.current += 1;
                    animatingRankRef.current = null;
                    stopLottoAudio();
                    activeStakeRef.current = stake;
                    setActiveStake(stake);
                    setSelected([]);
                    setDisplayWinner(null);
                    setSettledNumbers([]);
                    setBounceNumber(null);
                    setDrawNotice(null);
                    setSpinPhase("idle");
                    const nextRoom = rooms[stake];
                    if (nextRoom) {
                      // Stake switch = mid-join to that room: silent catch-up, then arm.
                      liveAudioArmedRef.current[nextRoom.id] = false;
                      syncSpinFromRoom(nextRoom);
                    }
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
                {(room.status === "countdown" || room.status === "drawing" || (room.status === "completed" && displayWinner)) && (
                  <div className="pointer-events-none absolute left-1/2 top-[52%] z-20 w-44 -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-sky-300/50 bg-[#07172d]/90 px-3 py-3 text-center text-white shadow-2xl backdrop-blur">
                    {room.status === "countdown" ? (
                      <><p className="text-[8px] font-black uppercase text-sky-200">{t("lotto.roomFull")}</p><p className="text-4xl font-black">{countdown}</p><p className="text-[8px]">{t("lotto.drawingIn")}</p></>
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
                    ) : room.status === "completed" && displayWinner ? (
                      <div className="lotto-pop"><p className="text-[9px] font-black uppercase">{[t("lotto.first"), t("lotto.second"), t("lotto.third")][displayWinner.rank - 1]} {t("lotto.winner")}</p><p className="text-3xl font-black">#{displayWinner.number}</p><p className="truncate text-[10px] font-bold">{displayWinner.user_id === userId ? t("lotto.youLabel", { name: firstName }) : displayWinner.display_name}</p><p className="text-[10px] font-black">{money(displayWinner.prize)} {t("common.etb")}</p></div>
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
                      const number = index + 1;
                      // Drive glow from local settle only — never from raw server
                      // winners, and never for the number still mid-spin.
                      const won =
                        settledSet.has(number) && spinningNumber !== number;
                      const bouncing = bounceNumber === number;
                      return (
                        <g key={index} className={bouncing ? "lotto-slice-bounce" : undefined}>
                          <path
                            d={segmentPath(index)}
                            fill={COLORS[index]}
                            stroke={won ? "#fde68a" : "rgba(255,255,255,.32)"}
                            strokeWidth={won ? 5 : 1}
                          />
                          <text
                            x={label.x}
                            y={label.y}
                            fill="white"
                            fontSize="10"
                            fontWeight="900"
                            textAnchor="middle"
                            dominantBaseline="central"
                            style={{
                              transform: `rotate(${-rotation}deg)`,
                              transformOrigin: `${label.x}px ${label.y}px`,
                              transition: wheelTransition,
                            }}
                          >
                            {number}
                          </text>
                        </g>
                      );
                    })}
                  </g>
                  <circle cx="150" cy="160" r="35" fill="#09111f" stroke="#d9aa34" strokeWidth="4" />
                  <path d="M 150 3 L 164 24 L 155 42 L 145 42 L 136 24 Z" fill="#f3c84b" stroke="#5e3908" strokeWidth="2" />
                </svg>
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                {[1, 2, 3].map((rank) => {
                  const winner = room.winners.find((item) => item.rank === rank);
                  const spinComplete =
                    Boolean(winner) &&
                    settledSet.has(winner!.number) &&
                    spinningNumber !== winner!.number;
                  const highlighted =
                    spinComplete &&
                    displayWinner?.rank === rank &&
                    (spinPhase === "settled" || spinPhase === "idle");
                  return (
                    <div
                      key={rank}
                      className={`rounded-lg border p-1.5 text-center ${
                        highlighted
                          ? "border-amber-400 bg-amber-50 dark:bg-amber-400/10"
                          : "border-slate-300 bg-white/70 dark:border-white/10 dark:bg-white/5"
                      }`}
                    >
                      <p className="text-[8px] font-black uppercase opacity-50">
                        {rank === 1 ? t("lotto.rank1Short") : rank === 2 ? t("lotto.rank2Short") : t("lotto.rank3Short")}{" "}
                        {t("lotto.winner")}
                      </p>
                      <p className="text-xs font-black">
                        {spinComplete && winner
                          ? `#${winner.number} · ${winner.user_id === userId ? t("common.you") : winner.display_name}`
                          : "—"}
                      </p>
                    </div>
                  );
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
                  // Never amber the pad from raw winners while that number spins.
                  const winner =
                    settledSet.has(number) && spinningNumber !== number
                      ? room.winners.find((item) => item.number === number)
                      : undefined;
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
                      <span className="max-w-full truncate px-0.5 text-[7px] font-black uppercase tracking-tight opacity-70">
                        {winner
                          ? t("lotto.rank", { rank: winner.rank })
                          : chosen
                            ? t("lotto.selected")
                            : owner?.user_id === userId
                              ? t("common.you")
                              : owner
                                ? (owner.label5 ?? owner.display_name.slice(0, 5) ?? owner.initials)
                                : t("lotto.open")}
                      </span>
                      {chosen && <Check size={9} className="absolute right-1 top-1" />}
                    </button>
                  );
                })}
              </div>
              {error && <p className="mt-2 rounded-md bg-rose-50 p-2 text-[9px] font-semibold text-rose-700 dark:bg-rose-400/10 dark:text-rose-200">{error}</p>}
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
