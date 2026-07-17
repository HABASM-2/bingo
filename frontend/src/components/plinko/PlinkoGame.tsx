import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CircleDot, Coins, History, Infinity as InfinityIcon, Loader2, Volume2, VolumeX } from "lucide-react";
import {
  getPlinkoHistory,
  getPlinkoPresets,
  playPlinko,
} from "../../services/plinko";
import type {
  PlinkoHistoryPage,
  PlinkoPlay,
  PlinkoPresets,
  PlinkoRisk,
} from "../../services/plinko";
import { useI18n } from "../../i18n";

interface PlinkoGameProps {
  isActive?: boolean;
  walletBalance: string | null;
  onBalanceChange: (balance: string) => void;
}

type Mode = "manual" | "auto";
type Risk = PlinkoRisk;
type View = "game" | "history";
type Peg = { x: number; y: number; radius: number };
type TrailPoint = { x: number; y: number; alpha: number };
type Ball = {
  id: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  age: number;
  bet: number;
  manual: boolean;
  targetSlot: number;
  result: PlinkoPlay;
  sequence: number;
  trail: TrailPoint[];
  lastPeg: number;
  pegCooldown: number;
};
type Wall = { x1: number; y1: number; x2: number; y2: number };
type Board = {
  width: number;
  height: number;
  left: number;
  right: number;
  pegTop: number;
  slotTop: number;
  slotBottom: number;
  slotWidth: number;
  slotOrigin: number;
  pegs: Peg[];
  walls: [Wall, Wall];
  topGaps: [number, number];
};

const ROW_OPTIONS = [8, 10, 12, 14, 16] as const;
const FIXED_STEP = 1 / 120;
const MAX_BALLS = 28;
const MAX_REQUESTS = 3;

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const money = (value: number) =>
  value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

/** Show API multipliers accurately (trim zeros; keep ≥1 decimal so 1.0x ≠ 0.99x). */
const multiplierLabel = (value: number | string) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const trimmed = n.toFixed(2).replace(/\.?0+$/, "");
  return `${trimmed.includes(".") ? trimmed : `${trimmed}.0`}x`;
};

const emptyMultipliers = (rows: number) => Array.from({ length: rows + 1 }, () => 1);

function wallXAtY(wall: Wall, y: number) {
  const span = wall.y2 - wall.y1;
  if (Math.abs(span) < 1e-6) return wall.x1;
  const t = clamp((y - wall.y1) / span, 0, 1);
  return wall.x1 + t * (wall.x2 - wall.x1);
}

function collideWall(ball: Ball, wall: Wall, inward: 1 | -1, restitution: number) {
  const wx = wallXAtY(wall, ball.y);
  const limit = wx + inward * ball.radius;
  const outside = inward === 1 ? ball.x < limit : ball.x > limit;
  if (!outside) return;

  ball.x = limit;
  const dx = wall.x2 - wall.x1;
  const dy = wall.y2 - wall.y1;
  const length = Math.hypot(dx, dy) || 1;
  // Inward normal: left wall uses (dy, -dx), right wall uses (-dy, dx).
  const nx = (inward === 1 ? dy : -dy) / length;
  const ny = (inward === 1 ? -dx : dx) / length;
  const normalVelocity = ball.vx * nx + ball.vy * ny;
  if (normalVelocity < 0) {
    const impulse = -(1 + restitution) * normalVelocity;
    ball.vx += impulse * nx;
    ball.vy += impulse * ny;
  }
}

function makeBoard(width: number, height: number, rows: number): Board {
  const left = Math.max(12, width * 0.038);
  const right = width - left;
  const slotTop = height - 35;
  const slotBottom = height - 8;
  const pegTop = 48;
  // slots = rows + 1 gaps between bottom pegs (bottom has rows + 2 pegs)
  const slotWidth = (right - left) / (rows + 1);
  const rowGap = (slotTop - pegTop - 9) / Math.max(1, rows - 1);
  const pegRadius = clamp(slotWidth * 0.105, 2, 3.25);
  const pegs: Peg[] = [];
  const center = width / 2;
  let topFirstX = center;
  let topLastX = center;
  let bottomFirstX = left;
  let bottomLastX = right;

  for (let row = 0; row < rows; row += 1) {
    const count = row + 3; // top row starts with 3 pegs
    const y = pegTop + row * rowGap;
    const start = center - ((count - 1) * slotWidth) / 2;
    if (row === 0) {
      topFirstX = start;
      topLastX = start + (count - 1) * slotWidth;
    }
    if (row === rows - 1) {
      bottomFirstX = start;
      bottomLastX = start + (count - 1) * slotWidth;
    }
    for (let column = 0; column < count; column += 1) {
      pegs.push({ x: start + column * slotWidth, y, radius: pegRadius });
    }
  }

  const wallPad = pegRadius + 2.5;
  const wallTop = pegTop - pegRadius - 6;
  const wallBottom = slotTop + 4;
  const walls: [Wall, Wall] = [
    {
      x1: topFirstX - wallPad,
      y1: wallTop,
      x2: bottomFirstX - wallPad,
      y2: wallBottom,
    },
    {
      x1: topLastX + wallPad,
      y1: wallTop,
      x2: bottomLastX + wallPad,
      y2: wallBottom,
    },
  ];

  return {
    width,
    height,
    left,
    right,
    pegTop,
    slotTop,
    slotBottom,
    slotWidth,
    slotOrigin: bottomFirstX,
    pegs,
    walls,
    topGaps: [topFirstX + slotWidth / 2, topFirstX + slotWidth * 1.5],
  };
}

function playTone(kind: "drop" | "peg" | "land", enabled: boolean) {
  if (!enabled) return;
  try {
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    const now = context.currentTime;
    const frequency = kind === "drop" ? 240 : kind === "peg" ? 480 : 680;
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(frequency, now);
    oscillator.frequency.exponentialRampToValueAtTime(frequency * 0.72, now + 0.09);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(kind === "peg" ? 0.018 : 0.045, now + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.11);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.12);
    oscillator.addEventListener("ended", () => void context.close());
  } catch {
    // Audio feedback is optional in restricted embedded browsers.
  }
}

export function PlinkoGame({
  isActive = true,
  walletBalance,
  onBalanceChange,
}: PlinkoGameProps) {
  const { t, ts } = useI18n();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const boardHostRef = useRef<HTMLDivElement>(null);
  const boardRef = useRef<Board>(makeBoard(360, 335, 16));
  const ballsRef = useRef<Ball[]>([]);
  const hitPegsRef = useRef<Map<number, number>>(new Map());
  const slotFlashRef = useRef<Map<number, number>>(new Map());
  const nextBallIdRef = useRef(1);
  const lastTimeRef = useRef<number | null>(null);
  const accumulatorRef = useRef(0);
  const autoTimerRef = useRef<number | null>(null);
  const historyTimerRef = useRef<number | null>(null);
  const autoRemainingRef = useRef(0);
  const autoRunningRef = useRef(false);
  const manualInFlightRef = useRef(false);
  const requestsRef = useRef(0);
  const mutedRef = useRef(false);
  const betRef = useRef(0);
  const rowsRef = useRef(16);
  const riskRef = useRef<Risk>("medium");
  const multipliersRef = useRef(emptyMultipliers(16));
  const presetsRef = useRef<PlinkoPresets | null>(null);
  const playSequenceRef = useRef(0);
  const nextBalanceSequenceRef = useRef(1);
  const resolvedBalancesRef = useRef(new Map<number, string | null>());

  const [view, setView] = useState<View>("game");
  const [mode, setMode] = useState<Mode>("manual");
  const [rows, setRows] = useState(16);
  const [risk, setRisk] = useState<Risk>("medium");
  const [betAmount, setBetAmount] = useState("0.00");
  const [presets, setPresets] = useState<PlinkoPresets | null>(null);
  const [muted, setMuted] = useState(false);
  const [manualInFlight, setManualInFlight] = useState(false);
  const [requestCount, setRequestCount] = useState(0);
  const [autoRunning, setAutoRunning] = useState(false);
  const [autoCount, setAutoCount] = useState("10");
  const [infinite, setInfinite] = useState(false);
  const [autoPlaced, setAutoPlaced] = useState(0);
  const [ballsDropped, setBallsDropped] = useState(0);
  const [lastHit, setLastHit] = useState<number | null>(null);
  const [sessionNet, setSessionNet] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<PlinkoHistoryPage | null>(null);
  const [historyPage, setHistoryPage] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [isDark, setIsDark] = useState(
    () => typeof document !== "undefined" && document.documentElement.dataset.theme === "dark",
  );

  mutedRef.current = muted;
  rowsRef.current = rows;
  riskRef.current = risk;
  multipliersRef.current = presets?.tables[risk]?.[String(rows)]?.map(Number)
    ?? emptyMultipliers(rows);

  const stopAuto = useCallback(() => {
    if (autoTimerRef.current !== null) {
      window.clearInterval(autoTimerRef.current);
      autoTimerRef.current = null;
    }
    autoRunningRef.current = false;
    autoRemainingRef.current = 0;
    setAutoRunning(false);
  }, []);

  const resetSession = useCallback(() => {
    stopAuto();
    ballsRef.current = [];
    hitPegsRef.current.clear();
    slotFlashRef.current.clear();
    manualInFlightRef.current = false;
    setManualInFlight(false);
    setAutoPlaced(0);
    setBallsDropped(0);
    setLastHit(null);
    setSessionNet(0);
  }, [stopAuto]);

  const refreshHistory = useCallback(async (page = historyPage) => {
    setHistoryLoading(true);
    try {
      setHistory(await getPlinkoHistory(10, page * 10));
      setHistoryPage(page);
    } catch {
      setError(t("plinko.historyError"));
    } finally {
      setHistoryLoading(false);
    }
  }, [historyPage]);

  const resolveBall = useCallback((ball: Ball, slot: number) => {
    const multiplier = Number(ball.result.multiplier);
    setLastHit(multiplier);
    setSessionNet((value) => value + Number(ball.result.net));
    slotFlashRef.current.set(slot, 1);
    resolvedBalancesRef.current.set(ball.sequence, ball.result.balance);
    while (resolvedBalancesRef.current.has(nextBalanceSequenceRef.current)) {
      const next = resolvedBalancesRef.current.get(nextBalanceSequenceRef.current);
      resolvedBalancesRef.current.delete(nextBalanceSequenceRef.current);
      nextBalanceSequenceRef.current += 1;
      if (next !== null && next !== undefined) onBalanceChange(next);
    }
    if (ball.manual) {
      manualInFlightRef.current = false;
      setManualInFlight(false);
    }
    if (historyTimerRef.current !== null) window.clearTimeout(historyTimerRef.current);
    historyTimerRef.current = window.setTimeout(() => void refreshHistory(0), 800);
    playTone("land", !mutedRef.current);
  }, [onBalanceChange, refreshHistory]);

  const requestBall = useCallback(async (manual: boolean) => {
    if (!isActive || ballsRef.current.length >= MAX_BALLS) return false;
    if (manual && manualInFlightRef.current) return false;
    if (requestsRef.current >= MAX_REQUESTS) return false;
    const bet = betRef.current;
    const balance = Number(walletBalance);
    if (!Number.isFinite(bet) || bet < 0 || (bet > 0 && (!Number.isFinite(balance) || balance < bet))) {
      setError(t("plinko.insufficient"));
      return false;
    }
    if (manual) {
      manualInFlightRef.current = true;
      setManualInFlight(true);
    }
    requestsRef.current += 1;
    setRequestCount(requestsRef.current);
    setError(null);
    try {
      const result = await playPlinko(bet.toFixed(2), riskRef.current, rowsRef.current);
      const board = boardRef.current;
      const gapCenter = board.topGaps[Math.random() < 0.5 ? 0 : 1];
      playSequenceRef.current += 1;
      ballsRef.current.push({
        id: nextBallIdRef.current++,
        x: gapCenter + (Math.random() - 0.5) * board.slotWidth * 0.18,
        y: Math.max(12, board.pegTop - 28),
        vx: (Math.random() - 0.5) * 7,
        vy: 12,
        radius: clamp(board.slotWidth * 0.22, 4.2, 6),
        age: 0,
        bet,
        manual,
        targetSlot: result.slot_index,
        result,
        sequence: playSequenceRef.current,
        trail: [],
        lastPeg: -1,
        pegCooldown: 0,
      });
      setBallsDropped((value) => value + 1);
      setLastHit(null);
      playTone("drop", !mutedRef.current);
      return true;
    } catch (reason) {
      const detail = (reason as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(detail ? ts(detail) : t("plinko.playFailed"));
      if (manual) {
        manualInFlightRef.current = false;
        setManualInFlight(false);
      }
      stopAuto();
      return false;
    } finally {
      requestsRef.current -= 1;
      setRequestCount(requestsRef.current);
    }
  }, [isActive, walletBalance, stopAuto]);

  const spawnAutoBall = useCallback(async () => {
    if (!autoRunningRef.current) return;
    if (requestsRef.current >= MAX_REQUESTS) return;
    if (autoRemainingRef.current <= 0) {
      stopAuto();
      return;
    }
    if (Number.isFinite(autoRemainingRef.current)) {
      autoRemainingRef.current -= 1;
    }
    const placed = await requestBall(false);
    if (!placed) {
      return;
    }
    setAutoPlaced((value) => value + 1);
    if (autoRemainingRef.current <= 0) stopAuto();
  }, [requestBall, stopAuto]);

  const startAuto = useCallback(() => {
    if (autoRunningRef.current || !isActive) return;
    const count = Math.max(1, Math.floor(Number(autoCount) || 1));
    autoRemainingRef.current = infinite ? Number.POSITIVE_INFINITY : count;
    autoRunningRef.current = true;
    setAutoRunning(true);
    setAutoPlaced(0);
    void spawnAutoBall();
    if (autoRunningRef.current) {
      autoTimerRef.current = window.setInterval(() => void spawnAutoBall(), 520);
    }
  }, [autoCount, infinite, isActive, spawnAutoBall]);

  const applyBet = useCallback((next: number) => {
    const safe = clamp(Math.round(next * 100) / 100, 0, Number(presetsRef.current?.max ?? 500));
    betRef.current = safe;
    setBetAmount(safe.toFixed(2));
  }, []);

  const commitBetInput = useCallback(() => {
    applyBet(Number(betAmount) || 0);
  }, [applyBet, betAmount]);

  const changeMode = useCallback((nextMode: Mode) => {
    if (nextMode === mode) return;
    stopAuto();
    setMode(nextMode);
  }, [mode, stopAuto]);

  const changeRows = useCallback((nextRows: number) => {
    if (nextRows === rows) return;
    setRows(nextRows);
    resetSession();
  }, [resetSession, rows]);

  const changeRisk = useCallback((nextRisk: Risk) => {
    if (nextRisk === risk) return;
    setRisk(nextRisk);
    resetSession();
  }, [resetSession, risk]);

  useEffect(() => {
    let cancelled = false;
    getPlinkoPresets()
      .then((value) => {
        if (cancelled) return;
        presetsRef.current = value;
        setPresets(value);
      })
      .catch(() => {
        if (!cancelled) setError(t("plinko.settingsError"));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const syncTheme = () => setIsDark(root.dataset.theme === "dark");
    syncTheme();
    const observer = new MutationObserver(syncTheme);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (view === "history") void refreshHistory(historyPage);
  }, [view, historyPage, refreshHistory]);

  useEffect(() => {
    if (!isActive) stopAuto();
  }, [isActive, stopAuto]);

  useEffect(() => () => {
    stopAuto();
    if (historyTimerRef.current !== null) window.clearTimeout(historyTimerRef.current);
  }, [stopAuto]);

  useEffect(() => {
    if (view !== "game") return;
    const host = boardHostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;

    const resize = () => {
      const rect = host.getBoundingClientRect();
      const width = Math.max(280, rect.width);
      const height = Math.max(275, rect.height);
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      boardRef.current = makeBoard(width, height, rowsRef.current);
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    return () => observer.disconnect();
  }, [rows, view]);

  useEffect(() => {
    if (!isActive || view !== "game") {
      lastTimeRef.current = null;
      return;
    }

    let frame = 0;
    let lastPegSound = 0;

    const update = (step: number) => {
      const board = boardRef.current;
      const gravity = riskRef.current === "high" ? 650 : riskRef.current === "low" ? 570 : 610;
      const resolved: { ball: Ball; slot: number }[] = [];

      hitPegsRef.current.forEach((life, index) => {
        const next = life - step * 5;
        if (next <= 0) hitPegsRef.current.delete(index);
        else hitPegsRef.current.set(index, next);
      });
      slotFlashRef.current.forEach((life, index) => {
        const next = life - step * 2.6;
        if (next <= 0) slotFlashRef.current.delete(index);
        else slotFlashRef.current.set(index, next);
      });

      for (const ball of ballsRef.current) {
        ball.age += step;
        ball.pegCooldown = Math.max(0, ball.pegCooldown - step);
        ball.trail = [
          { x: ball.x, y: ball.y, alpha: 0.55 },
          ...ball.trail.slice(0, 4).map((point) => ({ ...point, alpha: point.alpha * 0.7 })),
        ];
        ball.vy += gravity * step;
        ball.vx *= Math.pow(0.995, step * 120);
        // The server has already committed the outcome. Gradually bias the
        // trajectory toward that slot while retaining normal peg collisions.
        const progress = clamp(
          (ball.y - board.pegTop) / (board.slotTop - board.pegTop),
          0,
          1,
        );
        const targetX = board.slotOrigin + (ball.targetSlot + 0.5) * board.slotWidth;
        const targetDelta = targetX - ball.x;
        ball.vx += clamp(targetDelta * (1.4 + progress * 7), -95, 95) * step;
        ball.x += targetDelta * Math.pow(progress, 5) * step * 3.2;
        ball.x += ball.vx * step;
        ball.y += ball.vy * step;

        const wallRestitution = riskRef.current === "high" ? 0.58 : 0.5;
        collideWall(ball, board.walls[0], 1, wallRestitution);
        collideWall(ball, board.walls[1], -1, wallRestitution);

        for (let index = 0; index < board.pegs.length; index += 1) {
          const peg = board.pegs[index];
          const dx = ball.x - peg.x;
          const dy = ball.y - peg.y;
          const minimum = ball.radius + peg.radius;
          const distanceSquared = dx * dx + dy * dy;
          if (distanceSquared >= minimum * minimum) continue;

          const distance = Math.sqrt(distanceSquared) || 0.001;
          const nx = dx / distance;
          const ny = dy / distance;
          const overlap = minimum - distance;
          ball.x += nx * overlap;
          ball.y += ny * overlap;
          const normalVelocity = ball.vx * nx + ball.vy * ny;
          if (normalVelocity < 0) {
            const restitution = riskRef.current === "high" ? 0.62 : 0.54;
            const impulse = -(1 + restitution) * normalVelocity;
            ball.vx += impulse * nx;
            ball.vy += impulse * ny;
            if (Math.abs(nx) < 0.08) {
              ball.vx += (Math.random() < 0.5 ? -1 : 1) * (riskRef.current === "high" ? 30 : 20);
            }
          }
          if (ball.lastPeg !== index || ball.pegCooldown <= 0) {
            ball.lastPeg = index;
            ball.pegCooldown = 0.045;
            hitPegsRef.current.set(index, 1);
            const now = performance.now();
            if (now - lastPegSound > 65) {
              lastPegSound = now;
              playTone("peg", !mutedRef.current);
            }
          }
        }

        collideWall(ball, board.walls[0], 1, wallRestitution);
        collideWall(ball, board.walls[1], -1, wallRestitution);

        if (ball.y + ball.radius >= board.slotTop + 9 || ball.age > 9) {
          resolved.push({ ball, slot: ball.targetSlot });
        }
      }

      if (resolved.length > 0) {
        const resolvedIds = new Set(resolved.map(({ ball }) => ball.id));
        ballsRef.current = ballsRef.current.filter((ball) => !resolvedIds.has(ball.id));
        resolved.forEach(({ ball, slot }) => resolveBall(ball, slot));
      }
    };

    const draw = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const context = canvas.getContext("2d");
      if (!context) return;
      const board = boardRef.current;
      const ratio = canvas.width / board.width;
      const multipliers = multipliersRef.current;
      const palette = isDark
        ? {
            board: "#0a202d",
            glowStart: "rgba(26, 95, 117, .12)",
            glowEnd: "rgba(5, 20, 30, 0)",
            peg: "#e8f8fa",
            pegGlow: "#8fe8f2",
            hitPeg: "#b9ff7a",
            hitGlow: "#78e43c",
            slotText: "#092313",
            trail: "#76e83c",
            ball: "#80ec45",
            ballGlow: "#7df044",
            ballStroke: "rgba(226,255,208,.8)",
          }
        : {
            board: "#f0f9ff",
            glowStart: "rgba(14, 165, 233, .14)",
            glowEnd: "rgba(224, 242, 254, 0)",
            peg: "#0f6075",
            pegGlow: "rgba(14, 116, 144, .3)",
            hitPeg: "#65a30d",
            hitGlow: "rgba(101, 163, 13, .55)",
            slotText: "#052e16",
            trail: "#65a30d",
            ball: "#4d7c0f",
            ballGlow: "rgba(77, 124, 15, .5)",
            ballStroke: "rgba(236,252,203,.95)",
          };

      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, board.width, board.height);
      context.fillStyle = palette.board;
      context.fillRect(0, 0, board.width, board.height);

      const boardGlow = context.createRadialGradient(
        board.width / 2,
        board.height * 0.45,
        5,
        board.width / 2,
        board.height * 0.45,
        board.width * 0.6,
      );
      boardGlow.addColorStop(0, palette.glowStart);
      boardGlow.addColorStop(1, palette.glowEnd);
      context.fillStyle = boardGlow;
      context.fillRect(0, 0, board.width, board.height);

      board.pegs.forEach((peg, index) => {
        const flash = hitPegsRef.current.get(index) ?? 0;
        context.beginPath();
        context.fillStyle = flash > 0 ? palette.hitPeg : palette.peg;
        context.shadowColor = flash > 0 ? palette.hitGlow : palette.pegGlow;
        context.shadowBlur = flash > 0 ? 9 : 3;
        context.arc(peg.x, peg.y, peg.radius + flash * 0.7, 0, Math.PI * 2);
        context.fill();
      });
      context.shadowBlur = 0;

      multipliers.forEach((multiplier, index) => {
        const x = board.slotOrigin + index * board.slotWidth;
        const flash = slotFlashRef.current.get(index) ?? 0;
        const edgeRatio = Math.abs(index - (multipliers.length - 1) / 2) /
          ((multipliers.length - 1) / 2);
        const hue = 91 - edgeRatio * 18;
        context.fillStyle = flash > 0
          ? `hsl(${hue} 92% 70%)`
          : `hsl(${hue} 78% ${44 + edgeRatio * 8}%)`;
        const gap = Math.max(1.2, board.slotWidth * 0.075);
        const radius = Math.min(3, board.slotWidth * 0.16);
        context.beginPath();
        context.roundRect(
          x + gap / 2,
          board.slotTop,
          board.slotWidth - gap,
          board.slotBottom - board.slotTop,
          radius,
        );
        context.fill();
        context.fillStyle = palette.slotText;
        const label = multiplierLabel(multiplier);
        const labelScale = label.length >= 7 ? 0.24 : label.length >= 6 ? 0.27 : 0.31;
        context.font = `800 ${clamp(board.slotWidth * labelScale, 5, 9)}px system-ui`;
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillText(
          label,
          x + board.slotWidth / 2,
          board.slotTop + (board.slotBottom - board.slotTop) / 2,
          board.slotWidth - Math.max(1, gap),
        );
      });

      for (const ball of ballsRef.current) {
        ball.trail.forEach((point, index) => {
          context.globalAlpha = point.alpha * (1 - index / 7);
          context.fillStyle = palette.trail;
          context.beginPath();
          context.arc(point.x, point.y, Math.max(1.4, ball.radius * (0.8 - index * 0.09)), 0, Math.PI * 2);
          context.fill();
        });
        context.globalAlpha = 1;
        context.shadowColor = palette.ballGlow;
        context.shadowBlur = 13;
        context.fillStyle = palette.ball;
        context.beginPath();
        context.arc(ball.x, ball.y, ball.radius, 0, Math.PI * 2);
        context.fill();
        context.shadowBlur = 0;
        context.strokeStyle = palette.ballStroke;
        context.lineWidth = 1;
        context.stroke();
      }
      context.globalAlpha = 1;
    };

    const animate = (now: number) => {
      const previous = lastTimeRef.current ?? now;
      const elapsed = Math.min((now - previous) / 1000, 0.05);
      lastTimeRef.current = now;
      accumulatorRef.current += elapsed;
      while (accumulatorRef.current >= FIXED_STEP) {
        update(FIXED_STEP);
        accumulatorRef.current -= FIXED_STEP;
      }
      draw();
      frame = requestAnimationFrame(animate);
    };

    frame = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(frame);
      lastTimeRef.current = null;
      accumulatorRef.current = 0;
    };
  }, [isActive, isDark, resolveBall, view]);

  const parsedBet = Number(betAmount) || 0;
  const walletNumber = Number(walletBalance);
  const controlsLocked = autoRunning || requestCount > 0 || ballsRef.current.length > 0;
  const actionDisabled = mode === "auto" && autoRunning
    ? false
    : !isActive ||
      !presets ||
      parsedBet < 0 ||
      (parsedBet > 0 && (!Number.isFinite(walletNumber) || parsedBet > walletNumber)) ||
      (mode === "manual" && manualInFlight);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-slate-100 text-slate-900 transition-colors duration-300 [scrollbar-width:none] dark:bg-[#102a35] dark:text-slate-100 [&::-webkit-scrollbar]:hidden">
      <style>{`
        .plinko-number::-webkit-inner-spin-button,
        .plinko-number::-webkit-outer-spin-button { appearance: none; margin: 0; }
        .plinko-number { appearance: textfield; }
      `}</style>
      <div className="mx-auto flex min-h-full w-full max-w-[460px] flex-col px-3 pb-4 pt-2">
        <header className="mb-2 flex h-11 shrink-0 items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-400/10 dark:text-emerald-300 dark:ring-emerald-300/20">
              <CircleDot size={19} />
            </span>
            <div>
              <h1 className="text-sm font-extrabold tracking-wide">{t("plinko.title")}</h1>
              <p className="text-[9px] font-semibold uppercase tracking-[0.13em] text-slate-500 dark:text-slate-400">
                {t("plinko.verified")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex h-9 items-center gap-1.5 rounded-xl bg-white px-3 shadow-sm ring-1 ring-slate-200 dark:bg-[#0a202d] dark:shadow-none dark:ring-white/7">
              <Coins size={14} className="text-cyan-700 dark:text-cyan-300" />
              <span className="text-xs font-bold tabular-nums">
                {walletBalance == null ? "—" : money(Number(walletBalance))}
              </span>
              <span className="text-[8px] font-bold uppercase text-slate-500 dark:text-slate-500">{t("common.etb")}</span>
            </div>
            <button
              type="button"
              onClick={() => setMuted((value) => !value)}
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-slate-600 shadow-sm ring-1 ring-slate-200 transition active:scale-95 dark:bg-[#0a202d] dark:text-slate-400 dark:shadow-none dark:ring-white/7"
              aria-label={muted ? t("plinko.enableSound") : t("plinko.muteSound")}
            >
              {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
            </button>
          </div>
        </header>

        <div className="mb-2 grid h-9 grid-cols-2 rounded-lg bg-slate-200 p-1 dark:bg-[#0a202d]">
          {(["game", "history"] as const).map((item) => (
            <button
              key={item}
              type="button"
              disabled={item === "history" && controlsLocked}
              onClick={() => setView(item)}
              className={`flex items-center justify-center gap-1.5 rounded-md text-[10px] font-bold uppercase tracking-wide disabled:opacity-40 ${
                view === item ? "bg-white text-slate-900 shadow-sm dark:bg-[#3b5c6c] dark:text-white" : "text-slate-500 dark:text-slate-400"
              }`}
            >
              {item === "history" && <History size={13} />}
              {item === "game" ? t("plinko.game") : t("plinko.myBets")}
            </button>
          ))}
        </div>

        {error && (
          <div className="mb-2 flex items-center gap-2 rounded-lg bg-rose-100 px-3 py-2 text-[10px] font-semibold text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
            <AlertCircle size={14} /> {ts(error)}
          </div>
        )}

        {view === "game" ? (
        <>
        <section className="overflow-hidden rounded-xl border border-sky-200 bg-sky-50 shadow-[0_10px_24px_rgba(15,23,42,.10)] dark:border-cyan-100/5 dark:bg-[#0a202d] dark:shadow-[0_12px_30px_rgba(0,0,0,.18)]">
          <div
            ref={boardHostRef}
            className="relative h-[clamp(278px,82vw,350px)] w-full touch-none select-none"
          >
            <canvas
              ref={canvasRef}
              className="absolute inset-0 h-full w-full"
              aria-label={t("plinko.boardAria", { rows, balls: ballsRef.current.length })}
            />
            <div className="pointer-events-none absolute left-2 top-2 rounded-md bg-white/75 px-2 py-1 text-[8px] font-bold uppercase tracking-wider text-slate-600 shadow-sm dark:bg-black/15 dark:text-slate-400 dark:shadow-none">
              {t("plinko.rowsRisk", { rows, risk })}
            </div>
          </div>
        </section>

        <button
          type="button"
          disabled={actionDisabled}
          onClick={() => {
            if (mode === "manual") void requestBall(true);
            else if (autoRunning) stopAuto();
            else startAuto();
          }}
          className={`mt-2 flex h-12 w-full shrink-0 items-center justify-center rounded-lg text-xs font-extrabold uppercase tracking-[0.08em] text-white shadow-lg transition active:scale-[.99] disabled:cursor-not-allowed disabled:opacity-45 ${
            mode === "auto" && autoRunning
              ? "bg-rose-600 shadow-rose-950/20"
              : "bg-[#1473d2] shadow-blue-950/25 hover:bg-[#197bdd]"
          }`}
        >
          {mode === "manual"
            ? requestCount > 0
              ? <><Loader2 size={15} className="mr-2 animate-spin" />{t("plinko.verifying")}</>
              : manualInFlight ? t("plinko.ballInPlay") : parsedBet === 0 ? t("plinko.dropDemo") : t("plinko.placeBet")
            : autoRunning ? t("plinko.stopAuto") : t("plinko.startAuto")}
        </button>

        <div className="mt-2 grid grid-cols-3 rounded-lg border border-slate-200 bg-white py-2 text-center shadow-sm dark:border-white/5 dark:bg-[#0d2531] dark:shadow-none">
          <div>
            <p className="text-[8px] font-bold uppercase tracking-wider text-slate-500">{t("plinko.dropped")}</p>
            <p className="mt-0.5 text-xs font-extrabold tabular-nums">{ballsDropped}</p>
          </div>
          <div className="border-x border-slate-200 dark:border-white/7">
            <p className="text-[8px] font-bold uppercase tracking-wider text-slate-500">{t("plinko.lastHit")}</p>
            <p className="mt-0.5 text-xs font-extrabold text-lime-700 dark:text-lime-300">{lastHit === null ? "—" : multiplierLabel(lastHit)}</p>
          </div>
          <div>
            <p className="text-[8px] font-bold uppercase tracking-wider text-slate-500">{t("plinko.sessionNet")}</p>
            <p className={`mt-0.5 text-xs font-extrabold tabular-nums ${sessionNet >= 0 ? "text-cyan-700 dark:text-cyan-300" : "text-rose-600 dark:text-rose-300"}`}>
              {sessionNet > 0 ? "+" : ""}{money(sessionNet)}
            </p>
          </div>
        </div>

        <section className="mt-2 space-y-2.5 rounded-xl border border-slate-200 bg-white/70 p-2.5 shadow-sm dark:border-white/5 dark:bg-[#102a35] dark:shadow-none">
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label htmlFor="plinko-bet" className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">{t("plinko.betAmount")}</label>
              <span className="text-[9px] font-medium text-slate-500">
                {parsedBet === 0 ? t("plinko.demoHint") : t("plinko.paidHint")}
              </span>
            </div>
            <div className="flex h-11 overflow-hidden rounded-lg border border-slate-200 bg-white focus-within:border-cyan-500 dark:border-white/7 dark:bg-[#0a202d] dark:focus-within:border-cyan-400/35">
              <div className="flex min-w-0 flex-1 items-center px-3">
                <input
                  id="plinko-bet"
                  className="plinko-number min-w-0 flex-1 bg-transparent text-sm font-semibold tabular-nums text-slate-900 outline-none disabled:text-slate-400 dark:text-slate-100"
                  type="number"
                  min="0"
                  max={presets?.max ?? "500"}
                  step="0.1"
                  inputMode="decimal"
                  value={betAmount}
                  disabled={controlsLocked}
                  onChange={(event) => {
                    setBetAmount(event.target.value);
                    const value = Number(event.target.value);
                    if (Number.isFinite(value) && value >= 0) betRef.current = value;
                  }}
                  onBlur={commitBetInput}
                  aria-label={t("plinko.betAria")}
                />
                <Coins size={15} className="text-cyan-700 dark:text-cyan-300" />
              </div>
              <button
                type="button"
                disabled={controlsLocked}
                onClick={() => applyBet((Number(betAmount) || 0) / 2)}
                className="w-12 border-l border-slate-200 bg-slate-50 text-xs font-bold text-slate-700 active:bg-slate-100 dark:border-white/7 dark:bg-white/5 dark:text-slate-300 dark:active:bg-white/10"
              >
                ½
              </button>
              <button
                type="button"
                disabled={controlsLocked}
                onClick={() => applyBet((Number(betAmount) || Number(presets?.min ?? 1)) * 2)}
                className="w-12 border-l border-slate-200 bg-slate-50 text-xs font-bold text-slate-700 active:bg-slate-100 dark:border-white/7 dark:bg-white/5 dark:text-slate-300 dark:active:bg-white/10"
              >
                2×
              </button>
            </div>
          </div>

          <div>
            <label htmlFor="plinko-risk" className="mb-1.5 block text-[11px] font-semibold text-slate-700 dark:text-slate-300">{t("plinko.difficulty")}</label>
            <select
              id="plinko-risk"
              value={risk}
              disabled={controlsLocked}
              onChange={(event) => changeRisk(event.target.value as Risk)}
              className="h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold capitalize text-slate-800 outline-none focus:border-cyan-500 disabled:text-slate-400 dark:border-white/7 dark:bg-[#0a202d] dark:text-slate-200 dark:focus:border-cyan-400/35"
            >
              <option value="low">{t("plinko.easy")}</option>
              <option value="medium">{t("plinko.medium")}</option>
              <option value="high">{t("plinko.hard")}</option>
            </select>
          </div>

          <div>
            <label htmlFor="plinko-rows" className="mb-1.5 block text-[11px] font-semibold text-slate-700 dark:text-slate-300">{t("plinko.rows")}</label>
            <select
              id="plinko-rows"
              value={rows}
              disabled={controlsLocked}
              onChange={(event) => changeRows(Number(event.target.value))}
              className="h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800 outline-none focus:border-cyan-500 disabled:text-slate-400 dark:border-white/7 dark:bg-[#0a202d] dark:text-slate-200 dark:focus:border-cyan-400/35"
            >
              {ROW_OPTIONS.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </div>

          <div className="grid h-11 grid-cols-2 rounded-full bg-slate-200 p-1 dark:bg-[#091e29]">
            {(["manual", "auto"] as const).map((item) => (
              <button
                key={item}
                type="button"
                disabled={controlsLocked}
                onClick={() => changeMode(item)}
                className={`rounded-full text-xs font-bold capitalize transition ${
                  mode === item
                    ? "bg-white text-slate-900 shadow-sm dark:bg-[#3b5c6c] dark:text-white"
                    : "text-slate-500 active:text-slate-800 dark:text-slate-400 dark:active:text-slate-200"
                }`}
              >
                {item}
              </button>
            ))}
          </div>

          {mode === "auto" && (
            <div className="pb-1">
              <div className="mb-1.5 flex items-center justify-between">
                <label htmlFor="plinko-count" className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">{t("plinko.numberOfBets")}</label>
                {autoRunning && (
                  <span className="text-[9px] font-bold uppercase tracking-wider text-lime-700 dark:text-lime-300">
                    {t("plinko.placed", { count: autoPlaced })}
                  </span>
                )}
              </div>
              <div className="flex h-11 overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-white/7 dark:bg-[#0a202d]">
                <input
                  id="plinko-count"
                  className="plinko-number min-w-0 flex-1 bg-transparent px-3 text-sm font-semibold tabular-nums text-slate-900 outline-none disabled:text-slate-400 dark:text-slate-100 dark:disabled:text-slate-500"
                  type="number"
                  min="1"
                  max="9999"
                  step="1"
                  inputMode="numeric"
                  value={autoCount}
                  disabled={infinite || autoRunning}
                  onChange={(event) => setAutoCount(event.target.value)}
                  onBlur={() => setAutoCount(String(Math.max(1, Math.floor(Number(autoCount) || 1))))}
                />
                <button
                  type="button"
                  disabled={autoRunning}
                  onClick={() => setInfinite((value) => !value)}
                  className={`flex w-14 items-center justify-center border-l border-slate-200 transition disabled:opacity-50 dark:border-white/7 ${
                    infinite ? "bg-cyan-100 text-cyan-700 dark:bg-cyan-400/15 dark:text-cyan-300" : "bg-slate-50 text-slate-500 dark:bg-white/5 dark:text-slate-400"
                  }`}
                  aria-label={t("plinko.infiniteAria")}
                  aria-pressed={infinite}
                >
                  <InfinityIcon size={19} />
                </button>
              </div>
              <p className="mt-1.5 text-[9px] leading-relaxed text-slate-500">
                {t("plinko.autoHint")}
              </p>
            </div>
          )}
        </section>
        </>
        ) : (
          <section className="min-h-[420px] rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-white/5 dark:bg-[#0a202d] dark:shadow-none">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-extrabold">{t("plinko.myBets")}</h2>
                <p className="text-[9px] text-slate-500">
                  {history ? t("plinko.paidDemo", { paid: history.paid_count, demo: history.demo_count }) : t("plinko.dbHistory")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void refreshHistory(historyPage)}
                disabled={historyLoading}
                className="rounded-lg bg-cyan-50 px-3 py-2 text-[9px] font-bold uppercase text-cyan-700 disabled:opacity-50 dark:bg-white/5 dark:text-cyan-300"
              >
                {t("common.refresh")}
              </button>
            </div>
            {historyLoading ? (
              <div className="flex h-48 items-center justify-center text-slate-500">
                <Loader2 className="animate-spin" size={24} />
              </div>
            ) : history?.items.length ? (
              <div className="space-y-2">
                {history.items.map((item) => (
                  <div key={item.play_id} className="rounded-lg border border-slate-200 bg-slate-50 p-2.5 dark:border-white/5 dark:bg-white/[.025]">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-extrabold text-lime-700 dark:text-lime-300">{multiplierLabel(item.multiplier)}</span>
                        {item.is_demo && (
                          <span className="rounded bg-cyan-100 px-1.5 py-0.5 text-[8px] font-bold uppercase text-cyan-700 dark:bg-cyan-400/10 dark:text-cyan-300">{t("plinko.demo")}</span>
                        )}
                      </div>
                      <span className={`text-xs font-bold ${Number(item.net) >= 0 ? "text-emerald-700 dark:text-emerald-300" : "text-rose-600 dark:text-rose-300"}`}>
                        {item.is_demo ? t("plinko.noWalletChange") : t("plinko.netEtb", { net: `${Number(item.net) >= 0 ? "+" : ""}${money(Number(item.net))}` })}
                      </span>
                    </div>
                    <div className="mt-1.5 flex justify-between text-[9px] text-slate-500">
                      <span>{t("plinko.itemMeta", { risk: item.risk, rows: item.rows, slot: item.slot_index + 1 })}</span>
                      <span>{item.created_at ? new Date(item.created_at).toLocaleString() : "—"}</span>
                    </div>
                    {!item.is_demo && (
                      <div className="mt-1 text-[9px] text-slate-600 dark:text-slate-400">
                        {t("plinko.stakePayout", { stake: money(Number(item.stake)), payout: money(Number(item.payout)) })}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex h-48 items-center justify-center text-xs text-slate-500">{t("plinko.noPlays")}</div>
            )}
            <div className="mt-3 flex items-center justify-between">
              <button
                type="button"
                disabled={historyPage === 0 || historyLoading}
                onClick={() => setHistoryPage((page) => Math.max(0, page - 1))}
                className="rounded-lg bg-slate-100 px-3 py-2 text-[9px] font-bold uppercase disabled:opacity-30 dark:bg-white/5"
              >
                {t("common.prev")}
              </button>
              <span className="text-[9px] text-slate-500">{t("plinko.page", { page: historyPage + 1 })}</span>
              <button
                type="button"
                disabled={historyLoading || !history || (historyPage + 1) * 10 >= history.total}
                onClick={() => setHistoryPage((page) => page + 1)}
                className="rounded-lg bg-slate-100 px-3 py-2 text-[9px] font-bold uppercase disabled:opacity-30 dark:bg-white/5"
              >
                {t("common.next")}
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
