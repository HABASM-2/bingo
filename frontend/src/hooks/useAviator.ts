import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWebSocket } from "./useWebSocket";
import type { WebSocketStatus } from "./useWebSocket";
import { aviatorWebSocketUrl } from "../services/aviator";
import type {
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

  const roundRef = useRef(round);
  const serverMultRef = useRef(AVIATOR_START_MULT);
  const animFrameRef = useRef<number | null>(null);

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
        case "cashout":
          if ("round" in data) applyRound(data.round);
          if (data.type === "cashout") {
            setMultiplier(data.multiplier);
            serverMultRef.current = data.multiplier;
          }
          setError(null);
          break;
        case "error":
          setError(data.message);
          break;
        default:
          break;
      }
    },
    [applyRound, applyBalance],
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
    setError(null);
    sendRef.current({ type: "bet", stake, slot });
  }, []);

  const cashOut = useCallback((slot?: number, betId?: string) => {
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
    placeBet,
    cashOut,
    clearError,
  };
}
