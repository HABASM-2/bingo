import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { useBingoRoom } from "../../hooks/useBingoRoom";
import { findOrCreateRoom } from "../../services/bingo";
import { getMe } from "../../services/auth";
import type { BingoCard } from "../../types/bingo";
import { BottomNav } from "./BottomNav";
import type { NavTab } from "./BottomNav";
import { LobbyView } from "./LobbyView";
import { ActiveGameView } from "./ActiveGameView";
import { SpectatorView } from "./SpectatorView";
import { WinnerOverlay } from "./WinnerOverlay";
import { ProfileHub } from "./ProfileHub";

interface BingoGameProps {
  userId: string;
  firstName: string;
  /** Real Postgres balance from the authenticated `/api/auth/me` user, as
   * already resolved by `useAuth`. Used to seed the wallet immediately so it
   * never flashes a shared/template number while the room connects. */
  authBalance?: string;
  /** Fresh JWT from this Telegram launch — never read a sticky localStorage
   * value that might belong to a previous Mini App session. */
  accessToken: string;
  onExit?: () => void;
}

/** Placeholder shown while we have no confirmed, per-user balance yet.
 * Deliberately NOT a number - must never be mistaken for a real wallet. */
const WALLET_LOADING_PLACEHOLDER = "—";

const WINNER_OVERLAY_SECONDS = 5;
/** Let players see the last call + glowing win line before the dialog. */
const WIN_HOLD_MS = 1500;

function playBeep() {
  try {
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;

    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 660;
    osc.connect(gain);
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
    osc.onended = () => ctx.close();
  } catch {
    // Audio is best-effort.
  }
}

export default function BingoGame({
  userId,
  firstName,
  authBalance,
  accessToken,
  onExit,
}: BingoGameProps) {
  const [roomId, setRoomId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<NavTab>("bingo");
  const [soundOn, setSoundOn] = useState(true);
  const [autoOn, setAutoOn] = useState(true);
  const [showWinnerDialog, setShowWinnerDialog] = useState(false);

  // Lobby/Wallet/Profile always show THIS user's Postgres balance from
  // `/api/auth/me`. Redis `player_balance` is only a game-side cache and must
  // never overwrite the wallet (it historically showed shared/stale numbers).
  const [walletBalance, setWalletBalance] = useState<string | null>(authBalance ?? null);

  const lastBeepBall = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    findOrCreateRoom()
      .then((room) => {
        if (!cancelled) setRoomId(room.room_id);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Could not reach the Bingo server. Please try again.");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Authoritative refresh straight from the DB-backed `/api/auth/me`
  // endpoint. Runs on mount regardless of whether `authBalance` was already
  // supplied, so the wallet can never drift from what Postgres actually has
  // for THIS user.
  const refreshWalletFromAuth = useCallback(() => {
    getMe()
      .then((me) => setWalletBalance(me.balance))
      .catch(() => {
        // Leave the last known-good value in place; a transient failure here
        // must never blank the wallet or fall back to a fake number.
      });
  }, []);

  useEffect(() => {
    refreshWalletFromAuth();
  }, [refreshWalletFromAuth]);

  useEffect(() => {
    if (authBalance != null) {
      setWalletBalance(authBalance);
    }
  }, [authBalance]);

  const {
    connectionStatus,
    roomState,
    currentBall,
    drawn,
    secondsLeft,
    gameOver,
    toast,
    selectBoard,
    deselectBoard,
    deselectAll,
    claimBingo,
    showToast,
  } = useBingoRoom(roomId, accessToken);

  // Re-fetch from Postgres when stakes are charged (round starts) or when
  // derash is paid (game over) - never trust Redis for the wallet readout.
  useEffect(() => {
    if (roomState?.status === "in_progress" || gameOver) {
      refreshWalletFromAuth();
    }
  }, [roomState?.status, gameOver, refreshWalletFromAuth]);

  useEffect(() => {
    if (soundOn && currentBall !== null && currentBall !== lastBeepBall.current) {
      lastBeepBall.current = currentBall;
      playBeep();
    }
  }, [currentBall, soundOn]);

  // Hold the winning line / last call on screen briefly, then open the dialog.
  useEffect(() => {
    if (!gameOver) {
      setShowWinnerDialog(false);
      return;
    }

    setShowWinnerDialog(false);
    const timer = setTimeout(() => setShowWinnerDialog(true), WIN_HOLD_MS);

    return () => clearTimeout(timer);
  }, [gameOver]);

  const handleToggleBoard = useCallback(
    (boardId: number) => {
      const mine = roomState?.my_boards ?? [];
      if (mine.includes(boardId)) {
        deselectBoard(boardId);
        return;
      }

      const price = Number(roomState?.board_price ?? 0);
      const balance = Number(walletBalance);
      const nextCost = price * (mine.length + 1);

      if (!Number.isFinite(balance) || !Number.isFinite(price) || price <= 0) {
        selectBoard(boardId);
        return;
      }

      if (balance < price) {
        showToast(
          balance <= 0
            ? "Insufficient balance — deposit to pick a board."
            : `Insufficient balance — stake is ${price} ETB per board.`,
        );
        return;
      }

      if (balance < nextCost) {
        const affordable = Math.floor(balance / price);
        showToast(
          `Insufficient balance — you can only afford ${affordable} board(s).`,
        );
        return;
      }

      selectBoard(boardId);
    },
    [roomState, walletBalance, selectBoard, deselectBoard, showToast],
  );

  if (loadError) {
    return (
      <Shell onExit={onExit}>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
          <AlertCircle size={40} className="text-red-500" />
          <p className="text-sm text-purple-700">{loadError}</p>
        </div>
      </Shell>
    );
  }

  if (!roomId || !roomState) {
    return (
      <Shell onExit={onExit}>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-purple-500">
          <Loader2 size={32} className="animate-spin" />
          <p className="text-sm">Connecting to the Bingo room…</p>
        </div>
      </Shell>
    );
  }

  const inGame = roomState.status === "in_progress" || roomState.status === "finished";
  // Prefer server-issued cards; if the kickoff snapshot lags, fall back to
  // the boards this player reserved so a paying player never lands on the
  // spectator "please wait" screen.
  const playCards =
    roomState.cards.length > 0
      ? roomState.cards
      : (roomState.my_boards ?? []).map((boardId) => ({
          card_id: String(boardId),
          numbers: [] as BingoCard["numbers"],
          marks: [] as BingoCard["marks"],
        }));
  const isPlayer = playCards.length > 0;
  const youWon =
    gameOver != null &&
    ((gameOver.winners ?? []).some((w) => w.user_id === userId) ||
      gameOver.winner === userId);
  const winHold = gameOver != null && !showWinnerDialog;
  const winnersList = gameOver?.winners ?? roomState.winners ?? [];

  return (
    <Shell onExit={onExit} live={connectionStatus === "open"}>
      {inGame ? (
        isPlayer ? (
          <ActiveGameView
            room={roomState}
            drawn={drawn}
            currentBall={currentBall}
            cards={playCards}
            soundOn={soundOn}
            autoOn={autoOn}
            onToggleSound={() => setSoundOn((v) => !v)}
            onToggleAuto={() => setAutoOn((v) => !v)}
            onClaim={claimBingo}
            onRefresh={() => window.location.reload()}
            winHold={winHold}
            winners={winnersList}
          />
        ) : (
          <SpectatorView
            room={roomState}
            drawn={drawn}
            currentBall={currentBall}
            soundOn={soundOn}
            onToggleSound={() => setSoundOn((v) => !v)}
            winHold={winHold}
          />
        )
      ) : (
        <>
          <div className="flex-1 overflow-y-auto">
            {tab === "bingo" && (
              <LobbyView
                secondsLeft={secondsLeft}
                balance={walletBalance ?? WALLET_LOADING_PLACEHOLDER}
                boardPrice={roomState.board_price}
                poolMax={roomState.board_pool_max}
                maxBoards={roomState.max_boards}
                myBoards={roomState.my_boards ?? []}
                takenBoards={roomState.taken_boards ?? []}
                onToggleBoard={handleToggleBoard}
                onDeselectAll={deselectAll}
              />
            )}

            {tab === "profile" && (
              <ProfileHub
                firstName={firstName}
                balance={walletBalance}
                boardPrice={roomState.board_price}
              />
            )}
          </div>

          <BottomNav active={tab} onChange={setTab} />
        </>
      )}

      {showWinnerDialog && gameOver && (
        <WinnerOverlay
          winners={winnersList}
          winnerName={gameOver.winner_name ?? null}
          derash={gameOver.derash ?? roomState.derash}
          derashShare={gameOver.derash_share ?? roomState.derash_share}
          drawn={drawn}
          youWon={youWon}
          seconds={WINNER_OVERLAY_SECONDS}
        />
      )}

      {toast && (
        <div className="fixed bottom-24 left-1/2 z-40 w-[88%] max-w-sm -translate-x-1/2 rounded-2xl bg-[#4C1D95] px-5 py-3 text-center text-sm font-semibold text-white shadow-2xl">
          {toast}
        </div>
      )}
    </Shell>
  );
}

function Shell({
  children,
}: {
  children: ReactNode;
  onExit?: () => void;
  live?: boolean;
}) {
  return (
    <div className="mx-auto flex h-[100dvh] max-w-md flex-col bg-gradient-to-b from-[#EDE4F8] via-[#E7DEF6] to-[#DDD0F2] transition-colors duration-300 dark:from-[#12101A] dark:via-[#14121F] dark:to-[#0E0C16]">
      {children}
    </div>
  );
}
