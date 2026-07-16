import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWebSocket } from "./useWebSocket";
import type { WebSocketStatus } from "./useWebSocket";
import { damaWebSocketUrl } from "../services/dama";
import type {
  DamaChallenge,
  DamaClientMessage,
  DamaMatchStateMessage,
  DamaOnlinePlayer,
  DamaServerMessage,
  DamaServerMove,
  DamaSide,
} from "../types/dama";
import type { Board, Move, Outcome } from "../games/dama/engine";

export interface DamaOnlineMatch {
  matchId: string;
  board: Board;
  turn: DamaSide;
  mySide: DamaSide;
  status: "playing" | "finished";
  winner: Outcome;
  lastMove: Move | null;
  stake: string;
  pot: string;
  prizePool: string;
  plyCount: number;
  quietPlies: number;
  drawEligible: boolean;
  drawOfferBy: string | null;
  rematchOfferBy: string | null;
  rematchStake: string | null;
  rematchPeerLeft: boolean;
  turnDeadline: number | null;
  red: { user_id: string; display_name: string };
  black: { user_id: string; display_name: string };
}

function toBoard(raw: DamaMatchStateMessage["board"]): Board {
  return raw.map((p) => (p ? { side: p.side, kind: p.kind } : null));
}

function toMove(raw: DamaServerMove | null | undefined): Move | null {
  if (!raw) return null;
  return {
    from: raw.from,
    to: raw.to,
    captures: raw.captures ?? [],
    path: raw.path ?? [raw.to],
    promote: Boolean(raw.promote),
  };
}

function toMatch(msg: DamaMatchStateMessage): DamaOnlineMatch | null {
  if (!msg.my_side) return null;
  return {
    matchId: msg.match_id,
    board: toBoard(msg.board),
    turn: msg.turn,
    mySide: msg.my_side,
    status: msg.status,
    winner: msg.winner,
    lastMove: toMove(msg.last_move),
    stake: msg.stake ?? "0",
    pot: msg.pot ?? "0",
    prizePool: msg.prize_pool ?? "0",
    plyCount: msg.ply_count ?? 0,
    quietPlies: msg.quiet_plies ?? 0,
    drawEligible: Boolean(msg.draw_eligible),
    drawOfferBy: msg.draw_offer_by ?? null,
    rematchOfferBy: msg.rematch_offer_by ?? null,
    rematchStake: msg.rematch_stake ?? null,
    rematchPeerLeft: false,
    turnDeadline: msg.turn_deadline ?? null,
    red: msg.red,
    black: msg.black,
  };
}

interface UseDamaOnlineOptions {
  token: string | null;
  enabled: boolean;
  onBalance?: (balance: string) => void;
}

export function useDamaOnline({ token, enabled, onBalance }: UseDamaOnlineOptions) {
  const [players, setPlayers] = useState<DamaOnlinePlayer[]>([]);
  const [incoming, setIncoming] = useState<DamaChallenge | null>(null);
  const [outgoing, setOutgoing] = useState<DamaChallenge | null>(null);
  const [match, setMatch] = useState<DamaOnlineMatch | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onBalanceRef = useRef(onBalance);
  useEffect(() => {
    onBalanceRef.current = onBalance;
  }, [onBalance]);

  const url = useMemo(() => {
    if (!enabled || !token) return null;
    return damaWebSocketUrl(token);
  }, [enabled, token]);

  const onMessage = useCallback((data: DamaServerMessage) => {
    if ("balance" in data && typeof data.balance === "string" && data.balance) {
      onBalanceRef.current?.(data.balance);
    }

    switch (data.type) {
      case "players": {
        setPlayers(data.players.filter((p) => !p.is_self));
        if (data.resume_match) {
          const resumed = toMatch({ ...data.resume_match, type: "match_state" });
          if (resumed) setMatch(resumed);
        }
        break;
      }
      case "presence": {
        if (data.action === "leave" && data.user_id) {
          setPlayers((prev) => prev.filter((p) => p.user_id !== data.user_id));
          break;
        }
        if (data.player) {
          if (data.player.is_self) break;
          setPlayers((prev) => {
            const rest = prev.filter((p) => p.user_id !== data.player!.user_id);
            if (data.action === "leave") return rest;
            return [...rest, data.player!].sort((a, b) =>
              a.display_name.localeCompare(b.display_name),
            );
          });
        }
        break;
      }
      case "challenge_sent":
        setOutgoing(data.challenge);
        setError(null);
        break;
      case "challenge_incoming":
        setIncoming(data.challenge);
        setError(null);
        break;
      case "challenge_declined":
        setIncoming((c) => (c?.id === data.challenge_id ? null : c));
        setOutgoing((c) => (c?.id === data.challenge_id ? null : c));
        break;
      case "match_start":
      case "match_state": {
        const next = toMatch(data);
        if (next) {
          setMatch(next);
          setIncoming(null);
          setOutgoing(null);
        }
        break;
      }
      case "move_applied": {
        setMatch((prev) => {
          if (!prev || prev.matchId !== data.match_id) return prev;
          return {
            ...prev,
            board: toBoard(data.board),
            turn: data.turn,
            status: data.status,
            winner: data.winner,
            lastMove: toMove(data.move),
            stake: data.stake ?? prev.stake,
            prizePool: data.prize_pool ?? prev.prizePool,
            plyCount: data.ply_count ?? prev.plyCount,
            quietPlies: data.quiet_plies ?? prev.quietPlies,
            drawEligible: data.draw_eligible ?? prev.drawEligible,
            drawOfferBy: data.draw_offer_by ?? null,
            turnDeadline: data.turn_deadline ?? prev.turnDeadline,
          };
        });
        break;
      }
      case "match_over": {
        setMatch((prev) => {
          if (!prev || prev.matchId !== data.match_id) return prev;
          return {
            ...prev,
            board: toBoard(data.board),
            turn: data.turn,
            status: "finished",
            winner: data.winner,
            stake: data.stake ?? prev.stake,
            prizePool: data.prize_pool ?? prev.prizePool,
            drawOfferBy: null,
          };
        });
        break;
      }
      case "draw_offered": {
        setMatch((prev) => {
          if (!prev || prev.matchId !== data.match_id) return prev;
          return {
            ...prev,
            drawOfferBy: data.by_user_id,
            drawEligible: data.draw_eligible ?? prev.drawEligible,
          };
        });
        break;
      }
      case "draw_declined": {
        setMatch((prev) => {
          if (!prev || prev.matchId !== data.match_id) return prev;
          return { ...prev, drawOfferBy: null };
        });
        break;
      }
      case "rematch_offered": {
        setMatch((prev) => {
          if (!prev || prev.matchId !== data.match_id) return prev;
          return {
            ...prev,
            rematchOfferBy: data.by_user_id,
            rematchStake: data.stake ?? prev.rematchStake,
            rematchPeerLeft:
              data.peer_online === false || data.delivered === false
                ? true
                : false,
          };
        });
        break;
      }
      case "rematch_peer_left": {
        setMatch((prev) => {
          if (!prev || prev.matchId !== data.match_id) return prev;
          return {
            ...prev,
            rematchOfferBy: null,
            rematchPeerLeft: true,
          };
        });
        break;
      }
      case "error":
        setError(data.message);
        break;
      default:
        break;
    }
  }, []);

  const { status, send } = useWebSocket<DamaServerMessage, DamaClientMessage>({
    url,
    onMessage,
  });

  const sendRef = useRef(send);
  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  const challenge = useCallback((toUserId: string, stake: string) => {
    setError(null);
    sendRef.current({ type: "challenge", to_user_id: toUserId, stake });
  }, []);

  const acceptChallenge = useCallback((challengeId: string) => {
    sendRef.current({ type: "accept_challenge", challenge_id: challengeId });
  }, []);

  const declineChallenge = useCallback((challengeId: string) => {
    sendRef.current({ type: "decline_challenge", challenge_id: challengeId });
    setIncoming(null);
  }, []);

  const cancelChallenge = useCallback((challengeId: string) => {
    sendRef.current({ type: "cancel_challenge", challenge_id: challengeId });
    setOutgoing(null);
  }, []);

  const sendMove = useCallback((matchId: string, from: number, to: number) => {
    sendRef.current({ type: "move", match_id: matchId, from, to });
  }, []);

  const resign = useCallback((matchId: string) => {
    sendRef.current({ type: "resign", match_id: matchId });
  }, []);

  const claimTimeout = useCallback((matchId: string) => {
    sendRef.current({ type: "claim_timeout", match_id: matchId });
  }, []);

  const offerDraw = useCallback((matchId: string) => {
    sendRef.current({ type: "offer_draw", match_id: matchId });
  }, []);

  const acceptDraw = useCallback((matchId: string) => {
    sendRef.current({ type: "accept_draw", match_id: matchId });
  }, []);

  const declineDraw = useCallback((matchId: string) => {
    sendRef.current({ type: "decline_draw", match_id: matchId });
  }, []);

  const offerRematch = useCallback((matchId: string, stake?: string) => {
    sendRef.current({ type: "offer_rematch", match_id: matchId, stake });
  }, []);

  const acceptRematch = useCallback((matchId: string, stake?: string) => {
    sendRef.current({ type: "accept_rematch", match_id: matchId, stake });
  }, []);

  const clearMatch = useCallback(() => {
    setMatch(null);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    connectionStatus: status as WebSocketStatus,
    players,
    incoming,
    outgoing,
    match,
    error,
    challenge,
    acceptChallenge,
    declineChallenge,
    cancelChallenge,
    sendMove,
    resign,
    claimTimeout,
    offerDraw,
    acceptDraw,
    declineDraw,
    offerRematch,
    acceptRematch,
    clearMatch,
    clearError,
  };
}
