import { useEffect, useState } from "react";
import React from "react";
import useWebSocket from "react-use-websocket";
import PhoneContainer from "../components/PhoneContainer";
import BingoBoard from "../components/BingoBoard";
import CalledNumbersPanel from "../components/CalledNumbersPanel";
import PlayBoard from "../components/PlayBoard";
import NumberCaller from "../components/NumberCaller";
import { Volume2, VolumeX } from "lucide-react";
import { getBingoWsUrl } from "../config/api";
import { useLang } from "../useLang";
import { t } from "../i18n";

const AVAILABLE_STAKES = [10, 20, 50];

type WSMessage = {
  type: string;
  seconds_left?: number;
  reservation_active?: boolean;
  reserved_numbers?: number[];
  user_id?: string;
  selected_number?: number;
  playboard?: number[];
  number?: number;
  called_numbers?: number[];

  // ✅ MULTI WINNER
  winner_ids?: string[];
  winning_number?: number;
  winning_cells?: [number, number][][]; // cells per winner

  marked_numbers?: number[];
  message?: string;
  game_no?: string;
  players?: number;
  derash?: number;
};

const HeaderStat = ({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) => (
  <div className="flex flex-col items-center flex-1">
    <span className="text-[10px] text-zinc-400 uppercase">{label}</span>
    <span className="text-sm font-bold text-white">{value}</span>
  </div>
);

// Helper to render floating bingo balls
const BingoBall = ({ number }: { number: number }) => (
  <div
    className="absolute rounded-full w-6 h-6 bg-emerald-400 text-black flex items-center justify-center font-bold animate-bounce"
    style={{
      left: `${Math.random() * 90}%`,
      top: `${Math.random() * 90}%`,
      animationDuration: `${2 + Math.random() * 2}s`,
    }}
  >
    {number}
  </div>
);

const DashboardHeader = ({
  L,
  gameNo,
  derash,
  players,
  called,
  muted,
  toggleMute,
}: {
  L: any;
  gameNo: string;
  derash: number;
  players: number;
  called: number;
  muted: boolean;
  toggleMute: () => void;
}) => (
  <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2">
    <HeaderStat label={L.gameNo} value={gameNo} />
    <HeaderStat label={L.derash} value={derash} />
    <HeaderStat label={L.players} value={players} />
    <HeaderStat label={L.called} value={called} />
    <button
      onClick={toggleMute}
      className="h-9 w-9 flex items-center justify-center rounded-full bg-zinc-800 hover:bg-zinc-700 transition"
    >
      {muted ? (
        <VolumeX size={18} className="text-red-400" />
      ) : (
        <Volume2 size={18} className="text-emerald-400" />
      )}
    </button>
  </div>
);

const DashboardHome = () => {
  // ------------------ Initialize stake from URL ------------------
  const urlParams = new URLSearchParams(window.location.search);
  const initialUrlStake = Number(urlParams.get("stake"));
  const initialStake = AVAILABLE_STAKES.includes(initialUrlStake)
    ? initialUrlStake
    : null;

  const [stake, setStake] = useState<number | null>(initialStake);
  const [wsReady, setWsReady] = useState(false);
  const [reservationActive, setReservationActive] = useState(true);
  const [secondsLeft, setSecondsLeft] = useState(60);
  const [reservedNumbers, setReservedNumbers] = useState<number[]>([]);
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null);
  const [playboard, setPlayboard] = useState<number[]>([]);
  const [calledNumbers, setCalledNumbers] = useState<number[]>([]);
  const [lastNumber, setLastNumber] = useState<number | undefined>();
  const [winnerIds, setWinnerIds] = useState<string[]>([]);
  const [winningCells, setWinningCells] = useState<[number, number][]>([]);
  const [winningNumber, setWinningNumber] = useState<number | null>(null);
  const [wsId, setWsId] = useState<string | null>(null);
  const [_winner, setWinner] = useState(false);
  const [markedNumbers, setMarkedNumbers] = useState<number[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [autoClick, setAutoClick] = useState(false);
  const [_gameStarted, setGameStarted] = useState(false);

  const [gameNo, setGameNo] = useState("000001");
  const [players, setPlayers] = useState(0);
  const [derash, setDerash] = useState(0);
  const [muted, setMuted] = useState(true);

  const audioUnlockedRef = React.useRef(false);

  const [announcement, setAnnouncement] = useState<string | null>(null);
  const [announcementType, setAnnouncementType] = useState<
    "info" | "error" | "success"
  >("info");

  const [stakesCountdown, setStakesCountdown] = useState<
    Record<number, number>
  >({});

  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  const { lang, setLang } = useLang();
  const L = t(lang);

  const playNumberAudio = (num: number) => {
    if (muted || !audioUnlockedRef.current) return;

    const audio = new Audio(`/web/audio/${num}.mp3`);
    audioRef.current = audio;
    audio.volume = 1;

    audio.play().catch(() => {});
  };

  const playBingoSound = () => {
    if (!audioUnlockedRef.current) return; // only if user has unlocked audio
    const audio = new Audio("/web/audio/bingo.mp3");
    audio.volume = 1;
    audio.play().catch(() => {}); // ignore play errors
  };

  const [stakesStatus, setStakesStatus] = useState<Record<
    number,
    {
      reservation_active: boolean;
      seconds_left: number;
      players: number;
      derash: number;
      game_no: number;
    }
  > | null>(null);

  const token = localStorage.getItem("token");

  useEffect(() => {
    let interval: number;

    const fetchStakesStatus = async () => {
      try {
        const res = await fetch("/bingo/status");
        const data: Record<
          number,
          {
            reservation_active: boolean;
            seconds_left: number;
            players: number;
            derash: number;
            game_no: number;
          }
        > = await res.json();

        // Update both stakesStatus and initialize stakesCountdown if missing
        setStakesStatus(data);

        setStakesCountdown((prev) => {
          const next: Record<number, number> = { ...prev };
          for (const stakeStr in data) {
            const stake = Number(stakeStr);
            if (!(stake in prev) || data[stake].reservation_active) {
              next[stake] = data[stake].seconds_left;
            }
          }
          return next;
        });
      } catch (err) {
        console.error("Failed to fetch /bingo/status", err);
      }
    };

    fetchStakesStatus();

    // Start interval to count down per-stake every second
    interval = window.setInterval(() => {
      setStakesCountdown((prev) => {
        const next: Record<number, number> = { ...prev };
        for (const stake in next) {
          // Only decrement if reservation is active
          if (stakesStatus?.[stake]?.reservation_active && next[stake] > 0) {
            next[stake] = next[stake] - 1;
          }
        }
        return next;
      });
    }, 1000);

    // Refresh status from backend every 3 seconds
    const refreshInterval = window.setInterval(fetchStakesStatus, 3000);

    return () => {
      clearInterval(interval);
      clearInterval(refreshInterval);
    };
  }, [stakesStatus]);

  // ------------------ Update stake if URL changes ------------------
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlStake = Number(params.get("stake"));

    if (AVAILABLE_STAKES.includes(urlStake) && urlStake !== stake) {
      setStake(urlStake);
      localStorage.setItem("bingo_stake", String(urlStake));
    } else if (!urlStake && !reservationActive) {
      setStake(null);
      localStorage.removeItem("bingo_stake");
      localStorage.removeItem("bingo_selected_number");
    }
  }, [reservationActive]);

  // ------------------ WebSocket ------------------
  const { sendJsonMessage, lastJsonMessage } = useWebSocket(
    stake ? getBingoWsUrl(token ?? undefined, stake) : null,
    {
      shouldReconnect: () => true,
      reconnectAttempts: Infinity,
      reconnectInterval: 3000,
      onOpen: () => setWsReady(true),
      onClose: () => setWsReady(false),
    },
  );

  // ------------------ WS Handler ------------------
  useEffect(() => {
    if (!lastJsonMessage) return;
    const msg = lastJsonMessage as WSMessage;

    if (msg.game_no) setGameNo(msg.game_no);
    if (typeof msg.players === "number") setPlayers(msg.players);
    if (typeof msg.derash === "number") setDerash(msg.derash);

    // Clear any existing countdown
    let countdownInterval: number;

    const startCountdown = (seconds: number) => {
      setSecondsLeft(seconds);
      clearInterval(countdownInterval);
      countdownInterval = window.setInterval(() => {
        setSecondsLeft((prev) => {
          if (prev <= 1) {
            clearInterval(countdownInterval);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    };

    // Helper to reset user/game state
    const resetGameState = (
      announcementMsg: string,
      type: "info" | "error" | "success" = "info",
    ) => {
      setAnnouncement(announcementMsg);
      setAnnouncementType(type);
      setWinnerIds([]);
      setSelectedNumber(null);
      setPlayboard([]);
      setMarkedNumbers([]);
      setReservedNumbers([]);
      localStorage.removeItem("bingo_selected_number");

      setReservationActive(true);
      setSecondsLeft(60);
      setCalledNumbers([]);
      setLastNumber(undefined);
      setWinnerIds([]);
      setWinningNumber(null);
      setWinningCells([]);
      setWinner(false);
      setGameStarted(false);

      // Optional sound for important messages
      if (type === "error") {
        const audio = new Audio("/web/audio/alert.mp3");
        audio.volume = 0.8;
        audio.play().catch(() => {});
      }

      setTimeout(() => {
        setAnnouncement(null);
        setAnnouncementType("info");
      }, 5000);
    };

    switch (msg.type) {
      case "init":
        setReservationActive(msg.reservation_active ?? true);
        startCountdown(msg.seconds_left ?? 60);
        setGameStarted(!(msg.reservation_active ?? true));
        setReservedNumbers(msg.reserved_numbers ?? []);
        if (!wsId) setWsId(msg.user_id ?? null);

        if (msg.selected_number) {
          setSelectedNumber(msg.selected_number);
          setPlayboard(msg.playboard ?? []);
          setMarkedNumbers(msg.marked_numbers ?? []);
        }
        break;

      case "reservation":
        setReservationActive(msg.reservation_active ?? true);
        setReservedNumbers(msg.reserved_numbers ?? []);
        startCountdown(msg.seconds_left ?? 60);
        break;

      case "number_called":
        setCalledNumbers(msg.called_numbers ?? []);
        setLastNumber(msg.number);
        startCountdown(msg.seconds_left ?? 3); // Use backend CALL_INTERVAL
        if (msg.number) playNumberAudio(msg.number);
        break;

      case "reservation_end":
        setReservationActive(false);
        startCountdown(3); // short countdown before starting game
        setGameStarted(true);
        break;

      case "number_reserved":
        setReservedNumbers(msg.reserved_numbers ?? []);

        // 🔹 Restart countdown if reservation is active
        if (reservationActive) {
          setSecondsLeft((prev) => Math.max(prev, 1)); // keep the remaining seconds
        }

        if (msg.user_id === wsId) {
          if (msg.selected_number == null) {
            setSelectedNumber(null);
            setPlayboard([]);
            localStorage.removeItem("bingo_selected_number");
          } else {
            setSelectedNumber(msg.selected_number);
            setPlayboard(msg.playboard ?? []);
            localStorage.setItem(
              "bingo_selected_number",
              String(msg.selected_number),
            );
          }
        }
        break;

      case "winner_announcement":
        setAnnouncement(`🎉 ${L.playerWon}`);
        playBingoSound();
        break;

      case "winner":
        setWinningNumber(msg.winning_number ?? null);
        setWinnerIds(msg.winner_ids ?? []);

        // If YOU are one of winners, assign YOUR cells
        if (wsId && msg.winner_ids && msg.winning_cells) {
          const index = msg.winner_ids.indexOf(wsId);
          if (index !== -1) {
            setWinningCells(msg.winning_cells[index] ?? []);
          }
        }
        break;

      case "marked_numbers":
        setMarkedNumbers(msg.marked_numbers ?? []);
        break;

      case "no_players":
      case "new_round":
        resetGameState(L.newRound, "info");
        break;

      case "error":
        setErrorMessage(msg.message ?? "An error occurred");
        setTimeout(() => setErrorMessage(null), 3000);
        break;

      case "refund":
        resetGameState(L.refund, "info");
        break;

      case "round_cancelled":
        resetGameState(L.roundCancelled, "error");
        break;
    }

    return () => clearInterval(countdownInterval);
  }, [lastJsonMessage, wsId]);

  // ------------------ Local Countdown ------------------
  const joinStake = (s: number) => {
    setStake(s);
    localStorage.setItem("bingo_stake", String(s));
    window.history.replaceState({}, "", `?stake=${s}`);
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlStake = Number(params.get("stake"));

    if (AVAILABLE_STAKES.includes(urlStake)) {
      joinStake(urlStake);
    }
  }, []);

  const handleSelectNumber = (num: number) => {
    if (!reservationActive || !token) return;
    if (selectedNumber !== num) setSelectedNumber(num);
    sendJsonMessage({ type: "select_number", number: num });
  };

  // ------------------ Render ------------------
  if (!stake) {
    // Lobby view when no stake selected
    return (
      <PhoneContainer>
        {/* Floating Bingo Balls Background */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          {Array.from({ length: 15 }, (_, i) => (
            <BingoBall key={i} number={Math.floor(Math.random() * 75) + 1} />
          ))}
        </div>

        <div className="relative z-10 p-4 text-white">
          {/* Language switch */}
          <div className="flex justify-end mb-2">
            <button
              onClick={() => setLang(lang === "am" ? "en" : "am")}
              className="text-xs bg-zinc-800 px-3 py-1 rounded hover:bg-zinc-700 transition"
            >
              {lang === "am" ? "English" : "አማርኛ"}
            </button>
          </div>

          {/* Title */}
          <h1 className="text-2xl font-bold text-center mb-6 animate-pulse">
            🎯 {L.selectStake}
          </h1>

          {/* Stakes grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {AVAILABLE_STAKES.map((s) => {
              const status = stakesStatus?.[s];
              const secondsLeft = stakesCountdown[s] ?? 60;
              const totalSeconds = 60;

              const progressWidth = status?.reservation_active
                ? `${(secondsLeft / totalSeconds) * 100}%`
                : "100%";

              return (
                <div
                  key={s}
                  className={`relative bg-zinc-800 rounded-xl p-5 shadow-lg transform transition hover:scale-105 hover:shadow-2xl cursor-pointer border-2 ${
                    !status
                      ? "border-zinc-600"
                      : status.reservation_active
                        ? "border-yellow-400"
                        : "border-emerald-400"
                  }`}
                  onClick={() => joinStake(s)}
                >
                  {/* Stake and Countdown */}
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-lg font-bold text-emerald-400">
                      {s} Birr
                    </span>
                    {status ? (
                      status.reservation_active ? (
                        <span className="text-yellow-400 text-sm font-bold animate-pulse">
                          🔥 {L.countdown} {secondsLeft}s
                        </span>
                      ) : (
                        <span className="text-emerald-400 text-sm font-bold">
                          {L.playing}
                        </span>
                      )
                    ) : (
                      <span className="text-gray-400 text-sm">{L.loading}</span>
                    )}
                  </div>

                  {/* Countdown Progress Bar */}
                  {status?.reservation_active && (
                    <div className="w-full h-2 bg-zinc-700 rounded-full mb-3">
                      <div
                        className="h-2 bg-yellow-400 rounded-full transition-all"
                        style={{ width: progressWidth }}
                      />
                    </div>
                  )}

                  {/* Players Joining Indicator */}
                  <div className="flex items-center gap-1 mb-2">
                    {Array.from({ length: status?.players ?? 0 }).map(
                      (_, i) => (
                        <div
                          key={i}
                          className="w-3 h-3 rounded-full bg-blue-400 animate-bounce"
                          style={{ animationDelay: `${Math.random() * 0.5}s` }}
                        />
                      ),
                    )}
                    <span className="text-xs text-white ml-2">
                      {status?.players ?? 0} {L.players}
                    </span>
                  </div>

                  {/* Other info */}
                  {status ? (
                    <div className="flex flex-col gap-1 text-xs text-white">
                      <span>
                        {L.derash}: {status.derash} Birr
                      </span>
                      <span>
                        {L.gameNo}: {status.game_no}
                      </span>
                      <span>
                        Status:{" "}
                        {status.reservation_active ? L.waiting : L.playing}
                      </span>
                    </div>
                  ) : (
                    <span className="text-gray-400">Loading...</span>
                  )}

                  {/* Join Button */}
                  <button
                    className={`mt-4 w-full py-2 rounded font-bold transition ${
                      status?.reservation_active
                        ? "bg-yellow-400 hover:bg-yellow-500 text-black"
                        : "bg-emerald-500 hover:bg-emerald-600 text-white"
                    }`}
                  >
                    {L.join}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </PhoneContainer>
    );
  }

  // Game view
  return (
    <PhoneContainer>
      {announcement && (
        <div
          className={`fixed top-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-xl shadow-lg z-50 animate-fade-in
      ${announcementType === "info" ? "bg-yellow-400 text-black" : ""}
      ${announcementType === "error" ? "bg-red-600 text-white" : ""}
      ${announcementType === "success" ? "bg-green-500 text-white" : ""}
    `}
        >
          <p className="font-bold">{announcement}</p>
        </div>
      )}
      <div className="p-3 space-y-4 h-full overflow-y-auto">
        {!wsReady && (
          <p className="text-center text-white mt-10">{L.connecting}</p>
        )}

        <DashboardHeader
          gameNo={gameNo}
          L={L}
          derash={derash}
          players={players}
          called={calledNumbers.length}
          muted={muted}
          toggleMute={() => {
            setMuted((prev) => {
              const next = !prev;

              // First time user enables sound → unlock audio
              if (!next && !audioUnlockedRef.current) {
                const unlock = new Audio("web/audio/1.mp3");
                unlock.volume = 0;
                unlock
                  .play()
                  .then(() => {
                    unlock.pause();
                    unlock.currentTime = 0;
                    audioUnlockedRef.current = true;
                  })
                  .catch(() => {});
              }

              // If muting while sound playing → stop it
              if (next && audioRef.current) {
                audioRef.current.pause();
                audioRef.current.currentTime = 0;
              }

              return next;
            });
          }}
        />

        <h1 className="text-center text-lg font-bold text-emerald-400">
          {reservationActive
            ? L.selectNumber
            : playboard.length > 0
              ? L.bingoDraw
              : L.gameStarted}
        </h1>

        <div className="grid grid-cols-12 gap-3">
          <div className="col-span-7">
            <BingoBoard
              calledNumbers={calledNumbers}
              lastNumber={lastNumber}
              reservationActive={reservationActive}
              selectedNumber={selectedNumber}
              onSelectNumber={handleSelectNumber}
              reservedNumbers={reservedNumbers}
            />
          </div>
          <div className="col-span-5 space-y-3">
            <NumberCaller
              number={lastNumber}
              secondsLeft={secondsLeft}
              totalSeconds={reservationActive ? 60 : 3}
              gameStarting={reservationActive}
            />
            <CalledNumbersPanel
              calledNumbers={calledNumbers}
              lastNumber={lastNumber}
            />
          </div>
        </div>

        {playboard.length > 0 && (
          <>
            <div className="flex items-center gap-2 mb-2 justify-center">
              <label className="flex items-center gap-1 text-sm text-white cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={autoClick}
                  onChange={(e) => setAutoClick(e.target.checked)}
                  className="w-4 h-4 accent-emerald-400 rounded"
                />
                {L.autoClick}
              </label>
            </div>
            {playboard.length > 0 && !autoClick && (
              <div className="flex justify-center mb-2">
                <button
                  className="bg-yellow-400 px-4 py-2 rounded font-bold hover:bg-yellow-500"
                  onClick={() => {
                    sendJsonMessage({ type: "bingo_claim" });
                  }}
                >
                  🎉 Bingo!
                </button>
              </div>
            )}
            <PlayBoard
              playboard={playboard}
              calledNumbers={calledNumbers}
              winningCells={winningCells}
              wsId={wsId}
              winnerIds={winnerIds} // ✅ NEW
              sendJsonMessage={sendJsonMessage}
              markedNumbers={markedNumbers}
              setMarkedNumbers={setMarkedNumbers}
              onError={(msg) => {
                setErrorMessage(msg);
                setTimeout(() => setErrorMessage(null), 3000);
              }}
              autoClick={autoClick}
            />
          </>
        )}

        {winnerIds.length > 0 && (
          <div className="fixed inset-0 flex items-center justify-center z-50 pointer-events-none">
            <div className="bg-black bg-opacity-70 px-6 py-4 rounded-xl text-center pointer-events-auto">
              <p className="text-yellow-400 font-extrabold text-2xl">
                🎉 {L.winner}: Number {winningNumber}
                {wsId && winnerIds.includes(wsId) && ` (${L.you})`}
              </p>
            </div>
          </div>
        )}

        <p className="text-center text-sm text-gray-400">
          {reservationActive
            ? L.selectYourNumber(secondsLeft)
            : L.nextCall(secondsLeft)}
        </p>
      </div>

      {errorMessage && (
        <div className="fixed inset-0 flex items-center justify-center z-50 pointer-events-none">
          <div className="bg-red-600 bg-opacity-90 text-white px-6 py-4 rounded-xl text-center shadow-lg pointer-events-auto animate-fade-in">
            <p className="font-bold text-lg">
              ⚠️ {L.alert}: {errorMessage}
            </p>
          </div>
        </div>
      )}
    </PhoneContainer>
  );
};

export default DashboardHome;
