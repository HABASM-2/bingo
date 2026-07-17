import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWebSocket } from "./useWebSocket";
import type { WebSocketStatus } from "./useWebSocket";
import { bingoWebSocketUrl } from "../services/bingo";
import { getLanguage, mapServerMessage, tGlobal } from "../i18n";
import type {
  BingoClientMessage,
  BingoServerMessage,
  GameOverMessage,
  RoomStateMessage,
} from "../types/bingo";

interface UseBingoRoomResult {
  connectionStatus: WebSocketStatus;
  reconnectAttempt: number;
  latencyMs: number | null;
  roomState: RoomStateMessage | null;
  playerCount: number;
  currentBall: number | null;
  drawn: number[];
  secondsLeft: number;
  gameOver: GameOverMessage | null;
  toast: string | null;
  errorMessage: string | null;
  selectBoard: (boardId: number) => void;
  deselectBoard: (boardId: number) => void;
  deselectAll: () => void;
  claimBingo: (cardId: string) => void;
  refresh: () => void;
  dismissToast: () => void;
  showToast: (message: string) => void;
}

export function useBingoRoom(roomId: string | null, token: string | null): UseBingoRoomResult {
  const [roomState, setRoomState] = useState<RoomStateMessage | null>(null);
  const [playerCount, setPlayerCount] = useState(0);
  const [drawn, setDrawn] = useState<number[]>([]);
  const [currentBall, setCurrentBall] = useState<number | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [gameOver, setGameOver] = useState<GameOverMessage | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Countdown is driven by an authoritative server value but interpolated
  // locally so it ticks down smoothly and NEVER freezes between server
  // messages: we store the last server-reported seconds_left together with the
  // local clock time it arrived, then a 250ms interval derives the display.
  // Every lobby_tick / room_state re-locks onto the server truth. Using a
  // local arrival timestamp (instead of the server's absolute epoch) keeps the
  // countdown immune to client/server clock skew.
  const countdownBase = useRef<{ seconds: number; at: number } | null>(null);
  // Client-side debounce so a burst of taps on the same board (or a mashed
  // BINGO button) collapses to a single frame - the server also throttles,
  // but this keeps the socket quiet and the UI honest.
  const boardActionAt = useRef<Map<number, number>>(new Map());
  const claimActionAt = useRef<Map<string, number>>(new Map());
  const BOARD_TAP_COOLDOWN_MS = 200;
  const CLAIM_COOLDOWN_MS = 2500;

  const url = useMemo(() => {
    if (!roomId || !token) return null;

    return bingoWebSocketUrl(roomId, token);
  }, [roomId, token]);

  const flashToast = useCallback((message: string) => {
    setToast(message);

    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2600);
  }, []);

  // Lock the countdown onto a fresh server value (or stop it when we've left
  // the lobby phase).
  const syncCountdown = useCallback((seconds: number, isLobby: boolean) => {
    if (!isLobby) {
      countdownBase.current = null;
      setSecondsLeft(0);
      return;
    }

    countdownBase.current = { seconds: Math.max(0, seconds), at: Date.now() };
    setSecondsLeft(Math.max(0, seconds));
  }, []);

  const sendRef = useRef<((msg: BingoClientMessage) => void) | null>(null);

  const handleMessage = useCallback(
    (message: BingoServerMessage) => {
      switch (message.type) {
        case "room_state":
          setRoomState(message);
          setPlayerCount(
            message.player_count ?? message.players.filter((p) => p.connected).length,
          );
          setDrawn(message.drawn);
          setCurrentBall(message.current_ball);
          syncCountdown(message.seconds_left, message.status === "lobby");
          // Rehydrate the winner overlay after a refresh/reconnect: if the
          // room is still in its finished phase the full winner info lives on
          // the snapshot, so we rebuild the game_over view from it.
          if (message.status === "finished") {
            setGameOver({
              type: "game_over",
              winner: message.winner ?? null,
              winner_name: message.winner_name ?? null,
              pattern: message.winning_pattern ?? null,
              winning_card_id: message.winning_card_id ?? null,
              derash: message.derash,
              derash_share: message.derash_share,
              winners: message.winners ?? [],
              winner_count: message.winners?.length ?? 0,
            });
          } else {
            setGameOver(null);
          }
          break;

        case "player_count":
          setPlayerCount(message.count);
          break;

        case "player_left":
          setPlayerCount(message.count);
          setRoomState((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              players: prev.players.filter((p) => p.user_id !== message.user_id),
              player_count: message.count,
            };
          });
          break;

        case "board_delta":
          setRoomState((prev) => {
            if (!prev || prev.status !== "lobby") return prev;
            let myBoards = prev.my_boards;
            if (message.action === "released" && message.board_id != null) {
              myBoards = myBoards.filter((id) => id !== message.board_id);
            } else if (message.action === "released_all") {
              const drop = new Set(message.board_ids);
              myBoards = myBoards.filter((id) => !drop.has(id));
            }
            return {
              ...prev,
              my_boards: myBoards,
              taken_boards: message.taken_boards,
              selected_boards_count: message.selected_boards_count,
              players_in_round: message.players_in_round,
              projected_derash: message.projected_derash,
              derash: message.derash,
            };
          });
          break;

        case "lobby_tick":
          syncCountdown(message.seconds_left, true);
          break;

        case "ball":
          setDrawn(message.drawn);
          setCurrentBall(message.number);
          break;

        case "game_over":
          setGameOver(message);
          break;

        case "toast":
          flashToast(mapServerMessage(getLanguage(), message.message));
          break;

        case "error": {
          const localizedMessage = mapServerMessage(getLanguage(), message.message);
          setErrorMessage(localizedMessage);
          flashToast(localizedMessage);
          const raw = message.message.toLowerCase();
          if (
            raw.includes("board")
            || raw.includes("afford")
            || raw.includes("balance")
            || raw.includes("taken")
          ) {
            sendRef.current?.({ type: "join" });
          }
          break;
        }

        case "pong":
        case "bingo_result":
          if (message.type === "bingo_result" && !message.valid) {
            flashToast(
              message.reason
                ? mapServerMessage(getLanguage(), message.reason)
                : tGlobal("bingo.notWinner"),
            );
          }
          break;
      }
    },
    [flashToast, syncCountdown],
  );

  const { status, send, reconnectAttempt, latencyMs } = useWebSocket<
    BingoServerMessage,
    BingoClientMessage
  >({
    url,
    onMessage: handleMessage,
  });

  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  // Smoothly interpolate the countdown between server messages so it always
  // keeps ticking (never freezes) and can't drift negative.
  useEffect(() => {
    const id = setInterval(() => {
      const base = countdownBase.current;

      if (!base) return;

      const elapsed = (Date.now() - base.at) / 1000;
      const remaining = Math.max(0, Math.ceil(base.seconds - elapsed));

      setSecondsLeft((prev) => (prev === remaining ? prev : remaining));
    }, 250);

    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (status === "open") {
      send({ type: "join" });
    }
  }, [status, send]);

  useEffect(() => {
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  const boardTapAllowed = useCallback((boardId: number) => {
    const now = Date.now();
    const last = boardActionAt.current.get(boardId) ?? 0;

    if (now - last < BOARD_TAP_COOLDOWN_MS) return false;

    boardActionAt.current.set(boardId, now);
    return true;
  }, []);

  const selectBoard = useCallback(
    (boardId: number) => {
      if (!boardTapAllowed(boardId)) return;

      // Optimistic: turn this seat green + show cartela immediately. The next
      // personalized room_state from the server re-locks onto the truth
      // (including rejecting collisions with another player's claim).
      setRoomState((prev) => {
        if (!prev || prev.status !== "lobby") return prev;
        if (prev.my_boards.includes(boardId) || prev.taken_boards.includes(boardId)) {
          return prev;
        }
        if (prev.my_boards.length >= prev.max_boards) return prev;

        return {
          ...prev,
          my_boards: [...prev.my_boards, boardId].sort((a, b) => a - b),
          taken_boards: [...prev.taken_boards, boardId],
        };
      });

      send({ type: "select_board", board_id: boardId });
    },
    [send, boardTapAllowed],
  );

  const deselectBoard = useCallback(
    (boardId: number) => {
      if (!boardTapAllowed(boardId)) return;

      setRoomState((prev) => {
        if (!prev || prev.status !== "lobby") return prev;
        if (!prev.my_boards.includes(boardId)) return prev;

        return {
          ...prev,
          my_boards: prev.my_boards.filter((id) => id !== boardId),
          taken_boards: prev.taken_boards.filter((id) => id !== boardId),
        };
      });

      send({ type: "deselect_board", board_id: boardId });
    },
    [send, boardTapAllowed],
  );

  const deselectAll = useCallback(() => {
    setRoomState((prev) => {
      if (!prev || prev.status !== "lobby" || prev.my_boards.length === 0) return prev;

      const mine = new Set(prev.my_boards);

      return {
        ...prev,
        my_boards: [],
        taken_boards: prev.taken_boards.filter((id) => !mine.has(id)),
      };
    });

    send({ type: "deselect_all" });
  }, [send]);

  const claimBingo = useCallback(
    (cardId: string) => {
      const now = Date.now();
      const last = claimActionAt.current.get(cardId) ?? 0;

      if (now - last < CLAIM_COOLDOWN_MS) return;

      claimActionAt.current.set(cardId, now);
      send({ type: "claim_bingo", card_id: cardId });
    },
    [send],
  );

  const refresh = useCallback(() => send({ type: "join" }), [send]);

  const dismissToast = useCallback(() => setToast(null), []);

  return {
    connectionStatus: status,
    reconnectAttempt,
    latencyMs,
    roomState,
    playerCount,
    currentBall,
    drawn,
    secondsLeft,
    gameOver,
    toast,
    errorMessage,
    selectBoard,
    deselectBoard,
    deselectAll,
    claimBingo,
    refresh,
    dismissToast,
    showToast: flashToast,
  };
}
