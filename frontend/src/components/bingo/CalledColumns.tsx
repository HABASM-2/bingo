import { BINGO_COLUMN_LETTERS } from "../../utils/cartela";
import { COLUMN_COLORS } from "./colors";

interface CalledColumnsProps {
  drawn: number[];
  currentBall: number | null;
}

/**
 * The 1-75 call board on the left of the active game.
 */
export function CalledColumns({ drawn, currentBall }: CalledColumnsProps) {
  const drawnSet = new Set(drawn);
  const rows = Array.from({ length: 15 }, (_, r) => r);

  return (
    <div className="rounded-2xl bg-white/90 p-1.5 shadow-sm ring-1 ring-purple-100 dark:bg-[#1E1B2E] dark:ring-white/10">
      <div className="grid grid-cols-5 gap-0.5">
        {BINGO_COLUMN_LETTERS.map((letter) => {
          const color = COLUMN_COLORS[letter];
          return (
            <div
              key={letter}
              className="flex h-6 items-center justify-center rounded-md text-[11px] font-extrabold"
              style={{ backgroundColor: color.bg, color: color.text }}
            >
              {letter}
            </div>
          );
        })}
      </div>

      <div className="mt-1 grid grid-cols-5 gap-0.5">
        {rows.map((r) =>
          BINGO_COLUMN_LETTERS.map((_letter, c) => {
            const value = c * 15 + r + 1;
            const isCurrent = value === currentBall;
            const isCalled = drawnSet.has(value) && !isCurrent;

            return (
              <div
                key={value}
                className={`flex h-6 items-center justify-center rounded-md text-[11px] font-semibold transition-colors duration-200 ${
                  isCurrent
                    ? "bg-green-500 text-white shadow"
                    : isCalled
                      ? "bg-orange-400 text-white"
                      : "text-gray-700 dark:text-gray-300"
                }`}
              >
                {value}
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}
