import { useEffect, useState } from "react";
import useWebSocket from "react-use-websocket";
import PhoneContainer from "../components/PhoneContainer";
import BingoBoard from "../components/BingoBoard";
import CalledNumbersPanel from "../components/CalledNumbersPanel";
import PlayBoard from "../components/PlayBoard";
import NumberCaller from "../components/NumberCaller";
import { Volume2, VolumeX } from "lucide-react";
import { getBingoWsUrl } from "../config/api";

/* -------------------- WS MESSAGE TYPE -------------------- */
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
  balance?: number[];

  message?: string;

  game_no?: string;
  players?: number;
  derash?: number;
};

/* -------------------- HEADER -------------------- */
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

/* -------------------- MAIN -------------------- */
const DashboardHome = () => {
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
  const [winner, setWinner] = useState(false);
  const [userBalance, setUserBalance] = useState<number>(0);
  const [markedNumbers, setMarkedNumbers] = useState<number[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  /* -------------------- HEADER STATE -------------------- */
  const [gameNo, setGameNo] = useState("000001");
  const [players, setPlayers] = useState(0);
  const [derash, setDerash] = useState(0);
  const [muted, setMuted] = useState(false);

  /* -------------------- TOKEN -------------------- */
  const token = localStorage.getItem("token");

  /* -------------------- WEBSOCKET -------------------- */
  const { sendJsonMessage, lastJsonMessage } = useWebSocket(
    getBingoWsUrl(token ?? undefined), // convert null → undefined
    {
      shouldReconnect: () => true,
      reconnectAttempts: Infinity,
      reconnectInterval: 3000,
    }
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
        setReservedNumbers(msg.reserved_numbers ?? []);
        if (!wsId) setWsId(msg.user_id ?? null);
        if (msg.user_id === wsId && msg.selected_number) {
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
        setSecondsLeft(3); // start countdown for number calling
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
        setSecondsLeft(3); // reset countdown for next call
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
        setReservationActive(true);
        setSecondsLeft(60);
        setReservedNumbers([]);
        setSelectedNumber(null);
        setPlayboard([]);
        setMarkedNumbers([]);
        setCalledNumbers([]);
        setWinner(false);
        setLastNumber(undefined);
        break;

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
        break;

      case "error":
        setErrorMessage(msg.message ?? "An error occurred");
        // Clear automatically after 3 seconds
        setTimeout(() => setErrorMessage(null), 3000);
        break;
    }
  }, [lastJsonMessage, wsId]);

  /* -------------------- LOCAL COUNTDOWN FOR NUMBER CALLING -------------------- */
  useEffect(() => {
    if (reservationActive) return; // backend handles countdown for reservation

    const interval = setInterval(() => {
      setSecondsLeft((s) => (s > 0 ? s - 1 : 0));
    }, 1000);

    return () => clearInterval(interval);
  }, [reservationActive, lastNumber]);

  /* -------------------- ACTIONS -------------------- */
  const handleSelectNumber = (num: number) => {
    if (!reservationActive) return;
    if (!token) return;

    // Optimistic UI update
    if (selectedNumber !== num) {
      // generate empty playboard placeholder or show loading
      setSelectedNumber(num);
      setPlayboard([]);
      setMarkedNumbers([]);
    }

    sendJsonMessage({ type: "select_number", number: num });
  };

  /* -------------------- RENDER -------------------- */
  return (
    <PhoneContainer>
      <div className="p-3 space-y-4 h-full overflow-y-auto">
        {/* HEADER */}
        <DashboardHeader
          gameNo={gameNo}
          derash={derash}
          players={players}
          called={calledNumbers.length}
          muted={muted}
          toggleMute={() => setMuted((m) => !m)}
        />

        <h1 className="text-center text-lg font-bold text-emerald-400">
          {reservationActive
            ? "Select Your Number"
            : playboard.length > 0
            ? "BINGO DRAW"
            : "Game is already started"}
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
          <PlayBoard
            playboard={playboard}
            calledNumbers={calledNumbers}
            winningCells={winningCells}
            wsId={wsId}
            sendJsonMessage={sendJsonMessage}
            markedNumbers={markedNumbers}
            setMarkedNumbers={setMarkedNumbers}
          />
        )}

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

        <p className="text-center text-sm text-gray-400">
          {reservationActive
            ? `Select your number (${secondsLeft}s left)`
            : `Next call in ${secondsLeft}s`}
        </p>
      </div>
      {/* Error Toast */}
      {/* Centered Error Message */}
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
