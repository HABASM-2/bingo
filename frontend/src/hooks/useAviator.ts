import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWebSocket } from "./useWebSocket";
import type { WebSocketStatus } from "./useWebSocket";
import { aviatorWebSocketUrl } from "../services/aviator";
import type {
  AviatorBetRow,
  AviatorClientMessage,
  AviatorRoundState,
  AviatorServerMessage,
} from "../types/aviator";

/** Must match backend `crash.py`. */
export const AVIATOR_START_MULT = 1.0;
export const AVIATOR_MULT_GROWTH = 0.075;

interface UseAviatorOptions {
  token: string | null;
  enabled: boolean;
  onBalance?: (balance: string) => void;
}

function predictMultiplier(flyingStartedAt: number, crashCap?: number | null): number {
  const elapsed = Math.max(0, Date.now() / 1000 - flyingStartedAt);
  let mult = AVIATOR_START_MULT * Math.exp(AVIATOR_MULT_GROWTH * elapsed);
  if (crashCap != null && crashCap > 0) mult = Math.min(mult, crashCap);
  // Keep full precision for animation; the UI rounds only when rendering text.
  return mult;
}

export function useAviator({ token, enabled, onBalance }: UseAviatorOptions) {
  const [round, setRound] = useState<AviatorRoundState | null>(null);
  const [multiplier, setMultiplier] = useState(AVIATOR_START_MULT);
  const [displayMultiplier, setDisplayMultiplier] = useState(AVIATOR_START_MULT);
  const [history, setHistory] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [balance, setBalance] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<"bet" | "cashout" | null>(null);

  const roundRef = useRef(round);
  const serverMultRef = useRef(AVIATOR_START_MULT);
  const animFrameRef = useRef<number | null>(null);
  const pendingActionRef = useRef<"bet" | "cashout" | null>(null);

  useEffect(() => {
    roundRef.current = round;
  }, [round]);

  useEffect(() => {
    serverMultRef.current = multiplier;
  }, [multiplier]);

  useEffect(() => {
    if (!enabled) return;

    let lastTs = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.032, (now - lastTs) / 1000);
      lastTs = now;

      const rnd = roundRef.current;
      let target = serverMultRef.current;

      if (rnd?.phase === "flying" && rnd.flying_started_at) {
        target = predictMultiplier(rnd.flying_started_at, rnd.crash_multiplier);
      } else if (rnd?.phase === "crashed" && rnd.crash_multiplier) {
        target = rnd.crash_multiplier;
      }

      setDisplayMultiplier((prev) => {
        const diff = target - prev;
        if (Math.abs(diff) < 0.0005) return target;
        const alpha = 1 - Math.exp(-dt / 0.07);
        return prev + diff * alpha;
      });

      animFrameRef.current = requestAnimationFrame(tick);
    };

    animFrameRef.current = requestAnimationFrame(tick);
    return () => {
      if (animFrameRef.current != null) cancelAnimationFrame(animFrameRef.current);
    };
  }, [enabled]);

  const onBalanceRef = useRef(onBalance);
  useEffect(() => {
    onBalanceRef.current = onBalance;
  }, [onBalance]);

  const url = useMemo(() => {
    if (!enabled || !token) return null;
    return aviatorWebSocketUrl(token);
  }, [enabled, token]);

  const applyRound = useCallback((data: AviatorRoundState & { history?: number[] }) => {
    setRound(data);
    if (data.history) setHistory(data.history);
    if (data.multiplier != null) {
      setMultiplier(data.multiplier);
      serverMultRef.current = data.multiplier;
    } else if (data.phase === "betting" || data.phase === "waiting") {
      setMultiplier(AVIATOR_START_MULT);
      serverMultRef.current = AVIATOR_START_MULT;
    } else if (data.phase === "crashed" && data.crash_multiplier) {
      setMultiplier(data.crash_multiplier);
      serverMultRef.current = data.crash_multiplier;
    }
  }, []);

  const applyBalance = useCallback((value: string | undefined) => {
    if (!value) return;
    setBalance(value);
    onBalanceRef.current?.(value);
  }, []);

  const mergeBetDelta = useCallback(
    (data: {
      bet: AviatorBetRow;
      round_id: string;
      total_stake: string;
      total_payout: string;
      pool_remaining: string;
      player_count: number;
    }) => {
      setRound((prev) => {
        if (!prev || (prev.round_id && prev.round_id !== data.round_id)) {
          return prev;
        }
        const bets = [...(prev.bets ?? [])];
        const idx = bets.findIndex((b) => b.bet_id === data.bet.bet_id);
        if (idx >= 0) bets[idx] = data.bet;
        else bets.push(data.bet);
        return {
          ...prev,
          bets,
          total_stake: data.total_stake,
          total_payout: data.total_payout,
          pool_remaining: data.pool_remaining,
          player_count: data.player_count,
        };
      });
    },
    [],
  );

  const onMessage = useCallback(
    (data: AviatorServerMessage) => {
      if ("balance" in data && typeof data.balance === "string") {
        applyBalance(data.balance);
      }

      switch (data.type) {
        case "round_state":
        case "phase":
          applyRound(data);
          break;
        case "tick":
          setMultiplier(data.multiplier);
          serverMultRef.current = data.multiplier;
          setRound((prev) => (prev ? { ...prev, phase: data.phase } : prev));
          break;
        case "bet_placed":
          // Personal ack includes balance; broadcasts do not — only clear
          // pending on our own ack so other players' bets don't cancel ours.
          if (typeof data.balance === "string") {
            pendingActionRef.current = null;
            setPendingAction(null);
            setError(null);
          }
          mergeBetDelta(data);
          break;
        case "cashout":
          if (typeof data.balance === "string") {
            pendingActionRef.current = null;
            setPendingAction(null);
            setError(null);
          }
          mergeBetDelta({
            bet: data.bet,
            round_id: data.round_id,
            total_stake: data.total_stake,
            total_payout: data.total_payout,
            pool_remaining: data.pool_remaining,
            player_count: data.player_count,
          });
          setMultiplier(data.multiplier);
          serverMultRef.current = data.multiplier;
          break;
        case "error":
          pendingActionRef.current = null;
          setPendingAction(null);
          setError(data.message);
          break;
        default:
          break;
      }
    },
    [applyRound, applyBalance, mergeBetDelta],
  );

  const { status, send } = useWebSocket<AviatorServerMessage, AviatorClientMessage>({
    url,
    onMessage,
  });

  const sendRef = useRef(send);
  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  const placeBet = useCallback((stake: string, slot = 0) => {
    if (pendingActionRef.current) return;
    pendingActionRef.current = "bet";
    setPendingAction("bet");
    setError(null);
    sendRef.current({ type: "bet", stake, slot });
  }, []);

  const cashOut = useCallback((slot?: number, betId?: string) => {
    if (pendingActionRef.current) return;
    pendingActionRef.current = "cashout";
    setPendingAction("cashout");
    setError(null);
    sendRef.current({ type: "cashout", slot, bet_id: betId });
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    connectionStatus: status as WebSocketStatus,
    round,
    multiplier,
    displayMultiplier,
    history,
    balance,
    error,
    pendingAction,
    placeBet,
    cashOut,
    clearError,
  };
}
