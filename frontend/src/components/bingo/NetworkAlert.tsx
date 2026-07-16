import { useEffect, useRef, useState } from "react";
import { WifiOff, X } from "lucide-react";
import type { WebSocketStatus } from "../../hooks/useWebSocket";

interface NetworkAlertProps {
  connectionStatus: WebSocketStatus;
  reconnectAttempt: number;
  latencyMs: number | null;
}

interface NetworkInformation extends EventTarget {
  effectiveType?: string;
  downlink?: number;
  rtt?: number;
}

function getConnection(): NetworkInformation | undefined {
  const browserNavigator = navigator as Navigator & {
    connection?: NetworkInformation;
    mozConnection?: NetworkInformation;
    webkitConnection?: NetworkInformation;
  };

  return (
    browserNavigator.connection ??
    browserNavigator.mozConnection ??
    browserNavigator.webkitConnection
  );
}

function isWeakConnection(): boolean {
  const connection = getConnection();
  if (!connection) return false;

  return (
    connection.effectiveType === "slow-2g" ||
    connection.effectiveType === "2g" ||
    (connection.downlink != null && connection.downlink < 0.5) ||
    (connection.rtt != null && connection.rtt > 800)
  );
}

export function NetworkAlert({
  connectionStatus,
  reconnectAttempt,
  latencyMs,
}: NetworkAlertProps) {
  const [online, setOnline] = useState(() => navigator.onLine);
  const [rawWeak, setRawWeak] = useState(isWeakConnection);
  const [stableWeak, setStableWeak] = useState(false);
  const [highLatency, setHighLatency] = useState(false);
  const [socketSlow, setSocketSlow] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const slowLatencySamples = useRef(0);

  useEffect(() => {
    const connection = getConnection();
    const update = () => {
      setOnline(navigator.onLine);
      setRawWeak(isWeakConnection());
    };

    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    connection?.addEventListener("change", update);

    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
      connection?.removeEventListener("change", update);
    };
  }, []);

  // Network Information values fluctuate. Require five continuous seconds of
  // a weak reading before showing anything.
  useEffect(() => {
    if (!rawWeak) {
      setStableWeak(false);
      return;
    }

    const timer = setTimeout(() => setStableWeak(true), 5000);
    return () => clearTimeout(timer);
  }, [rawWeak]);

  // A single slow pong can be scheduling jitter. Require two consecutive
  // high-latency samples before warning.
  useEffect(() => {
    if (latencyMs === null || latencyMs <= 1800) {
      slowLatencySamples.current = 0;
      setHighLatency(false);
      return;
    }

    slowLatencySamples.current += 1;
    if (slowLatencySamples.current >= 2) setHighLatency(true);
  }, [latencyMs]);

  // Avoid warning during a normal, momentary reconnect.
  useEffect(() => {
    if (connectionStatus === "open" || connectionStatus === "idle") {
      setSocketSlow(false);
      return;
    }

    const timer = setTimeout(() => setSocketSlow(true), 6000);
    return () => clearTimeout(timer);
  }, [connectionStatus]);

  const hasIssue =
    !online ||
    stableWeak ||
    highLatency ||
    socketSlow ||
    reconnectAttempt >= 3;

  // Once healthy again, allow a future real issue to display.
  useEffect(() => {
    if (!hasIssue) setDismissed(false);
  }, [hasIssue]);

  if (!hasIssue || dismissed) return null;

  const message = !online
    ? "You are offline. Check your internet connection."
    : "Weak network detected. Move to a stronger connection to avoid missing calls.";

  return (
    <div className="fixed left-1/2 top-3 z-[60] flex w-[92%] max-w-sm -translate-x-1/2 items-center gap-2 rounded-2xl bg-amber-500 py-3 pl-4 pr-2 text-sm font-bold text-amber-950 shadow-xl ring-1 ring-amber-300">
      <WifiOff size={19} className="shrink-0" />
      <span className="flex-1">{message}</span>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-950/10 transition hover:bg-amber-950/20 active:scale-90"
        aria-label="Dismiss network warning"
      >
        <X size={18} strokeWidth={2.5} />
      </button>
    </div>
  );
}
