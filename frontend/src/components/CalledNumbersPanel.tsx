const getLetter = (num: number) => {
  if (num <= 15) return "B";
  if (num <= 30) return "I";
  if (num <= 45) return "N";
  if (num <= 60) return "G";
  return "O";
};

type Props = {
  calledNumbers: number[];
  lastNumber?: number;
};

const CalledNumbersPanel = ({ calledNumbers, lastNumber }: Props) => {
  const lastFive = [...calledNumbers].slice(-5).reverse();

  // Arrange in grid: 2 + 2 + 1
  const rows: number[][] = [
    lastFive.slice(0, 2),
    lastFive.slice(2, 4),
    lastFive.slice(4, 5),
  ];

  return (
    <div className="rounded-2xl bg-zinc-900 border border-zinc-800 p-3 space-y-2">
      <h3 className="text-center text-sm font-semibold text-emerald-400">
        Last Calls
      </h3>

      <div className="space-y-1">
        {rows.map((row, rowIndex) => (
          <div
            key={rowIndex}
            className={`flex justify-center gap-2 ${
              row.length === 1 ? "justify-center" : ""
            }`}
          >
            {row.map((num) => (
              <div
                key={num}
                className={`
                  flex items-center justify-center gap-2 rounded-lg py-1 px-2 text-sm
                  ${
                    num === lastNumber
                      ? "bg-yellow-400 text-black font-bold"
                      : "bg-zinc-800 text-zinc-300"
                  }
                `}
              >
                <span className="font-semibold">{getLetter(num)}</span>
                <span>{num}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};

export default CalledNumbersPanel;
