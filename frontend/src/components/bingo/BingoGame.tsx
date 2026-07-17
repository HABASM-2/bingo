import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { useI18n } from "../../i18n";
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
import { HomeView } from "./HomeView";
import { NetworkAlert } from "./NetworkAlert";
import { getAdminMe } from "../../services/admin";
import {
  BINGO_AUDIO_SRC,
  NEW_GAME_AUDIO_SRC,
  enableGameAudio,
  numberAudioSrc,
  playGameAudio,
  preloadEventSounds,
  stopGameAudio,
} from "../../utils/gameAudio";
import {
  launchGameToTab,
  readTelegramLaunch,
} from "../../utils/telegramLaunch";
import type { RoomStatus } from "../../types/bingo";

const AdminDashboard = lazy(() =>
  import("../admin/AdminDashboard").then((m) => ({ default: m.AdminDashboard })),
);
const DamaGame = lazy(() =>
  import("../dama/DamaGame").then((m) => ({ default: m.DamaGame })),
);
const AviatorGame = lazy(() =>
  import("../aviator/AviatorGame").then((m) => ({ default: m.AviatorGame })),
);
const PlinkoGame = lazy(() =>
  import("../plinko/PlinkoGame").then((m) => ({ default: m.PlinkoGame })),
);
const LottoSpinGame = lazy(() =>
  import("../lotto/LottoSpinGame").then((m) => ({ default: m.LottoSpinGame })),
);

type KeepAliveGame = "dama" | "aviator" | "plinko" | "lotto";

function GameChunkFallback() {
  return (
    <div className="flex flex-1 items-center justify-center p-10">
      <Loader2 className="animate-spin text-violet-600" aria-label="Loading" />
    </div>
  );
}

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

export default function BingoGame({
  userId,
  firstName,
  authBalance,
  accessToken,
  onExit,
}: BingoGameProps) {
  const { t } = useI18n();
  const translateRef = useRef(t);
  translateRef.current = t;
  const [roomId, setRoomId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<NavTab>("home");
  const [isAdmin, setIsAdmin] = useState(false);
  const [mountedGames, setMountedGames] = useState<Partial<Record<KeepAliveGame, true>>>({});
  const [soundOn, setSoundOn] = useState(true);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [audioRetryToken, setAudioRetryToken] = useState(0);
  const [autoOn, setAutoOn] = useState(true);
  const [showWinnerDialog, setShowWinnerDialog] = useState(false);
  const deepLinkConsumed = useRef(false);
  const adminDeepLinkRequested = useRef(false);

  // Open a specific game once when launched via bot deep link / start_param.
  useEffect(() => {
    if (deepLinkConsumed.current) return;
    deepLinkConsumed.current = true;
    const { game } = readTelegramLaunch();
    if (game === "admin") adminDeepLinkRequested.current = true;
    else if (game) setTab(launchGameToTab(game));
  }, []);

  // Navigation capability comes only from the server-authorized endpoint.
  useEffect(() => {
    let active = true;
    getAdminMe()
      .then((capability) => {
        if (!active) return;
        setIsAdmin(capability.is_admin);
        if (adminDeepLinkRequested.current) {
          setTab(capability.is_admin ? "admin" : "home");
        }
      })
      .catch(() => {
        if (active) {
          setIsAdmin(false);
          if (adminDeepLinkRequested.current) setTab("home");
        }
      });
    return () => { active = false; };
  }, [accessToken]);

  // Mount heavy game chunks once on first visit; keep them hidden (WS keep-alive).
  if (
    (tab === "dama" || tab === "aviator" || tab === "plinko" || tab === "lotto") &&
    !mountedGames[tab]
  ) {
    setMountedGames((prev) => (prev[tab] ? prev : { ...prev, [tab]: true }));
  }

  const handleAdminAccessDenied = useCallback(() => {
    setIsAdmin(false);
    setTab("home");
  }, []);

  // Lobby/Wallet/Profile always show THIS user's Postgres balance from
  // `/api/auth/me`. Redis `player_balance` is only a game-side cache and must
  // never overwrite the wallet (it historically showed shared/stale numbers).
  const [walletBalance, setWalletBalance] = useState<string | null>(authBalance ?? null);

  const lastSpokenBall = useRef<number | null>(null);
  const previousRoomStatus = useRef<RoomStatus | null>(null);

  useEffect(() => {
    const removeAudioUnlock = preloadEventSounds(() => {
      setAudioBlocked(false);
      setAudioRetryToken((value) => value + 1);
    });

    return () => {
      removeAudioUnlock();
      stopGameAudio();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    findOrCreateRoom()
      .then((room) => {
        if (!cancelled) setRoomId(room.room_id);
      })
      .catch(() => {
        if (!cancelled) setLoadError(translateRef.current("bingo.loadError"));
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
    reconnectAttempt,
    latencyMs,
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

  const onBingoTab = tab === "bingo";
  const wasOnBingoTab = useRef(onBingoTab);

  // Silence bingo audio when leaving the Bingo tab, but keep soundOn so
  // returning restores the previous preference without replaying missed calls.
  useEffect(() => {
    const justEnteredBingo = onBingoTab && !wasOnBingoTab.current;

    if (!onBingoTab) {
      stopGameAudio();
    } else if (justEnteredBingo && currentBall !== null) {
      lastSpokenBall.current = currentBall;
    }

    wasOnBingoTab.current = onBingoTab;
  }, [onBingoTab, currentBall]);

  // Speak each called number only while the Bingo tab is visible.
  useEffect(() => {
    if (
      onBingoTab &&
      soundOn &&
      roomState?.status === "in_progress" &&
      currentBall !== null &&
      currentBall !== lastSpokenBall.current
    ) {
      const ball = currentBall;
      void playGameAudio(numberAudioSrc(ball)).then((played) => {
        if (played) {
          lastSpokenBall.current = ball;
          setAudioBlocked(false);
        } else {
          setAudioBlocked(true);
        }
      });
    }
  }, [audioRetryToken, currentBall, onBingoTab, roomState?.status, soundOn]);

  // Play the round-start beat only on the real lobby -> game transition.
  // Also jump onto the Bingo tab so the live round overlays the interface.
  useEffect(() => {
    const nextStatus = roomState?.status ?? null;
    const previousStatus = previousRoomStatus.current;

    if (previousStatus === "lobby" && nextStatus === "in_progress") {
      setTab("bingo");
      if (soundOn) void playGameAudio(NEW_GAME_AUDIO_SRC);
    }

    if (nextStatus === "lobby") {
      lastSpokenBall.current = null;
    }

    previousRoomStatus.current = nextStatus;
  }, [roomState?.status, soundOn]);

  useEffect(() => {
    if (!onBingoTab || !soundOn) stopGameAudio();
  }, [onBingoTab, soundOn]);

  const handleToggleSound = useCallback(() => {
    if (soundOn) {
      setSoundOn(false);
      setAudioBlocked(false);
      return;
    }

    lastSpokenBall.current = null;
    setSoundOn(true);
    setAudioRetryToken((value) => value + 1);
  }, [soundOn]);

  const handleEnableAudio = useCallback(() => {
    void enableGameAudio().then((enabled) => {
      setAudioBlocked(!enabled);
      if (enabled && currentBall !== null) {
        lastSpokenBall.current = currentBall;
      }
    });
  }, [currentBall]);

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

  // Winner sound only while Bingo is the active tab.
  useEffect(() => {
    if (onBingoTab && soundOn && showWinnerDialog && gameOver) {
      void playGameAudio(BINGO_AUDIO_SRC);
    }
  }, [gameOver, onBingoTab, showWinnerDialog, soundOn]);

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
            ? t("bingo.insufficientDeposit")
            : t("bingo.insufficientStake", { price }),
        );
        return;
      }

      if (balance < nextCost) {
        const affordable = Math.floor(balance / price);
        showToast(
          t("bingo.insufficientAfford", { count: affordable }),
        );
        return;
      }

      selectBoard(boardId);
    },
    [roomState, walletBalance, selectBoard, deselectBoard, showToast, t],
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
          <p className="text-sm">{t("loading.subtitle")}</p>
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
      {onBingoTab && (
        <NetworkAlert
          connectionStatus={connectionStatus}
          reconnectAttempt={reconnectAttempt}
          latencyMs={latencyMs}
        />
      )}

      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        {tab === "home" && (
          <HomeView
            firstName={firstName}
            balance={walletBalance ?? WALLET_LOADING_PLACEHOLDER}
            bingoPlayers={
              inGame
                ? roomState.players_in_round
                : (roomState.player_count ?? roomState.players_in_round)
            }
            bingoLive={inGame}
            bingoSecondsLeft={secondsLeft}
            onOpenGame={(game) => setTab(game)}
          />
        )}

        {tab === "bingo" &&
          (inGame ? (
            isPlayer ? (
              <ActiveGameView
                room={roomState}
                drawn={drawn}
                currentBall={currentBall}
                cards={playCards}
                soundOn={soundOn}
                audioBlocked={audioBlocked}
                autoOn={autoOn}
                onToggleSound={handleToggleSound}
                onEnableAudio={handleEnableAudio}
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
                audioBlocked={audioBlocked}
                onToggleSound={handleToggleSound}
                onEnableAudio={handleEnableAudio}
                winHold={winHold}
              />
            )
          ) : (
            <div className="flex-1 overflow-y-auto">
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
            </div>
          ))}

        {mountedGames.dama && (
          <div
            className={
              tab === "dama"
                ? "flex min-h-0 flex-1 flex-col overflow-hidden"
                : "hidden"
            }
          >
            <Suspense fallback={<GameChunkFallback />}>
              <DamaGame
                accessToken={accessToken}
                userId={userId}
                firstName={firstName}
                walletBalance={walletBalance}
                onBalanceChange={setWalletBalance}
                isActive={tab === "dama"}
              />
            </Suspense>
          </div>
        )}

        {mountedGames.aviator && (
          <div
            className={
              tab === "aviator"
                ? "flex min-h-0 flex-1 flex-col overflow-hidden"
                : "hidden"
            }
          >
            <Suspense fallback={<GameChunkFallback />}>
              <AviatorGame
                accessToken={accessToken}
                userId={userId}
                firstName={firstName}
                walletBalance={walletBalance}
                onBalanceChange={setWalletBalance}
                isActive={tab === "aviator"}
              />
            </Suspense>
          </div>
        )}

        {mountedGames.plinko && (
          <div
            className={
              tab === "plinko"
                ? "flex min-h-0 flex-1 flex-col overflow-hidden"
                : "hidden"
            }
          >
            <Suspense fallback={<GameChunkFallback />}>
              <PlinkoGame
                walletBalance={walletBalance}
                onBalanceChange={setWalletBalance}
                isActive={tab === "plinko"}
              />
            </Suspense>
          </div>
        )}

        {mountedGames.lotto && (
          <div
            className={
              tab === "lotto"
                ? "flex min-h-0 flex-1 flex-col overflow-hidden"
                : "hidden"
            }
          >
            <Suspense fallback={<GameChunkFallback />}>
              <LottoSpinGame
                accessToken={accessToken}
                userId={userId}
                firstName={firstName}
                walletBalance={walletBalance}
                onBalanceChange={setWalletBalance}
                isActive={tab === "lotto"}
              />
            </Suspense>
          </div>
        )}

        {tab === "profile" && (
          <div className="flex-1 overflow-y-auto">
            <ProfileHub
              firstName={firstName}
              balance={walletBalance}
              boardPrice={roomState.board_price}
            />
          </div>
        )}

        {tab === "admin" && isAdmin && (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <Suspense fallback={<GameChunkFallback />}>
              <AdminDashboard onAccessDenied={handleAdminAccessDenied} />
            </Suspense>
          </div>
        )}
      </div>

      <BottomNav active={tab} onChange={setTab} bingoLive={inGame} isAdmin={isAdmin} />

      {onBingoTab && showWinnerDialog && gameOver && (
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

      {onBingoTab && toast && (
        <div className="fixed bottom-28 left-1/2 z-40 w-[88%] max-w-sm -translate-x-1/2 rounded-2xl bg-[#4C1D95] px-5 py-3 text-center text-sm font-semibold text-white shadow-2xl">
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
