import { useCallback, useEffect, useRef, useState } from "react";

export type WebSocketStatus = "idle" | "connecting" | "open" | "closed";

interface UseWebSocketOptions<TIncoming> {
  /** Pass `null` to stay disconnected (e.g. while waiting for a room id). */
  url: string | null;
  onMessage?: (data: TIncoming) => void;
  heartbeatIntervalMs?: number;
  heartbeatMessage?: unknown;
  baseReconnectDelayMs?: number;
  maxReconnectDelayMs?: number;
}

interface UseWebSocketResult<TOutgoing> {
  status: WebSocketStatus;
  send: (message: TOutgoing) => void;
  reconnectAttempt: number;
}

/**
 * Small reconnecting WebSocket client: exponential backoff on drop, an
 * outbound queue so `send()` never throws while disconnected (messages are
 * flushed once the socket reopens), and a ping heartbeat to keep the
 * connection (and any proxies in between) alive.
 */
export function useWebSocket<TIncoming = unknown, TOutgoing = unknown>({
  url,
  onMessage,
  heartbeatIntervalMs = 25000,
  heartbeatMessage = { type: "ping" },
  baseReconnectDelayMs = 1000,
  maxReconnectDelayMs = 15000,
}: UseWebSocketOptions<TIncoming>): UseWebSocketResult<TOutgoing> {
  const [status, setStatus] = useState<WebSocketStatus>("idle");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const queueRef = useRef<TOutgoing[]>([]);
  const onMessageRef = useRef(onMessage);
  const heartbeatMessageRef = useRef(heartbeatMessage);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptRef = useRef(0);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    heartbeatMessageRef.current = heartbeatMessage;
  }, [heartbeatMessage]);

  const flushQueue = useCallback((socket: WebSocket) => {
    while (queueRef.current.length > 0) {
      const next = queueRef.current.shift();

      if (next !== undefined) {
        socket.send(JSON.stringify(next));
      }
    }
  }, []);

  const send = useCallback((message: TOutgoing) => {
    const socket = socketRef.current;

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message));
    } else {
      queueRef.current.push(message);
    }
  }, []);

  useEffect(() => {
    if (!url) {
      setStatus("idle");
      return;
    }

    let cancelled = false;

    const clearHeartbeat = () => {
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = null;
      }
    };

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const connect = () => {
      if (cancelled) return;

      setStatus("connecting");

      const socket = new WebSocket(url);
      socketRef.current = socket;

      socket.onopen = () => {
        if (cancelled) return;

        attemptRef.current = 0;
        setReconnectAttempt(0);
        setStatus("open");
        flushQueue(socket);

        clearHeartbeat();
        heartbeatTimerRef.current = setInterval(() => {
          send(heartbeatMessageRef.current as TOutgoing);
        }, heartbeatIntervalMs);
      };

      socket.onmessage = (event) => {
        if (cancelled) return;

        try {
          const parsed = JSON.parse(event.data) as TIncoming;
          onMessageRef.current?.(parsed);
        } catch {
          // Ignore malformed frames rather than crashing the connection.
        }
      };

      socket.onclose = () => {
        clearHeartbeat();

        if (cancelled) return;

        setStatus("closed");

        const attempt = attemptRef.current + 1;
        attemptRef.current = attempt;
        setReconnectAttempt(attempt);

        const delay = Math.min(
          baseReconnectDelayMs * 2 ** (attempt - 1),
          maxReconnectDelayMs,
        );

        clearReconnectTimer();
        reconnectTimerRef.current = setTimeout(connect, delay);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      cancelled = true;

      clearReconnectTimer();
      clearHeartbeat();

      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [url, flushQueue, send, heartbeatIntervalMs, baseReconnectDelayMs, maxReconnectDelayMs]);

  return { status, send, reconnectAttempt };
}
