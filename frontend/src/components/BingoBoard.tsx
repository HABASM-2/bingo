import { useState } from "react";

type Props = {
  calledNumbers: number[];
  lastNumber?: number;
  reservationActive?: boolean;
  selectedNumber?: number | null;
  onSelectNumber?: (num: number) => void;
  reservedNumbers?: number[];
};

const groups = [
  { label: "B", start: 1, end: 15, bgColor: "bg-red-300" },
  { label: "I", start: 16, end: 30, bgColor: "bg-green-300" },
  { label: "N", start: 31, end: 45, bgColor: "bg-blue-300" },
  { label: "G", start: 46, end: 60, bgColor: "bg-yellow-300" },
  { label: "O", start: 61, end: 75, bgColor: "bg-purple-300" },
];

const BingoBoard = ({
  calledNumbers,
  lastNumber,
  reservationActive = false,
  selectedNumber,
  onSelectNumber,
  reservedNumbers = [],
}: Props) => {
  const [error, setError] = useState<string | null>(null);

  const handleClick = (num: number) => {
    if (!reservationActive || !onSelectNumber) return;

    try {
      setError(null);
      onSelectNumber(num);
    } catch (err: any) {
      setError(err.message || "Unable to reserve number");
    }
  };

  return (
    <div className="inline-block p-2 rounded-xl bg-[#0f172a] shadow-lg max-w-full overflow-x-auto">
      {error && (
        <div className="text-red-500 font-bold text-center text-xs mb-1">
          {error}
        </div>
      )}

      {/* Header row */}
      <div className="grid grid-cols-5 gap-[1px] mb-1">
        {groups.map((group) => (
          <div
            key={group.label}
            className={`${group.bgColor} text-black flex-1 min-w-[20px] h-5 flex items-center justify-center font-bold rounded-md text-[10px]`}
          >
            {group.label}
          </div>
        ))}
      </div>

      {/* Numbers grid */}
      <div className="grid grid-cols-5 gap-[1px]">
        {groups.map((group) => (
          <div key={group.label} className="flex flex-col gap-[1px]">
            {Array.from(
              { length: group.end - group.start + 1 },
              (_, i) => group.start + i
            ).map((num) => {
              const isCalled = calledNumbers.includes(num);
              const isSelected = selectedNumber === num;
              const isReserved = reservedNumbers.includes(num);

              // Determine background and text color
              let bgClass = "bg-gray-50";
              let textClass = "text-black";
              let shadowClass = "";

              if (isCalled) {
                bgClass = "bg-emerald-500";
                textClass = "text-white font-bold";
              } else if (isSelected || isReserved) {
                bgClass = "bg-yellow-400";
                shadowClass = "shadow-[0_0_3px_#facc15]";
                textClass = "text-black font-bold";
              }

              return (
                <button
                  key={num}
                  onClick={() => handleClick(num)}
                  disabled={!reservationActive && !isCalled}
                  className={`flex-1 min-w-[18px] h-4 sm:h-5 text-[9px] sm:text-[10px] font-bold flex items-center justify-center rounded-md
                      ${bgClass} ${textClass} ${shadowClass} transition`}
                >
                  {num}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};

export default BingoBoard;
