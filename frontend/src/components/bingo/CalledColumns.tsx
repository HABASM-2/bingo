import { useEffect, useState } from "react";
import { BINGO_COLUMN_LETTERS } from "../../utils/cartela";
import { COLUMN_COLORS } from "./colors";

interface CalledColumnsProps {
  drawn: number[];
  currentBall: number | null;
}

/**
 * The 1-75 call board on the left of the active game.
 * Height is content-sized (flex-none) — never stretch to fill the viewport.
 */
export function CalledColumns({ drawn, currentBall }: CalledColumnsProps) {
  const drawnSet = new Set(drawn);
  const rows = Array.from({ length: 15 }, (_, r) => r);
  const [bounceBall, setBounceBall] = useState<number | null>(null);

  useEffect(() => {
    if (currentBall == null) {
      setBounceBall(null);
      return;
    }
    setBounceBall(currentBall);
    const id = window.setTimeout(() => setBounceBall(null), 650);
    return () => window.clearTimeout(id);
  }, [currentBall]);

  return (
    <div className="h-fit w-full flex-none self-start rounded-2xl bg-white/95 p-1.5 shadow-sm ring-1 ring-purple-200/80 dark:bg-[#1E1B2E] dark:ring-white/15">
      <div className="grid grid-cols-5 gap-0.5">
        {BINGO_COLUMN_LETTERS.map((letter) => {
          const color = COLUMN_COLORS[letter];
          return (
            <div
              key={letter}
              className="flex h-6 items-center justify-center rounded-md border border-black/10 text-[11px] font-extrabold dark:border-white/15"
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
            const shouldBounce = bounceBall === value;

            return (
              <div
                key={value}
                className={`flex h-6 items-center justify-center rounded-md border text-[11px] font-semibold transition-colors duration-200 ${
                  isCurrent
                    ? "border-green-600/50 bg-green-500 text-white shadow-sm"
                    : isCalled
                      ? "border-orange-500/40 bg-orange-400 text-white"
                      : "border-stone-300/90 bg-stone-50 text-stone-700 dark:border-white/20 dark:bg-white/[0.06] dark:text-stone-200"
                } ${
                  shouldBounce
                    ? "animate-[calledBounce_0.55s_cubic-bezier(0.22,1.45,0.36,1)] motion-reduce:animate-none"
                    : isCurrent
                      ? "animate-[calledPulse_1.4s_ease-in-out_infinite] motion-reduce:animate-none"
                      : ""
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
