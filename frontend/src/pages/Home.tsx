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
  const [winnerId, setWinnerId] = useState<string | null>(null);
  const [winningNumber, setWinningNumber] = useState<number | null>(null);
  const [winningCells, setWinningCells] = useState<[number, number][]>([]);
  const [wsId, setWsId] = useState<string | null>(null);
  const [_winner, setWinner] = useState(false);
  const [markedNumbers, setMarkedNumbers] = useState<number[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [autoClick, setAutoClick] = useState(false);
  const [_gameStarted, setGameStarted] = useState(false);

  const [gameNo, setGameNo] = useState("000001");
  const [players, setPlayers] = useState(0);
  const [derash, setDerash] = useState(0);
  const [muted, setMuted] = useState(false);

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
    const interval = setInterval(() => {
      fetch("/bingo/status")
        .then((res) => res.json())
        .then((data) => setStakesStatus(data));
    }, 3000);
    return () => clearInterval(interval);
  }, []);

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
        localStorage.removeItem("bingo_selected_number");
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
    // Show lobby only if no stake
    return (
      <PhoneContainer>
        <div className="p-4 text-white">
          <h1 className="text-xl font-bold text-center mb-4">
            🎯 Select Stake
          </h1>
          <table className="w-full text-center border border-zinc-700 rounded-lg overflow-hidden">
            <thead className="bg-zinc-800 text-sm">
              <tr>
                <th className="p-2">Stake</th>
                <th className="p-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {AVAILABLE_STAKES.map((s) => {
                const status = stakesStatus?.[s];
                return (
                  <tr key={s} className="border-t border-zinc-700">
                    <td className="p-3 font-bold text-emerald-400">{s} Birr</td>
                    <td>
                      {status ? (
                        <div className="flex flex-col gap-1 text-xs text-white">
                          <span>
                            Status:{" "}
                            {status.reservation_active
                              ? "Countdown"
                              : "Playing"}
                          </span>
                          <span>Players: {status.players}</span>
                          <span>Derash: {status.derash} Birr</span>
                          <span>Game #: {status.game_no}</span>
                        </div>
                      ) : (
                        <span className="text-gray-400">Loading...</span>
                      )}
                    </td>
                    <td>
                      <button
                        className="bg-emerald-500 px-4 py-1 rounded font-bold hover:bg-emerald-600"
                        onClick={() => joinStake(s)}
                      >
                        Join
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </PhoneContainer>
    );
  }

  // Game view
  return (
    <PhoneContainer>
      <div className="p-3 space-y-4 h-full overflow-y-auto">
        {!wsReady && (
          <p className="text-center text-white mt-10">
            Connecting to game server...
          </p>
        )}

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
