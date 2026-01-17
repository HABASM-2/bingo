type Props = {
  playboard: number[];
  calledNumbers: number[];
  winningCells: [number, number][];
  wsId: string | null;
  sendJsonMessage: (msg: any) => void;
  markedNumbers: number[];
  setMarkedNumbers: (nums: number[]) => void;
  onError: (msg: string) => void; // ✅ new
};

const PlayBoard = ({
  playboard,
  calledNumbers,
  winningCells,
  wsId,
  sendJsonMessage,
  markedNumbers,
  setMarkedNumbers,
  onError,
}: Props) => {
  const labels = ["B", "I", "N", "G", "O"];
  const safeWinningCells = winningCells ?? [];

  const labelColors: Record<string, string> = {
    B: "bg-red-400 text-white",
    I: "bg-blue-400 text-white",
    N: "bg-yellow-400 text-black",
    G: "bg-green-400 text-white",
    O: "bg-purple-400 text-white",
  };

  const handleClick = (num: number) => {
    if (num === 0) return; // FREE
    if (!calledNumbers.length) return;

    const lastCalled = calledNumbers[calledNumbers.length - 1];

    // ❌ Wrong click
    if (
      num !== lastCalled ||
      markedNumbers.includes(num) ||
      !playboard.includes(num)
    ) {
      onError("❌ Wrong number! You are out of the game."); // tell Home to show toast
      sendJsonMessage({ type: "mark_number", number: num }); // backend handles disqualification
      return;
    }

    // ✅ Valid click
    sendJsonMessage({ type: "mark_number", number: num });
  };

  return (
    <div className="mt-2 space-y-1 w-1/2 mx-auto">
      <h2 className="text-center font-bold text-green-600 text-sm">
        Your Bingo Card
      </h2>

      {/* Column Labels */}
      <div className="grid grid-cols-5 gap-[2px]">
        {labels.map((l) => (
          <div
            key={l}
            className={`h-6 flex items-center justify-center text-xs font-bold rounded ${labelColors[l]}`}
          >
            {l}
          </div>
        ))}
      </div>

      {/* Bingo Cells */}
      <div className="grid grid-cols-5 gap-[2px]">
        {playboard.map((num, idx) => {
          const row = Math.floor(idx / 5);
          const col = idx % 5;

          const isFree = num === 0;
          const isWinning = safeWinningCells.some(
            ([r, c]) => r === row && c === col
          );
          const isMarked = markedNumbers.includes(num);

          const lastCalled = calledNumbers[calledNumbers.length - 1];

          let bgClass = "bg-gray-100 text-gray-800"; // default off-white

          if (isWinning) bgClass = "bg-green-600 text-white animate-pulse";
          else if (isFree) bgClass = "bg-green-300 text-white";
          else if (isMarked) bgClass = "bg-green-500 text-white";
          else if (num === lastCalled)
            bgClass = "bg-yellow-300 text-black animate-pulse";

          return (
            <div
              key={idx}
              onClick={() => handleClick(num)}
              className={`h-8 flex items-center justify-center text-xs font-bold cursor-pointer transition ${bgClass} rounded`}
            >
              {isFree ? "FREE" : num}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PlayBoard;
