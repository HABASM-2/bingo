import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeftRight,
  Bot,
  Crown,
  RotateCcw,
  Sparkles,
  Timer,
  Users,
  Wifi,
} from "lucide-react";
import {
  type Board,
  type GameMode,
  type Move,
  type Outcome,
  type Piece,
  type Side,
  applyMove,
  colOf,
  countPieces,
  createInitialBoard,
  evaluateOutcome,
  formatClock,
  isPlayable,
  legalMoves,
  opposite,
  rowOf,
} from "../../games/dama/engine";
import { chooseAiMove } from "../../games/dama/ai";
import { DAMA_TURN_TIMEOUT_SEC } from "../../games/dama/constants";
import { useDamaOnline } from "../../hooks/useDamaOnline";
import {
  finishDamaAiGame,
  getActiveDamaAiSession,
  startDamaAiGame,
  syncDamaAiSession,
  type DamaAiSession,
} from "../../services/dama";
import { ConfirmDialog } from "./ConfirmDialog";
import { OnlineLobby } from "./OnlineLobby";
import { ResultOverlay, type ResultKind } from "./ResultOverlay";
import { StakePicker, stakePrizePreview } from "./StakePicker";

type Phase = "menu" | "stake_ai" | "online_lobby" | "play";

const HUMAN: Side = "red";
const AI: Side = "black";

function sideLabel(
  side: Side,
  mode: GameMode,
  names?: { red: string; black: string } | null,
): string {
  if (mode === "online" && names) {
    return side === "red" ? names.red : names.black;
  }
  if (mode === "ai") return side === HUMAN ? "You" : "Computer";
  return side === "red" ? "Player 1" : "Player 2";
}

function outcomeMessage(
  outcome: Outcome,
  mode: GameMode,
  mySide?: Side | null,
  agreedDraw = false,
): string {
  if (outcome === "draw") {
    return agreedDraw ? "Draw agreed — stakes refunded." : "Draw — no more moves.";
  }
  if (mode === "online" && mySide) {
    if (outcome === mySide) return "You win!";
    return "You lose.";
  }
  if (mode === "ai") return outcome === HUMAN ? "You win!" : "Computer wins.";
  return outcome === "red" ? "Player 1 (Red) wins!" : "Player 2 (Black) wins!";
}

/** Long / stuck games may offer a mutual draw (mirrors server heuristic). */
function isDrawEligible(plyCount: number, quietPlies: number, board: Board): boolean {
  if (quietPlies >= 30) return true;
  if (plyCount >= 50) return true;
  const pieces = board.filter(Boolean);
  const men = pieces.filter((p) => p!.kind === "man").length;
  if (pieces.length > 0 && men === 0 && plyCount >= 20) return true;
  return false;
}

function squareCenter(
  boardEl: HTMLElement,
  square: number,
  flipped = false,
): { x: number; y: number } {
  const view = flipped ? 63 - square : square;
  const cell = boardEl.clientWidth / 8;
  return {
    x: colOf(view) * cell + cell / 2,
    y: rowOf(view) * cell + cell / 2,
  };
}

/** Rotate board 180° so Black sits at the bottom for the online Black player. */
function flipSquare(square: number): number {
  return 63 - square;
}

interface DamaGameProps {
  accessToken?: string;
  userId?: string;
  firstName?: string;
  walletBalance?: string | null;
  onBalanceChange?: (balance: string) => void;
  /** False while another bottom-nav tab is showing (component stays mounted). */
  isActive?: boolean;
}

export function DamaGame({
  accessToken = "",
  userId = "",
  walletBalance = null,
  onBalanceChange,
  isActive = true,
}: DamaGameProps) {
  const [phase, setPhase] = useState<Phase>("menu");
  const [mode, setMode] = useState<GameMode>("ai");
  const [board, setBoard] = useState<Board>(() => createInitialBoard());
  const [turn, setTurn] = useState<Side>("red");
  const [selected, setSelected] = useState<number | null>(null);
  const [thinking, setThinking] = useState(false);
  const [animating, setAnimating] = useState(false);
  const [animFrom, setAnimFrom] = useState<number | null>(null);
  const [lastMove, setLastMove] = useState<Move | null>(null);
  const [history, setHistory] = useState<Array<{ board: Board; turn: Side }>>([]);
  const [totalMs, setTotalMs] = useState({ red: 0, black: 0 });
  const [turnMs, setTurnMs] = useState(0);
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [ghostPiece, setGhostPiece] = useState<Piece | null>(null);
  const [mySide, setMySide] = useState<Side | null>(null);
  const [onlineNames, setOnlineNames] = useState<{ red: string; black: string } | null>(
    null,
  );
  const [matchId, setMatchId] = useState<string | null>(null);
  const [stake, setStake] = useState("10");
  const [activeStake, setActiveStake] = useState<string | null>(null);
  const [prizePool, setPrizePool] = useState<string | null>(null);
  const [aiGameCode, setAiGameCode] = useState<string | null>(null);
  const [stakeBusy, setStakeBusy] = useState(false);
  const [stakeError, setStakeError] = useState<string | null>(null);
  const [plyCount, setPlyCount] = useState(0);
  const [quietPlies, setQuietPlies] = useState(0);
  const [agreedDraw, setAgreedDraw] = useState(false);
  const [aiDrawOffered, setAiDrawOffered] = useState(false);
  const [forcedDraw, setForcedDraw] = useState(false);
  const [timeoutWinner, setTimeoutWinner] = useState<Side | null>(null);
  const [turnDeadline, setTurnDeadline] = useState<number | null>(null);
  const [turnLeftSec, setTurnLeftSec] = useState<number | null>(null);
  const [rematchStake, setRematchStake] = useState("10");
  const [savedAiSession, setSavedAiSession] = useState<DamaAiSession | null>(null);
  const [confirmAction, setConfirmAction] = useState<
    null | "resign" | "new" | "leave_ai"
  >(null);
  const [resultDismissed, setResultDismissed] = useState(false);
  const aiSettledRef = useRef(false);
  const timeoutClaimedRef = useRef(false);


  const boardRef = useRef<HTMLDivElement>(null);
  const ghostRef = useRef<HTMLDivElement>(null);
  const boardRectRef = useRef<DOMRect | null>(null);
  const dragMetaRef = useRef<{ from: number; piece: Piece } | null>(null);
  const turnStartedRef = useRef(Date.now());
  const busyRef = useRef(false);
  const lastAppliedMoveKey = useRef<string | null>(null);

  const onlineEnabled = phase === "online_lobby" || (phase === "play" && mode === "online");
  const online = useDamaOnline({
    token: accessToken || null,
    enabled: onlineEnabled && Boolean(accessToken),
    onBalance: onBalanceChange,
  });

  const onlineSendMoveRef = useRef(online.sendMove);
  const commitMoveRef = useRef<
    (move: Move, opts?: { skipHop?: boolean }) => Promise<void>
  >(async () => {});

  useEffect(() => {
    onlineSendMoveRef.current = online.sendMove;
  }, [online.sendMove]);


  const localOutcome = useMemo(() => evaluateOutcome(board, turn), [board, turn]);
  const outcome: Outcome =
    forcedDraw || agreedDraw
      ? "draw"
      : timeoutWinner
        ? timeoutWinner
        : mode === "online" && online.match
          ? online.match.status === "finished"
            ? online.match.winner
            : null
          : localOutcome;

  const drawEligible =
    mode === "online" && online.match
      ? online.match.drawEligible
      : mode === "ai"
        ? isDrawEligible(plyCount, quietPlies, board)
        : false;

  const moves = useMemo(() => {
    if (outcome || animating) return [];
    if (mode === "online" && mySide && turn !== mySide) return [];
    return legalMoves(board, turn);
  }, [board, turn, outcome, animating, mode, mySide]);


  const selectable = useMemo(() => {
    const set = new Set<number>();
    for (const m of moves) set.add(m.from);
    return set;
  }, [moves]);

  const allTargets = useMemo(() => {
    const set = new Set<number>();
    for (const m of moves) set.add(m.to);
    return set;
  }, [moves]);

  const allCapturable = useMemo(() => {
    const set = new Set<number>();
    for (const m of moves) for (const c of m.captures) set.add(c);
    return set;
  }, [moves]);

  const focusFrom = dragFrom ?? selected;

  const focusMoves = useMemo(() => {
    if (focusFrom === null) return moves;
    return moves.filter((m) => m.from === focusFrom);
  }, [moves, focusFrom]);

  const focusTargets = useMemo(() => {
    const set = new Set<number>();
    for (const m of focusMoves) set.add(m.to);
    return set;
  }, [focusMoves]);

  const focusCapturable = useMemo(() => {
    const set = new Set<number>();
    for (const m of focusMoves) for (const c of m.captures) set.add(c);
    return set;
  }, [focusMoves]);

  const redCount = countPieces(board, "red");
  const blackCount = countPieces(board, "black");

  const humanCanAct =
    phase === "play" &&
    !outcome &&
    !thinking &&
    !animating &&
    (mode === "local" ||
      (mode === "ai" && turn === HUMAN) ||
      (mode === "online" && mySide != null && turn === mySide));


  const cacheBoardRect = () => {
    boardRectRef.current = boardRef.current?.getBoundingClientRect() ?? null;
  };

  const placeGhost = (x: number, y: number, scale = 1.06) => {
    const el = ghostRef.current;
    if (!el) return;
    el.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%) scale(${scale})`;
    el.style.opacity = "1";
    el.style.visibility = "visible";
  };

  const hideGhost = () => {
    const el = ghostRef.current;
    if (!el) return;
    el.style.opacity = "0";
    el.style.visibility = "hidden";
  };

  const startGame = (nextMode: GameMode) => {
    busyRef.current = false;
    dragMetaRef.current = null;
    lastAppliedMoveKey.current = null;
    aiSettledRef.current = false;
    timeoutClaimedRef.current = false;
    setMode(nextMode);
    setBoard(createInitialBoard());
    setTurn("red");
    setSelected(null);
    setLastMove(null);
    setHistory([]);
    setThinking(false);
    setAnimating(false);
    setAnimFrom(null);
    setDragFrom(null);
    setGhostPiece(null);
    hideGhost();
    setTotalMs({ red: 0, black: 0 });
    setTurnMs(0);
    turnStartedRef.current = Date.now();
    setMySide(nextMode === "online" ? null : HUMAN);
    setOnlineNames(null);
    setMatchId(null);
    setPlyCount(0);
    setQuietPlies(0);
    setAgreedDraw(false);
    setAiDrawOffered(false);
    setForcedDraw(false);
    setTimeoutWinner(null);
    setTurnDeadline(null);
    setTurnLeftSec(null);
    setResultDismissed(false);
    if (nextMode === "local") {
      setActiveStake(null);
      setPrizePool(null);
      setAiGameCode(null);
    }
    if (nextMode !== "online") {
      online.clearMatch();
    }
    setPhase("play");
  };

  const openAiStake = () => {
    setStakeError(null);
    setMode("ai");
    // Prefer resuming an unfinished paid game over opening a new stake sheet.
    if (accessToken) {
      void getActiveDamaAiSession()
        .then((res) => {
          if (res.active && res.session) {
            resumeAiSession(res.session);
            return;
          }
          setPhase("stake_ai");
        })
        .catch(() => setPhase("stake_ai"));
      return;
    }
    setPhase("stake_ai");
  };

  const confirmAiStake = async () => {
    if (!accessToken) {
      setStakeError("Sign in to play for stakes");
      return;
    }
    if (Number(walletBalance) < Number(stake)) {
      setStakeError("Insufficient balance");
      return;
    }
    setStakeBusy(true);
    setStakeError(null);
    try {
      const result = await startDamaAiGame(stake);
      onBalanceChange?.(result.balance);
      // Server returns an unfinished session instead of charging again.
      if (result.resumed && result.session) {
        resumeAiSession(result.session);
        return;
      }
      aiSettledRef.current = false;
      startGame("ai");
      setAiGameCode(result.game_code);
      setActiveStake(result.stake);
      setPrizePool(result.prize_pool);
      setStake(result.stake);
      setRematchStake(result.stake);
      setTurnDeadline(
        result.turn_deadline ?? Date.now() / 1000 + DAMA_TURN_TIMEOUT_SEC,
      );
      setSavedAiSession(null);
    } catch {
      setStakeError("Could not start staked game. Check your balance.");
    } finally {
      setStakeBusy(false);
    }
  };

  const resumeAiSession = (session: DamaAiSession) => {
    busyRef.current = false;
    dragMetaRef.current = null;
    lastAppliedMoveKey.current = null;
    aiSettledRef.current = false;
    timeoutClaimedRef.current = false;
    setMode("ai");
    setBoard(session.board);
    setTurn(session.turn);
    setSelected(null);
    setLastMove(null);
    setHistory([]);
    setThinking(false);
    setAnimating(false);
    setAnimFrom(null);
    setDragFrom(null);
    setGhostPiece(null);
    hideGhost();
    setTotalMs({ red: 0, black: 0 });
    setTurnMs(0);
    turnStartedRef.current = Date.now();
    setMySide(HUMAN);
    setOnlineNames(null);
    setMatchId(null);
    setPlyCount(session.ply_count);
    setQuietPlies(session.quiet_plies);
    setAgreedDraw(false);
    setAiDrawOffered(false);
    setForcedDraw(false);
    setTimeoutWinner(null);
    setResultDismissed(false);
    setAiGameCode(session.game_code);
    setActiveStake(session.stake);
    setPrizePool(session.prize_pool);
    setStake(session.stake);
    setRematchStake(session.stake);
    setTurnDeadline(session.turn_deadline);
    setSavedAiSession(null);
    online.clearMatch();
    setPhase("play");
  };

  const openOnlineLobby = () => {
    setMode("online");
    setMatchId(null);
    setMySide(null);
    setOnlineNames(null);
    setActiveStake(null);
    setPrizePool(null);
    online.clearMatch();
    online.clearError();
    setPhase("online_lobby");
  };

  useEffect(() => {
    if (phase !== "play" || outcome) return;
    turnStartedRef.current = Date.now();
    setTurnMs(0);
    const id = window.setInterval(() => {
      setTurnMs(Date.now() - turnStartedRef.current);
    }, 200);
    return () => window.clearInterval(id);
  }, [phase, turn, outcome]);

  const playHopAnimation = useCallback(async (move: Move, piece: Piece) => {
    const boardEl = boardRef.current;
    if (!boardEl) return;
    const flipped = mode === "online" && mySide === "black";

    setAnimating(true);
    setAnimFrom(move.from);
    setGhostPiece(piece);
    cacheBoardRect();

    const hops = move.path.length > 0 ? move.path : [move.to];
    let prev = move.from;

    for (const landing of hops) {
      const start = squareCenter(boardEl, prev, flipped);
      const end = squareCenter(boardEl, landing, flipped);
      await new Promise<void>((resolve) => {
        const duration = 160;
        const t0 = performance.now();
        const tick = (now: number) => {
          const t = Math.min(1, (now - t0) / duration);
          const ease = t < 0.5 ? 2 * t * t : 1 - (2 - 2 * t) ** 2 / 2;
          const lift = Math.sin(Math.PI * t) * 12;
          const scale = 1 + Math.sin(Math.PI * t) * 0.08;
          placeGhost(
            start.x + (end.x - start.x) * ease,
            start.y + (end.y - start.y) * ease - lift,
            scale,
          );
          if (t < 1) requestAnimationFrame(tick);
          else resolve();
        };
        requestAnimationFrame(tick);
      });
      prev = landing;
    }

    hideGhost();
    setGhostPiece(null);
    setAnimFrom(null);
    setAnimating(false);
  }, [mode, mySide]);

  // Enter play when an online match starts / resumes.
  useEffect(() => {
    const m = online.match;
    if (!m) return;
    if (phase !== "online_lobby" && !(phase === "play" && mode === "online")) return;

    setMode("online");
    setMatchId(m.matchId);
    setMySide(m.mySide);
    setOnlineNames({ red: m.red.display_name, black: m.black.display_name });
    setActiveStake(m.stake);
    setPrizePool(m.prizePool);
    setRematchStake(m.rematchStake || m.stake);
    setAgreedDraw(m.winner === "draw" && m.status === "finished");
    setForcedDraw(false);
    setAiDrawOffered(false);
    setTimeoutWinner(null);
    setResultDismissed(false);
    timeoutClaimedRef.current = false;
    setPlyCount(m.plyCount);
    setQuietPlies(m.quietPlies);
    setBoard(m.board);
    setTurn(m.turn);
    setLastMove(m.lastMove);
    setTurnDeadline(m.turnDeadline);
    setHistory([]);
    setSelected(null);
    setPhase("play");
    turnStartedRef.current = Date.now();
    setTurnMs(0);
    lastAppliedMoveKey.current = m.lastMove
      ? `${m.lastMove.from}-${m.lastMove.to}-${m.turn}`
      : `start-${m.matchId}`;
  }, [online.match?.matchId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep online turn deadline / rematch stake in sync.
  useEffect(() => {
    if (mode !== "online" || !online.match) return;
    setTurnDeadline(online.match.turnDeadline);
    if (online.match.rematchStake) setRematchStake(online.match.rematchStake);
  }, [mode, online.match?.turnDeadline, online.match?.rematchStake, online.match?.turn]);

  // When Dama tab focuses: auto-resume unfinished Vs Computer (no second stake).
  useEffect(() => {
    if (!accessToken || !isActive) return;
    let cancelled = false;
    void getActiveDamaAiSession()
      .then((res) => {
        if (cancelled) return;
        if (res.active && res.session) {
          setSavedAiSession(res.session);
          setPhase((p) => {
            if (p === "menu" || p === "stake_ai") {
              queueMicrotask(() => {
                if (!cancelled) resumeAiSession(res.session!);
              });
            }
            return p;
          });
          return;
        }
        setSavedAiSession(null);
        if (res.timed_out && res.settled?.balances) {
          const bal = Object.values(res.settled.balances)[0];
          if (bal) onBalanceChange?.(bal);
        }
      })
      .catch(() => {
        if (!cancelled) setSavedAiSession(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resume when tab focuses
  }, [accessToken, isActive]);

  // Menu banner: refresh saved session when returning to modes.
  useEffect(() => {
    if (phase !== "menu" || !accessToken) {
      if (phase === "menu" && !accessToken) setSavedAiSession(null);
      return;
    }
    let cancelled = false;
    void getActiveDamaAiSession()
      .then((res) => {
        if (cancelled) return;
        setSavedAiSession(res.active && res.session ? res.session : null);
      })
      .catch(() => {
        if (!cancelled) setSavedAiSession(null);
      });
    return () => {
      cancelled = true;
    };
  }, [phase, accessToken]);

  // Persist AI board whenever the tab hides or this component unmounts.
  const aiSyncRef = useRef({
    mode,
    phase,
    outcome,
    aiGameCode,
    board,
    turn,
    plyCount,
    quietPlies,
  });
  aiSyncRef.current = {
    mode,
    phase,
    outcome,
    aiGameCode,
    board,
    turn,
    plyCount,
    quietPlies,
  };

  useEffect(() => {
    const flush = () => {
      const s = aiSyncRef.current;
      if (s.mode !== "ai" || s.phase !== "play" || s.outcome || !s.aiGameCode) return;
      const deadline = Date.now() / 1000 + DAMA_TURN_TIMEOUT_SEC;
      void syncDamaAiSession({
        game_code: s.aiGameCode,
        board: s.board,
        turn: s.turn,
        ply_count: s.plyCount,
        quiet_plies: s.quietPlies,
        turn_deadline: turnDeadline ?? deadline,
      }).catch(() => {});
    };

    if (!isActive) flush();

    const onVisibility = () => {
      if (document.visibilityState === "hidden") flush();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flush);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, [turnDeadline, isActive]);

  // Turn countdown (AI + online).
  useEffect(() => {
    if (phase !== "play" || outcome || (mode !== "ai" && mode !== "online")) {
      setTurnLeftSec(null);
      return;
    }
    const deadline =
      mode === "online" ? (online.match?.turnDeadline ?? turnDeadline) : turnDeadline;
    if (!deadline) {
      setTurnLeftSec(null);
      return;
    }
    const tick = () => {
      setTurnLeftSec(Math.max(0, Math.ceil(deadline - Date.now() / 1000)));
    };
    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [
    phase,
    outcome,
    mode,
    turnDeadline,
    online.match?.turnDeadline,
    turn,
  ]);

  // Claim win when opponent's 2-minute turn expires.
  useEffect(() => {
    if (phase !== "play" || outcome || turnLeftSec === null || turnLeftSec > 0) return;
    if (timeoutClaimedRef.current) return;

    if (mode === "online" && matchId) {
      timeoutClaimedRef.current = true;
      online.claimTimeout(matchId);
      return;
    }
    if (mode === "ai") {
      timeoutClaimedRef.current = true;
      // Side to move ran out of time — the other side wins.
      setTimeoutWinner(opposite(turn));
    }
  }, [phase, outcome, turnLeftSec, mode, matchId, turn, online]);

  // Reset result sheet when a new outcome appears.
  useEffect(() => {
    if (outcome) setResultDismissed(false);
  }, [outcome]);

  // Apply remote online board updates (opponent moves + server auth).
  useEffect(() => {
    if (mode !== "online" || !online.match || phase !== "play") return;
    const m = online.match;
    const key = m.lastMove
      ? `${m.lastMove.from}-${m.lastMove.to}-${m.turn}-${m.status}`
      : `idle-${m.turn}-${m.status}`;
    if (lastAppliedMoveKey.current === key) return;

    const prevKey = lastAppliedMoveKey.current;
    lastAppliedMoveKey.current = key;

    const run = async () => {
      const move = m.lastMove;
      if (move && prevKey && !prevKey.startsWith("start-")) {
        const movingSide = board[move.from]?.side;
        const fromOpponent = movingSide != null && movingSide !== mySide;
        if (fromOpponent && !busyRef.current) {
          const piece = board[move.from];
          if (piece) {
            busyRef.current = true;
            await playHopAnimation(move, piece);
            busyRef.current = false;
          }
        }
      }
      setBoard(m.board);
      setTurn(m.turn);
      setLastMove(m.lastMove);
      setSelected(null);
      setDragFrom(null);
      hideGhost();
      setGhostPiece(null);
    };

    void run();
  }, [online.match, mode, phase, mySide, playHopAnimation]); // eslint-disable-line react-hooks/exhaustive-deps

  const commitMove = useCallback(
    async (move: Move, opts?: { skipHop?: boolean }) => {
      if (busyRef.current) return;
      const piece = board[move.from];
      if (!piece) return;
      busyRef.current = true;

      const spent = Date.now() - turnStartedRef.current;
      setTotalMs((prev) => ({
        ...prev,
        [turn]: prev[turn] + spent,
      }));

      setSelected(null);
      setDragFrom(null);
      dragMetaRef.current = null;
      hideGhost();
      setGhostPiece(null);

      try {
        if (mode === "online" && matchId) {
          if (!opts?.skipHop) {
            await playHopAnimation(move, piece);
          }
          const next = applyMove(board, move);
          setBoard(next);
          setLastMove(move);
          setTurn(opposite(turn));
          lastAppliedMoveKey.current = `${move.from}-${move.to}-${opposite(turn)}-playing`;
          onlineSendMoveRef.current(matchId, move.from, move.to);
          return;
        }

        setHistory((h) => [...h, { board, turn }]);

        if (!opts?.skipHop) {
          await playHopAnimation(move, piece);
        }

        const next = applyMove(board, move);
        setBoard(next);
        setLastMove(move);
        const nextTurn = opposite(turn);
        setTurn(nextTurn);
        const nextPly = plyCount + 1;
        const nextQuiet = move.captures.length > 0 ? 0 : quietPlies + 1;
        setPlyCount(nextPly);
        setQuietPlies(nextQuiet);
        setAiDrawOffered(false);

        if (mode === "ai" && aiGameCode) {
          const deadline = Date.now() / 1000 + DAMA_TURN_TIMEOUT_SEC;
          setTurnDeadline(deadline);
          void syncDamaAiSession({
            game_code: aiGameCode,
            board: next,
            turn: nextTurn,
            ply_count: nextPly,
            quiet_plies: nextQuiet,
            turn_deadline: deadline,
          })
            .then((res) => setTurnDeadline(res.turn_deadline))
            .catch(() => {});
        }
      } finally {
        busyRef.current = false;
      }
    },
    [board, turn, playHopAnimation, mode, matchId, aiGameCode, plyCount, quietPlies],
  );

  useEffect(() => {
    commitMoveRef.current = commitMove;
  }, [commitMove]);

  const tryCommitTo = useCallback(
    (to: number, fromOverride?: number | null, skipHop = false) => {
      const from = fromOverride ?? selected;
      if (from === null || from === undefined) return;
      const options = moves.filter((m) => m.from === from && m.to === to);
      if (options.length === 0) return;
      void commitMove(options[0], { skipHop });
    },
    [selected, moves, commitMove],
  );

  const onPointerDownPiece = (
    event: React.PointerEvent,
    square: number,
    piece: Piece,
  ) => {
    if (!humanCanAct || !selectable.has(square)) return;
    event.preventDefault();
    event.stopPropagation();

    cacheBoardRect();
    const rect = boardRectRef.current;
    if (!rect || !boardRef.current) return;

    boardRef.current.setPointerCapture(event.pointerId);
    dragMetaRef.current = { from: square, piece };
    setSelected(square);
    setDragFrom(square);
    setGhostPiece(piece);
    placeGhost(event.clientX - rect.left, event.clientY - rect.top, 1.08);
  };

  const onPointerMove = (event: React.PointerEvent) => {
    if (!dragMetaRef.current || !boardRef.current) return;
    // Fresh rect each move (scroll/layout) + DOM-only transform (no React).
    const rect = boardRef.current.getBoundingClientRect();
    boardRectRef.current = rect;
    placeGhost(event.clientX - rect.left, event.clientY - rect.top, 1.1);
  };

  const squareFromPoint = (clientX: number, clientY: number): number | null => {
    const rect = boardRectRef.current ?? boardRef.current?.getBoundingClientRect();
    if (!rect) return null;
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    if (x < 0 || y < 0 || x > rect.width || y > rect.height) return null;
    const col = Math.min(7, Math.floor((x / rect.width) * 8));
    const row = Math.min(7, Math.floor((y / rect.height) * 8));
    const viewIdx = row * 8 + col;
    const flipped = mode === "online" && mySide === "black";
    return flipped ? flipSquare(viewIdx) : viewIdx;
  };

  const endDrag = (event: React.PointerEvent) => {
    const meta = dragMetaRef.current;
    if (!meta) return;
    const from = meta.from;
    const to = squareFromPoint(event.clientX, event.clientY);
    dragMetaRef.current = null;
    setDragFrom(null);
    hideGhost();
    setGhostPiece(null);
    if (to !== null && to !== from) {
      tryCommitTo(to, from, true);
      return;
    }
    setSelected(from);
  };

  const onSquareClick = (square: number) => {
    if (!humanCanAct || dragMetaRef.current) return;
    if (selected !== null && focusTargets.has(square)) {
      tryCommitTo(square);
      return;
    }
    if (selectable.has(square)) {
      setSelected(square);
      return;
    }
    setSelected(null);
  };

  useEffect(() => {
    if (
      !isActive ||
      phase !== "play" ||
      mode !== "ai" ||
      outcome ||
      turn !== AI ||
      animating
    ) {
      if (turn !== AI) setThinking(false);
      return;
    }

    let cancelled = false;
    setThinking(true);
    const timer = window.setTimeout(() => {
      if (cancelled) return;
      // Use latest board via functional path — choose on a snapshot from this effect.
      const move = chooseAiMove(board, AI, "smart");
      if (cancelled) return;
      if (move) {
        void commitMoveRef.current(move).finally(() => {
          if (!cancelled) setThinking(false);
        });
      } else {
        setThinking(false);
      }
    }, 420);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // Intentionally omit commitMove — it is read via commitMoveRef so the
    // 200ms clock tick cannot cancel the AI thinking timer forever.
  }, [isActive, phase, mode, outcome, turn, board, animating]);

  // Settle AI stakes once the game ends.
  useEffect(() => {
    if (mode !== "ai" || !outcome || !aiGameCode || aiSettledRef.current) return;
    aiSettledRef.current = true;
    const humanOutcome =
      outcome === "draw" ? "draw" : outcome === HUMAN ? "win" : "loss";
    void finishDamaAiGame(aiGameCode, humanOutcome)
      .then((res) => {
        const bal = res.balances && Object.values(res.balances)[0];
        if (bal) onBalanceChange?.(bal);
        if (res.prize_pool) setPrizePool(res.prize_pool);
      })
      .catch(() => {
        aiSettledRef.current = false;
      });
  }, [mode, outcome, aiGameCode, onBalanceChange]);

  useEffect(() => {
    if (mode === "online" && online.match?.status === "finished" && online.match.winner === "draw") {
      setAgreedDraw(true);
    }
  }, [mode, online.match?.status, online.match?.winner]);

  const offerAiDraw = () => {
    if (mode !== "ai" || !drawEligible || outcome || aiDrawOffered) return;
    setAiDrawOffered(true);
    // Computer only allows this button when the game looks endless — that is
    // its agreement condition; it accepts shortly after you offer.
    window.setTimeout(() => {
      setAgreedDraw(true);
      setForcedDraw(true);
      setAiDrawOffered(false);
    }, 700);
  };

  const rematchAi = async () => {
    const s = rematchStake || activeStake || stake;
    setStake(s);
    if (!accessToken) return;
    if (Number(walletBalance) < Number(s)) {
      setStakeError("Insufficient balance for rematch");
      return;
    }
    setStakeBusy(true);
    setStakeError(null);
    try {
      const result = await startDamaAiGame(s);
      onBalanceChange?.(result.balance);
      aiSettledRef.current = false;
      startGame("ai");
      setAiGameCode(result.game_code);
      setActiveStake(result.stake);
      setPrizePool(result.prize_pool);
      setStake(result.stake);
      setRematchStake(result.stake);
      setTurnDeadline(
        result.turn_deadline ?? Date.now() / 1000 + DAMA_TURN_TIMEOUT_SEC,
      );
    } catch {
      setStakeError("Could not start rematch");
    } finally {
      setStakeBusy(false);
    }
  };

  const resultKind = ((): ResultKind | null => {
    if (!outcome) return null;
    if (outcome === "draw") return "draw";
    if (mode === "online" && mySide) return outcome === mySide ? "win" : "loss";
    if (mode === "ai") return outcome === HUMAN ? "win" : "loss";
    return outcome === "red" ? "win" : "loss";
  })();

  const resultTitle =
    resultKind === "win"
      ? "You win!"
      : resultKind === "loss"
        ? "You lost"
        : "Draw";

  const resultSubtitle =
    resultKind === "win"
      ? mode === "ai"
        ? "Nice play — prize credited to your wallet."
        : "Opponent timed out or you forced the win."
      : resultKind === "loss"
        ? mode === "ai"
          ? "Computer takes this round. Rematch anytime."
          : "Better luck next game — propose a rematch."
        : "Stakes refunded. Ready for another?" ;

  const onlineRematchStatus =
    mode === "online" && online.match
      ? online.match.rematchPeerLeft
        ? "peer_left"
        : online.match.rematchOfferBy === userId
          ? "offered_by_me"
          : online.match.rematchOfferBy
            ? "offered_by_them"
            : "idle"
      : "idle";

  const runConfirm = () => {
    const action = confirmAction;
    setConfirmAction(null);
    if (action === "resign") {
      if (mode === "online" && matchId) {
        online.resign(matchId);
        return;
      }
      if (mode === "ai" && !outcome) {
        setTimeoutWinner(AI);
      }
      return;
    }
    if (action === "new") {
      if (mode === "ai") {
        if (!outcome && aiGameCode && !aiSettledRef.current) {
          aiSettledRef.current = true;
          void finishDamaAiGame(aiGameCode, "loss")
            .then((res) => {
              const bal = res.balances && Object.values(res.balances)[0];
              if (bal) onBalanceChange?.(bal);
            })
            .catch(() => {
              aiSettledRef.current = false;
            });
        }
        openAiStake();
        return;
      }
      startGame(mode);
      return;
    }
    if (action === "leave_ai") {
      setPhase("menu");
    }
  };

  const undo = () => {
    if (history.length === 0 || thinking || animating || busyRef.current) return;
    let nextBoard = board;
    let nextTurn = turn;
    if (mode === "ai" && history.length >= 2 && turn === HUMAN) {
      const target = history[history.length - 2];
      setHistory((h) => h.slice(0, -2));
      setBoard(target.board);
      setTurn(target.turn);
      nextBoard = target.board;
      nextTurn = target.turn;
      setPlyCount((n) => Math.max(0, n - 2));
    } else {
      const prev = history[history.length - 1];
      setHistory((h) => h.slice(0, -1));
      setBoard(prev.board);
      setTurn(prev.turn);
      nextBoard = prev.board;
      nextTurn = prev.turn;
      setPlyCount((n) => Math.max(0, n - 1));
    }
    setSelected(null);
    setLastMove(null);
    setDragFrom(null);
    dragMetaRef.current = null;
    setGhostPiece(null);
    hideGhost();
    setAnimFrom(null);
    if (mode === "ai" && aiGameCode) {
      const deadline = Date.now() / 1000 + DAMA_TURN_TIMEOUT_SEC;
      setTurnDeadline(deadline);
      timeoutClaimedRef.current = false;
      void syncDamaAiSession({
        game_code: aiGameCode,
        board: nextBoard,
        turn: nextTurn,
        ply_count: Math.max(0, plyCount - (mode === "ai" && turn === HUMAN ? 2 : 1)),
        quiet_plies: quietPlies,
        turn_deadline: deadline,
      }).catch(() => {});
    }
  };

  if (phase === "menu") {
    return (
      <div className="flex h-full flex-col overflow-y-auto px-3 py-3 animate-[fadeIn_0.3s_ease-out]">
        <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#7C2D12] via-[#C2410C] to-[#F59E0B] px-4 py-5 text-white shadow-lg">
          <div className="absolute -right-8 -top-10 h-32 w-32 rounded-full bg-white/15 blur-2xl" />
          <div className="absolute -bottom-12 left-6 h-28 w-28 rounded-full bg-amber-200/30 blur-2xl" />
          <div className="relative flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/20 ring-1 ring-white/30">
              <Crown size={26} />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/75">
                Dalamax
              </p>
              <h1 className="text-2xl font-black leading-tight">Dama</h1>
              <p className="mt-0.5 text-sm text-white/85">
                Slide pieces · back-captures · flying kings.
              </p>
            </div>
          </div>
        </header>

        <p className="mt-4 px-0.5 text-sm font-medium text-purple-600 dark:text-purple-300/80">
          Drag a glowing piece along its route. Crowning ends that turn — no instant king eat.
        </p>

        {savedAiSession && (
          <button
            type="button"
            onClick={() => resumeAiSession(savedAiSession)}
            className="mt-3 w-full rounded-3xl bg-gradient-to-r from-amber-500 to-orange-500 p-4 text-left text-white shadow-md transition active:scale-[0.985]"
          >
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-white/80">
              Resume Vs Computer
            </p>
            <p className="mt-1 text-base font-extrabold">
              Continue · stake {savedAiSession.stake} ETB
            </p>
            <p className="mt-0.5 text-xs font-medium text-white/85">
              Session kept ~20 min · 2 min per turn
            </p>
          </button>
        )}

        <div className="mt-3 flex flex-col gap-3 pb-4">
          <button
            type="button"
            onClick={openAiStake}
            className="rounded-3xl bg-white/95 p-4 text-left shadow-md ring-1 ring-orange-100 transition active:scale-[0.985] dark:bg-[#1E1B2E] dark:ring-white/10"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-orange-500 to-amber-400 text-white shadow">
                <Bot size={24} />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-lg font-extrabold text-purple-950 dark:text-white">
                  Vs Computer
                </h2>
                <p className="text-xs font-medium text-purple-500 dark:text-purple-300/75">
                  Stake 5 / 10 / 15 or custom · win the pot.
                </p>
              </div>
              <Sparkles className="text-orange-400" size={18} />
            </div>
          </button>

          <button
            type="button"
            onClick={openOnlineLobby}
            disabled={!accessToken}
            className="rounded-3xl bg-white/95 p-4 text-left shadow-md ring-1 ring-purple-100 transition active:scale-[0.985] disabled:opacity-50 dark:bg-[#1E1B2E] dark:ring-white/10"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-fuchsia-500 text-white shadow">
                <Wifi size={24} />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-lg font-extrabold text-purple-950 dark:text-white">
                  Vs Person
                </h2>
                <p className="text-xs font-medium text-purple-500 dark:text-purple-300/75">
                  {accessToken
                    ? "Online players · search · challenge & confirm."
                    : "Sign in to play online against others."}
                </p>
              </div>
              <Users className="text-violet-400" size={18} />
            </div>
          </button>

          <button
            type="button"
            onClick={() => startGame("local")}
            className="rounded-3xl bg-white/95 p-4 text-left shadow-md ring-1 ring-orange-100 transition active:scale-[0.985] dark:bg-[#1E1B2E] dark:ring-white/10"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-stone-600 to-stone-800 text-white shadow">
                <ArrowLeftRight size={24} />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-lg font-extrabold text-purple-950 dark:text-white">
                  Pass & Play
                </h2>
                <p className="text-xs font-medium text-purple-500 dark:text-purple-300/75">
                  Same device · free · no wallet stake.
                </p>
              </div>
            </div>
          </button>
        </div>
      </div>
    );
  }

  if (phase === "stake_ai") {
    const preview = stakePrizePreview(stake);
    return (
      <div className="flex h-full flex-col overflow-y-auto px-3 py-3 animate-[fadeIn_0.25s_ease-out]">
        <button
          type="button"
          onClick={() => setPhase("menu")}
          className="mb-3 self-start rounded-xl bg-white/80 px-3 py-1.5 text-xs font-bold text-purple-700 ring-1 ring-purple-100 dark:bg-white/10 dark:text-purple-200 dark:ring-white/10"
        >
          Back
        </button>
        <StakePicker balance={walletBalance} stake={stake} onStakeChange={setStake} />
        {stakeError && (
          <p className="mt-2 text-center text-xs font-semibold text-rose-600">{stakeError}</p>
        )}
        <button
          type="button"
          disabled={stakeBusy || Number(walletBalance) < Number(stake)}
          onClick={() => void confirmAiStake()}
          className="mt-4 rounded-2xl bg-orange-500 px-4 py-3.5 text-sm font-extrabold text-white shadow disabled:opacity-40"
        >
          {stakeBusy ? "Starting…" : `Play · win up to ${preview.prize} ETB`}
        </button>
      </div>
    );
  }

  if (phase === "online_lobby") {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        {online.match?.status === "playing" && (
          <div className="shrink-0 px-3 pt-3">
            <button
              type="button"
              onClick={() => setPhase("play")}
              className="w-full rounded-2xl bg-gradient-to-r from-violet-600 to-fuchsia-500 px-4 py-3 text-sm font-extrabold text-white shadow"
            >
              Return to match · stake {online.match.stake} ETB
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1">
          <OnlineLobby
            connectionStatus={online.connectionStatus}
            players={online.players}
            selfUserId={userId}
            balance={walletBalance}
            stake={stake}
            onStakeChange={setStake}
            incoming={online.incoming}
            outgoing={online.outgoing}
            error={online.error}
            onBack={() => {
              online.clearError();
              setPhase("menu");
            }}
            onChallenge={online.challenge}
            onAccept={online.acceptChallenge}
            onDecline={online.declineChallenge}
            onCancel={online.cancelChallenge}
            onClearError={online.clearError}
          />
        </div>
      </div>
    );
  }

  const showRoutes = (humanCanAct || (mode === "local" && !outcome)) && !animating;

  const routeTargets = focusFrom !== null ? focusTargets : allTargets;
  const routeCaptures = focusFrom !== null ? focusCapturable : allCapturable;

  // Online Black sees a 180° board so their men sit at the bottom (no phone rotate).
  const boardFlipped = mode === "online" && mySide === "black";
  const toView = (logical: number) => (boardFlipped ? flipSquare(logical) : logical);
  const toLogical = (view: number) => (boardFlipped ? flipSquare(view) : view);

  const opponentSide: Side | null =
    mode === "online" && mySide ? (mySide === "red" ? "black" : "red") : null;

  const renderSideCard = (side: Side, title: string) => {
    const count = side === "red" ? redCount : blackCount;
    return (
      <SideCard
        key={side}
        title={title}
        side={side}
        men={count.men}
        kings={count.kings}
        active={turn === side && !outcome}
        thinking={thinking && turn === side && mode === "ai"}
        turnMs={turn === side && !outcome ? turnMs : 0}
        totalMs={totalMs[side] + (turn === side && !outcome ? turnMs : 0)}
      />
    );
  };

  return (
    <div className="flex h-full flex-col overflow-hidden px-2.5 pb-2 pt-2 animate-[fadeIn_0.25s_ease-out]">
      {(mode === "ai" || mode === "online") && (
        <div className="mb-2 flex items-center justify-between gap-2 rounded-2xl bg-white/85 px-3 py-2 text-xs font-bold shadow-sm ring-1 ring-purple-100 dark:bg-[#1E1B2E] dark:ring-white/10">
          <span className="tabular-nums text-purple-800 dark:text-purple-100">
            Wallet{" "}
            <span className="text-purple-950 dark:text-white">
              {walletBalance != null ? Number(walletBalance).toFixed(2) : "—"}
            </span>{" "}
            ETB
          </span>
          <span className="tabular-nums text-orange-600 dark:text-orange-300">
            Stake {activeStake ?? "—"}
            {prizePool ? ` · win ${prizePool}` : ""}
          </span>
        </div>
      )}

      <div className="mb-2 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => {
            if (mode === "ai" && !outcome) {
              setConfirmAction("leave_ai");
              return;
            }
            if (mode === "online") {
              setPhase("online_lobby");
              return;
            }
            setPhase("menu");
          }}
          className="rounded-xl bg-white/80 px-3 py-1.5 text-xs font-bold text-purple-700 ring-1 ring-purple-100 dark:bg-white/10 dark:text-purple-200 dark:ring-white/10"
        >
          {mode === "online" ? "Lobby" : "Modes"}
        </button>
        <div className="flex items-center gap-1.5">
          {mode === "local" && (
            <button
              type="button"
              onClick={undo}
              disabled={history.length === 0 || thinking || animating || Boolean(outcome)}
              className="flex items-center gap-1 rounded-xl bg-white/80 px-2.5 py-1.5 text-xs font-bold text-purple-700 ring-1 ring-purple-100 disabled:opacity-40 dark:bg-white/10 dark:text-purple-200 dark:ring-white/10"
            >
              <RotateCcw size={13} />
              Undo
            </button>
          )}
          {mode === "online" && matchId && !outcome ? (
            <>
              {drawEligible && (
                online.match?.drawOfferBy && online.match.drawOfferBy !== userId ? (
                  <>
                    <button
                      type="button"
                      onClick={() => online.acceptDraw(matchId)}
                      className="rounded-xl bg-emerald-500 px-2.5 py-1.5 text-xs font-bold text-white shadow"
                    >
                      Accept draw
                    </button>
                    <button
                      type="button"
                      onClick={() => online.declineDraw(matchId)}
                      className="rounded-xl bg-white/80 px-2.5 py-1.5 text-xs font-bold text-purple-700 ring-1 ring-purple-100 dark:bg-white/10 dark:text-purple-200"
                    >
                      Decline
                    </button>
                  </>
                ) : online.match?.drawOfferBy === userId ? (
                  <span className="rounded-xl bg-amber-100 px-2.5 py-1.5 text-xs font-bold text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                    Draw offered…
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => online.offerDraw(matchId)}
                    className="rounded-xl bg-sky-500 px-2.5 py-1.5 text-xs font-bold text-white shadow"
                  >
                    Offer draw
                  </button>
                )
              )}
              <button
                type="button"
                onClick={() => setConfirmAction("resign")}
                className="rounded-xl bg-rose-500 px-2.5 py-1.5 text-xs font-bold text-white shadow"
              >
                Resign
              </button>
            </>
          ) : mode === "ai" && !outcome && drawEligible ? (
            <>
              <button
                type="button"
                disabled={aiDrawOffered}
                onClick={offerAiDraw}
                className="rounded-xl bg-sky-500 px-2.5 py-1.5 text-xs font-bold text-white shadow disabled:opacity-50"
              >
                {aiDrawOffered ? "Computer deciding…" : "Offer draw"}
              </button>
              <button
                type="button"
                onClick={() => setConfirmAction("resign")}
                className="rounded-xl bg-rose-500 px-2.5 py-1.5 text-xs font-bold text-white shadow"
              >
                Resign
              </button>
            </>
          ) : mode === "ai" && !outcome ? (
            <button
              type="button"
              onClick={() => setConfirmAction("resign")}
              className="rounded-xl bg-rose-500 px-2.5 py-1.5 text-xs font-bold text-white shadow"
            >
              Resign
            </button>
          ) : mode !== "online" ? (
            <button
              type="button"
              onClick={() => setConfirmAction("new")}
              className="rounded-xl bg-orange-500 px-2.5 py-1.5 text-xs font-bold text-white shadow"
            >
              New
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                online.clearMatch();
                setPhase("online_lobby");
              }}
              className="rounded-xl bg-orange-500 px-2.5 py-1.5 text-xs font-bold text-white shadow"
            >
              Find opponent
            </button>
          )}
        </div>
      </div>

      {turnLeftSec != null && !outcome && (mode === "ai" || mode === "online") && (
        <div
          className={`mb-2 flex items-center justify-center gap-2 rounded-2xl px-3 py-1.5 text-xs font-extrabold tabular-nums ${
            turnLeftSec <= 15
              ? "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-200"
              : "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
          }`}
        >
          <Timer size={14} />
          {turnLeftSec <= 0
            ? "Time up…"
            : `${Math.floor(turnLeftSec / 60)}:${String(turnLeftSec % 60).padStart(2, "0")} left this turn`}
        </div>
      )}

      {mode === "online" && mySide && opponentSide ? (
        <div className="mb-2">
          {renderSideCard(
            opponentSide,
            sideLabel(opponentSide, mode, onlineNames),
          )}
        </div>
      ) : (
        <div className="mb-2 grid grid-cols-2 gap-2">
          {renderSideCard("red", sideLabel("red", mode, onlineNames))}
          {renderSideCard("black", sideLabel("black", mode, onlineNames))}
        </div>
      )}

      <div className="mx-auto w-full max-w-[380px]">
        <div
          ref={boardRef}
          className="relative grid aspect-square w-full touch-none grid-cols-8 overflow-hidden select-none"
          style={{
            background: "#5C3A21",
            boxShadow: "0 10px 28px rgba(60, 30, 10, 0.35)",
            outline: "3px solid #F5D76E",
            outlineOffset: "0px",
          }}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={() => {
            dragMetaRef.current = null;
            setDragFrom(null);
            setGhostPiece(null);
            hideGhost();
          }}
        >
          {Array.from({ length: 64 }, (_, viewIdx) => {
            const i = toLogical(viewIdx);
            const playable = isPlayable(i);
            const piece = board[i];
            const isSelected = selected === i || dragFrom === i;
            const isTarget = showRoutes && routeTargets.has(i);
            const isLast =
              lastMove != null && (lastMove.from === i || lastMove.to === i);
            const canDrag = humanCanAct && selectable.has(i);
            const hidePiece = dragFrom === i || animFrom === i;
            const woodGrain = playable
              ? "repeating-linear-gradient(90deg, rgba(255,255,255,0.04) 0 1px, transparent 1px 4px), repeating-linear-gradient(0deg, rgba(0,0,0,0.05) 0 1px, transparent 1px 5px)"
              : "repeating-linear-gradient(90deg, rgba(120,80,30,0.06) 0 1px, transparent 1px 5px), repeating-linear-gradient(0deg, rgba(90,55,20,0.05) 0 1px, transparent 1px 6px)";

            return (
              <button
                key={viewIdx}
                type="button"
                onClick={() => onSquareClick(i)}
                className="relative min-h-0 min-w-0 overflow-hidden"
                style={{
                  backgroundColor: playable ? "#8B5A2B" : "#E8D4A8",
                  backgroundImage: woodGrain,
                }}
              >
                {(isSelected || isTarget || (showRoutes && selectable.has(i))) && (
                  <span
                    className="absolute inset-0"
                    style={{
                      background: isSelected
                        ? "rgba(32, 178, 170, 0.42)"
                        : isTarget
                          ? "rgba(32, 178, 170, 0.28)"
                          : "rgba(32, 178, 170, 0.12)",
                    }}
                  />
                )}
                {isLast && !isSelected && (
                  <span className="absolute inset-0 bg-sky-400/15" />
                )}
                {showRoutes && routeCaptures.has(i) && (
                  <span className="absolute inset-[18%] rounded-full ring-2 ring-[#1DB954]/80" />
                )}

                {piece && !hidePiece && (
                  <span
                    className={`absolute inset-0 z-10 flex items-center justify-center p-[11%] ${
                      canDrag ? "cursor-grab touch-none active:cursor-grabbing" : ""
                    }`}
                    style={{ touchAction: "none" }}
                    onPointerDown={(e) => onPointerDownPiece(e, i, piece)}
                  >
                    <span className="relative block aspect-square w-full">
                      <PieceView
                        side={piece.side}
                        king={piece.kind === "king"}
                        pulse={showRoutes && selectable.has(i)}
                      />
                    </span>
                  </span>
                )}
              </button>
            );
          })}

          {showRoutes && focusFrom !== null && focusMoves.length > 0 && (
            <svg
              className="pointer-events-none absolute inset-0 z-[15] h-full w-full"
              viewBox="0 0 8 8"
              preserveAspectRatio="none"
            >
              {focusMoves.map((move) => {
                const points = [focusFrom, ...move.path];
                const d = points
                  .map((sq, n) => {
                    const view = toView(sq);
                    return `${n === 0 ? "M" : "L"} ${colOf(view) + 0.5} ${rowOf(view) + 0.5}`;
                  })
                  .join(" ");
                return (
                  <g key={`${move.from}-${move.to}-${move.captures.join(",")}`}>
                    <path
                      d={d}
                      fill="none"
                      stroke="#1DB954"
                      strokeWidth="0.08"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      opacity="0.95"
                    />
                    {points.map((sq) => {
                      const view = toView(sq);
                      return (
                        <circle
                          key={`dot-${move.to}-${sq}`}
                          cx={colOf(view) + 0.5}
                          cy={rowOf(view) + 0.5}
                          r="0.12"
                          fill="#1DB954"
                        />
                      );
                    })}
                  </g>
                );
              })}
            </svg>
          )}

          {showRoutes && focusFrom === null && (
            <svg
              className="pointer-events-none absolute inset-0 z-[15] h-full w-full"
              viewBox="0 0 8 8"
              preserveAspectRatio="none"
            >
              {[...selectable].map((from) => {
                const view = toView(from);
                return (
                  <circle
                    key={`origin-${from}`}
                    cx={colOf(view) + 0.5}
                    cy={rowOf(view) + 0.5}
                    r="0.1"
                    fill="#1DB954"
                    opacity="0.85"
                  />
                );
              })}
            </svg>
          )}

          <div
            ref={ghostRef}
            className="pointer-events-none absolute left-0 top-0 z-20 will-change-transform"
            style={{
              width: "12.5%",
              height: "12.5%",
              opacity: 0,
              visibility: "hidden",
              filter: "drop-shadow(0 8px 10px rgba(0,0,0,0.35))",
            }}
          >
            {ghostPiece && (
              <div className="flex h-full w-full items-center justify-center p-[11%]">
                <PieceView side={ghostPiece.side} king={ghostPiece.kind === "king"} />
              </div>
            )}
          </div>
        </div>
      </div>

      {mode === "online" && mySide && (
        <div className="mt-2">
          {renderSideCard(mySide, `You · ${sideLabel(mySide, mode, onlineNames)}`)}
        </div>
      )}

      <div className="mt-2 rounded-2xl bg-white/80 px-3 py-2 text-center text-sm font-semibold text-purple-800 shadow-sm ring-1 ring-purple-100 dark:bg-[#1E1B2E] dark:text-purple-100 dark:ring-white/10">
        {outcome ? (
          <span className="text-orange-600 dark:text-orange-300">
            {outcomeMessage(outcome, mode, mySide, agreedDraw)}
          </span>
        ) : thinking ? (
          <span className="inline-flex items-center gap-2">
            <Bot size={15} className="animate-pulse" />
            Computer is thinking…
          </span>
        ) : animating ? (
          <span>Jumping…</span>
        ) : mode === "online" && mySide && turn !== mySide ? (
          <span>Waiting for {sideLabel(turn, mode, onlineNames)}…</span>
        ) : mode === "online" && online.match?.drawOfferBy === userId ? (
          <span>Waiting for opponent to accept your draw…</span>
        ) : mode === "ai" && aiDrawOffered ? (
          <span>Computer is considering your draw offer…</span>
        ) : drawEligible && !outcome ? (
          <span>Game looks long — you can offer a draw</span>
        ) : (
          <span>
            {sideLabel(turn, mode, onlineNames)} to move
            {moves.some((m) => m.captures.length > 0) ? " · capture required" : ""}
            {" · "}
            slide a glowing piece
          </span>
        )}
      </div>

      <ConfirmDialog
        open={confirmAction != null}
        title={
          confirmAction === "resign"
            ? "Resign this game?"
            : confirmAction === "new"
              ? "Start a new game?"
              : "Leave to modes?"
        }
        message={
          confirmAction === "resign"
            ? "You will forfeit the stake. This cannot be undone."
            : confirmAction === "new"
              ? mode === "ai" && !outcome
                ? "Your current staked game will count as a loss."
                : "Leave this board and start over."
              : "Your Vs Computer game is saved for about 20 minutes so you can continue."
        }
        confirmLabel={
          confirmAction === "resign"
            ? "Resign"
            : confirmAction === "new"
              ? "New game"
              : "Leave"
        }
        danger={confirmAction === "resign" || confirmAction === "new"}
        onCancel={() => setConfirmAction(null)}
        onConfirm={runConfirm}
      />

      {resultKind && !resultDismissed && (mode === "ai" || mode === "online") && (
        <ResultOverlay
          kind={resultKind}
          title={resultTitle}
          subtitle={resultSubtitle}
          stake={activeStake}
          prizePool={prizePool}
          balance={walletBalance}
          rematchStake={rematchStake}
          onRematchStakeChange={setRematchStake}
          rematchStatus={mode === "online" ? onlineRematchStatus : "idle"}
          busy={stakeBusy}
          onProposeRematch={
            mode === "ai"
              ? () => void rematchAi()
              : matchId
                ? () => online.offerRematch(matchId, rematchStake)
                : undefined
          }
          onAcceptRematch={
            mode === "online" && matchId
              ? () =>
                  online.acceptRematch(
                    matchId,
                    online.match?.rematchStake || rematchStake,
                  )
              : undefined
          }
          onClose={() => {
            setResultDismissed(true);
            if (mode === "online") {
              online.clearMatch();
              setPhase("online_lobby");
            } else {
              setPhase("menu");
            }
          }}
        />
      )}
    </div>
  );
}

function SideCard({
  title,
  side,
  men,
  kings,
  active,
  thinking = false,
  turnMs,
  totalMs,
}: {
  title: string;
  side: Side;
  men: number;
  kings: number;
  active: boolean;
  thinking?: boolean;
  turnMs: number;
  totalMs: number;
}) {
  return (
    <div
      className={`rounded-2xl px-3 py-2 shadow-sm ring-1 transition ${
        active
          ? "bg-gradient-to-r from-[#F4F7EC] to-[#C5C9A0] ring-[#A8B07A]"
          : "bg-[#E8E2D6] ring-[#D5CFC2]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center">
            <PieceView side={side} king={false} compact />
          </span>
          <span className="text-xs font-extrabold text-stone-800">{title}</span>
        </div>
        {thinking ? (
          <span className="text-[10px] font-bold uppercase tracking-wide text-orange-600">
            Thinking
          </span>
        ) : active ? (
          <span className="text-[10px] font-bold uppercase tracking-wide text-teal-700">
            Turn
          </span>
        ) : null}
      </div>
      <p className="mt-1 text-[11px] font-medium text-stone-600">
        {men} men · {kings} king{kings === 1 ? "" : "s"}
      </p>
      <div className="mt-1 flex items-center gap-1 text-[11px] font-bold tabular-nums text-stone-800">
        <Timer size={12} className={active ? "text-teal-700" : "text-stone-400"} />
        <span>{formatClock(active ? turnMs : 0)}</span>
        <span className="font-medium text-stone-500">· total {formatClock(totalMs)}</span>
      </div>
    </div>
  );
}

function PieceView({
  side,
  king,
  pulse,
  compact = false,
}: {
  side: Side;
  king: boolean;
  pulse?: boolean;
  compact?: boolean;
}) {
  const isRed = side === "red";

  return (
    <span
      className={`relative block shrink-0 overflow-hidden rounded-full ${
        compact ? "h-7 w-7" : "w-full"
      } ${pulse ? "ring-2 ring-[#1DB954]/70 ring-inset" : ""}`}
      style={{
        // Width-driven square — never stretch into an oval when crowned.
        aspectRatio: "1 / 1",
        height: compact ? undefined : "auto",
        maxWidth: "100%",
        background: isRed
          ? "radial-gradient(circle at 35% 30%, #ff6b6b 0%, #e11d2e 55%, #9f1239 100%)"
          : "radial-gradient(circle at 35% 30%, #ffffff 0%, #f3f4f6 55%, #d1d5db 100%)",
        boxShadow: isRed
          ? "inset 0 2px 3px rgba(255,255,255,0.35), inset 0 -3px 4px rgba(0,0,0,0.28), 0 2px 4px rgba(0,0,0,0.35)"
          : "inset 0 2px 3px rgba(255,255,255,0.95), inset 0 -3px 4px rgba(0,0,0,0.18), 0 2px 4px rgba(0,0,0,0.28)",
        border: isRed ? "1.5px solid #7f1d1d" : "1.5px solid #9ca3af",
      }}
    >
      <span
        className="pointer-events-none absolute rounded-full"
        style={{
          inset: "18%",
          border: isRed
            ? "1.5px solid rgba(255,255,255,0.22)"
            : "1.5px solid rgba(0,0,0,0.12)",
        }}
      />
      <span
        className="pointer-events-none absolute rounded-full"
        style={{
          inset: "32%",
          border: isRed
            ? "1.5px solid rgba(255,255,255,0.16)"
            : "1.5px solid rgba(0,0,0,0.1)",
        }}
      />
      {king && (
        <span
          className="pointer-events-none absolute inset-0 flex items-center justify-center"
          aria-hidden
        >
          <Crown
            className={isRed ? "text-amber-200" : "text-amber-500"}
            strokeWidth={2.6}
            fill={isRed ? "rgba(251, 191, 36, 0.35)" : "rgba(245, 158, 11, 0.35)"}
            style={{
              width: compact ? 11 : "42%",
              height: compact ? 11 : "42%",
            }}
          />
        </span>
      )}
    </span>
  );
}
