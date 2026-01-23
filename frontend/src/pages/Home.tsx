import { useEffect, useState } from "react";
import useWebSocket from "react-use-websocket";
import PhoneContainer from "../components/PhoneContainer";
import BingoBoard from "../components/BingoBoard";
import CalledNumbersPanel from "../components/CalledNumbersPanel";
import PlayBoard from "../components/PlayBoard";
import NumberCaller from "../components/NumberCaller";
import { Volume2, VolumeX } from "lucide-react";
import { getBingoWsUrl } from "../config/api";

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
  winner_id?: string;
  winning_number?: number;
  winning_cells?: [number, number][];
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

const DashboardHeader = ({
  gameNo,
  derash,
  players,
  called,
  muted,
  toggleMute,
}: {
  gameNo: string;
  derash: number;
  players: number;
  called: number;
  muted: boolean;
  toggleMute: () => void;
}) => (
  <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2">
    <HeaderStat label="Game No" value={gameNo} />
    <HeaderStat label="Derash" value={derash} />
    <HeaderStat label="Player" value={players} />
    <HeaderStat label="Called" value={called} />
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
  /* -------------------- STAKE -------------------- */
  const [stake, setStake] = useState<number | null>(null);
  const [wsReady, setWsReady] = useState(false);

  /* -------------------- GAME STATES -------------------- */
  const [reservationActive, setReservationActive] = useState(true);
  const [secondsLeft, setSecondsLeft] = useState(60);
  const [reservedNumbers, setReservedNumbers] = useState<number[]>([]);
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null);
  const [playboard, setPlayboard] = useState<number[]>([]);
  const [calledNumbers, setCalledNumbers] = useState<number[]>([]);
  const [lastNumber, setLastNumber] = useState<number | undefined>();
  const [winnerId, setWinnerId] = useState<string | null>(null);
  const [winningNumber, setWinningNumber] = useState<number | null>(null);
  const [winningCells, setWinningCells] = useState<[number, number][]>([]);
  const [wsId, setWsId] = useState<string | null>(null);
  const [_winner, setWinner] = useState(false);
  const [markedNumbers, setMarkedNumbers] = useState<number[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [autoClick, setAutoClick] = useState(false);
  const [_gameStarted, setGameStarted] = useState(false);

  /* -------------------- HEADER -------------------- */
  const [gameNo, setGameNo] = useState("000001");
  const [players, setPlayers] = useState(0);
  const [derash, setDerash] = useState(0);
  const [muted, setMuted] = useState(false);

  const token = localStorage.getItem("token");

  /* -------------------- LOAD STAKE -------------------- */
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlStake = params.get("stake");

    // Get current localStorage stake and selected number
    const savedStake = localStorage.getItem("bingo_stake");
    const savedNumber = localStorage.getItem("bingo_selected_number");

    // Case 1: user already in a game (reserved number) -> always use savedStake
    if (savedNumber) {
      setStake(savedStake ? Number(savedStake) : null);
      return;
    }

    // Case 2: no active game -> use URL stake if valid
    if (urlStake && AVAILABLE_STAKES.includes(Number(urlStake))) {
      const s = Number(urlStake);
      setStake(s);
      localStorage.setItem("bingo_stake", String(s));
      return;
    }

    // Case 3: fallback to savedStake if URL is not valid
    if (savedStake && AVAILABLE_STAKES.includes(Number(savedStake))) {
      setStake(Number(savedStake));
    }
  }, []);

  /* -------------------- WS -------------------- */
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

  /* -------------------- WS HANDLER -------------------- */
  useEffect(() => {
    if (!lastJsonMessage) return;
    const msg = lastJsonMessage as WSMessage;

    if (msg.game_no) setGameNo(msg.game_no);
    if (typeof msg.players === "number") setPlayers(msg.players);
    if (typeof msg.derash === "number") setDerash(msg.derash);

    switch (msg.type) {
      case "init":
        setReservationActive(msg.reservation_active ?? true);
        setSecondsLeft(msg.seconds_left ?? 60);
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
        setSecondsLeft(msg.seconds_left ?? 60);
        setReservedNumbers(msg.reserved_numbers ?? []);
        break;

      case "reservation_end":
        setReservationActive(false);
        setSecondsLeft(3);
        setGameStarted(true);
        break;

      case "number_reserved":
        setReservedNumbers(msg.reserved_numbers ?? []);
        if (msg.user_id === wsId) {
          if (msg.selected_number == null) {
            setSelectedNumber(null);
            setPlayboard([]);
            setMarkedNumbers([]);
            setWinner(false);
          } else {
            setSelectedNumber(msg.selected_number);
            setPlayboard(msg.playboard ?? []);
            setMarkedNumbers(msg.marked_numbers ?? []);
          }
        }
        break;

      case "number_called":
        setCalledNumbers(msg.called_numbers ?? []);
        setLastNumber(msg.number);
        setSecondsLeft(3);
        break;

      case "winner":
        setWinnerId(msg.winner_id ?? null);
        setWinningNumber(msg.winning_number ?? null);
        setWinningCells(msg.winning_cells ?? []);
        if (msg.winner_id === wsId) setWinner(true);
        break;

      case "marked_numbers":
        setMarkedNumbers(msg.marked_numbers ?? []);
        break;

      case "no_players":
      case "new_round":
        setReservationActive(true);
        setSecondsLeft(60);
        setReservedNumbers([]);
        setSelectedNumber(null);
        setPlayboard([]);
        setCalledNumbers([]);
        setLastNumber(undefined);
        setWinnerId(null);
        setWinningNumber(null);
        setWinningCells([]);
        setWinner(false);
        setMarkedNumbers([]);
        setGameStarted(false);
        break;

      case "error":
        setErrorMessage(msg.message ?? "An error occurred");
        setTimeout(() => setErrorMessage(null), 3000);
        break;
    }
  }, [lastJsonMessage, wsId]);

  /* -------------------- LOCAL COUNTDOWN -------------------- */
  useEffect(() => {
    if (reservationActive) return;
    const interval = setInterval(
      () => setSecondsLeft((s) => (s > 0 ? s - 1 : 0)),
      1000,
    );
    return () => clearInterval(interval);
  }, [reservationActive, lastNumber]);

  /* -------------------- SELECT NUMBER -------------------- */
  const handleSelectNumber = (num: number) => {
    if (!reservationActive || !token) return;
    if (selectedNumber !== num) setSelectedNumber(num);
    sendJsonMessage({ type: "select_number", number: num });
  };

  /* -------------------- RENDER -------------------- */
  if (!stake) {
    return (
      <PhoneContainer>
        <div className="p-3 h-full flex flex-col items-center justify-center text-white">
          <h1 className="text-lg font-bold mb-4">Select a Stake to Start</h1>
          {AVAILABLE_STAKES.map((s) => (
            <button
              key={s}
              className="px-4 py-2 m-1 bg-emerald-500 rounded font-bold"
              onClick={() => {
                setStake(s);
                localStorage.setItem("bingo_stake", String(s));
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </PhoneContainer>
    );
  }

  return (
    <PhoneContainer>
      <div className="p-3 space-y-4 h-full overflow-y-auto">
        {!wsReady && (
          <p className="text-center text-white mt-10">
            Connecting to game server...
          </p>
        )}

        {/* Header */}
        <DashboardHeader
          gameNo={gameNo}
          derash={derash}
          players={players}
          called={calledNumbers.length}
          muted={muted}
          toggleMute={() => setMuted((m) => !m)}
        />

        {/* Title */}
        <h1 className="text-center text-lg font-bold text-emerald-400">
          {reservationActive
            ? "Select Your Number"
            : playboard.length > 0
              ? "BINGO DRAW"
              : "Game is already started"}
        </h1>

        {/* Bingo & Called Numbers */}
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

        {/* Playboard */}
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
                Auto-Click Numbers
              </label>
            </div>
            <PlayBoard
              playboard={playboard}
              calledNumbers={calledNumbers}
              winningCells={winningCells}
              wsId={wsId}
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

        {/* Winner Modal */}
        {winnerId && (
          <div className="fixed inset-0 flex items-center justify-center z-50 pointer-events-none">
            <div className="bg-black bg-opacity-70 px-6 py-4 rounded-xl text-center pointer-events-auto">
              <p className="text-yellow-400 font-extrabold text-2xl">
                🎉 Bingo Winner: Number {winningNumber}
                {winnerId === wsId && " (YOU)"}
              </p>
            </div>
          </div>
        )}

        {/* Footer countdown */}
        <p className="text-center text-sm text-gray-400">
          {reservationActive
            ? `Select your number (${secondsLeft}s left)`
            : `Next call in ${secondsLeft}s`}
        </p>
      </div>

      {/* Error toast */}
      {errorMessage && (
        <div className="fixed inset-0 flex items-center justify-center z-50 pointer-events-none">
          <div className="bg-red-600 bg-opacity-90 text-white px-6 py-4 rounded-xl text-center shadow-lg pointer-events-auto animate-fade-in">
            <p className="font-bold text-lg">⚠️ {errorMessage}</p>
          </div>
        </div>
      )}
    </PhoneContainer>
  );
};

export default DashboardHome;
