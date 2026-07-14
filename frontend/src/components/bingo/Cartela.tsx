import { useEffect, useMemo, useState } from "react";
import { BINGO_COLUMN_LETTERS, cartelaForBoard, patternCells } from "../../utils/cartela";
import { COLUMN_COLORS } from "./colors";

export type CartelaSize = "xs" | "sm" | "md" | "lg";

interface CartelaProps {
  boardId: number;
  drawnSet?: Set<number>;
  variant?: "preview" | "play";
  size?: CartelaSize;
  autoOn?: boolean;
  /**
   * When set (winner hold beat), cells on this pattern flash/glow so the
   * last call is clear before the winner dialog opens.
   */
  winPattern?: string | null;
}

const SIZE_STYLES: Record<
  CartelaSize,
  { pad: string; gap: string; headerH: string; headerText: string; cellText: string; freeText: string; ring: string }
> = {
  // Play footprint: compact but still readable.
  xs: {
    pad: "p-0.5",
    gap: "gap-px",
    headerH: "h-5",
    headerText: "text-[11px]",
    cellText: "text-[8px] leading-none",
    freeText: "text-[9px]",
    ring: "rounded-md",
  },
  sm: {
    pad: "p-1",
    gap: "gap-px",
    headerH: "h-[22px]",
    headerText: "text-xs",
    cellText: "text-[9px] leading-none",
    freeText: "text-[10px]",
    ring: "rounded-lg",
  },
  md: {
    pad: "p-1",
    gap: "gap-0.5",
    headerH: "h-6",
    headerText: "text-xs",
    cellText: "text-[10px] leading-none",
    freeText: "text-xs",
    ring: "rounded-xl",
  },
  lg: {
    pad: "p-1.5",
    gap: "gap-0.5",
    headerH: "h-7",
    headerText: "text-sm",
    cellText: "text-xs",
    freeText: "text-sm",
    ring: "rounded-2xl",
  },
};

function cardNumbersOnBoard(boardId: number): number[] {
  const grid = cartelaForBoard(boardId);
  const nums: number[] = [];

  for (const row of grid) {
    for (const value of row) {
      if (value != null) nums.push(value);
    }
  }

  return nums;
}

export function Cartela({
  boardId,
  drawnSet,
  variant = "play",
  size = "md",
  autoOn = true,
  winPattern = null,
}: CartelaProps) {
  const grid = useMemo(() => cartelaForBoard(boardId), [boardId]);
  const boardNums = useMemo(() => cardNumbersOnBoard(boardId), [boardId]);
  const drawn = drawnSet ?? new Set<number>();
  const isPlay = variant === "play";
  const s = SIZE_STYLES[size];
  const drawnListKey = [...drawn].sort((a, b) => a - b).join(",");

  const winCellKeys = useMemo(() => {
    const cells = patternCells(winPattern);
    return new Set(cells.map(([r, c]) => `${r}-${c}`));
  }, [winPattern]);

  const [manualMarks, setManualMarks] = useState<Set<number>>(() => new Set());

  useEffect(() => {
    if (!isPlay || !autoOn) return;

    setManualMarks(new Set(boardNums.filter((n) => drawn.has(n))));
  }, [autoOn, isPlay, boardNums, drawnListKey]);

  const markedSet = useMemo(() => {
    if (!isPlay) return new Set<number>();
    if (autoOn) return new Set(boardNums.filter((n) => drawn.has(n)));
    return manualMarks;
  }, [isPlay, autoOn, boardNums, drawn, manualMarks]);

  const handleCellClick = (value: number) => {
    if (!isPlay || autoOn) return;
    if (!drawn.has(value)) return;
    if (manualMarks.has(value)) return;

    setManualMarks((prev) => {
      const next = new Set(prev);
      next.add(value);
      return next;
    });
  };

  return (
    <div
      className={`${s.ring} ${s.pad} bg-white shadow-sm ring-1 ring-purple-100/80 transition-shadow duration-300 dark:bg-[#1E1B2E] dark:ring-white/10`}
    >
      <div className={`grid grid-cols-5 ${s.gap}`}>
        {BINGO_COLUMN_LETTERS.map((letter) => {
          const color = COLUMN_COLORS[letter];
          return (
            <div
              key={letter}
              className={`flex ${s.headerH} items-center justify-center rounded-full font-black tracking-wide ${s.headerText}`}
              style={{ backgroundColor: color.bg, color: color.text }}
            >
              {letter}
            </div>
          );
        })}
      </div>

      <div className={`mt-0.5 grid grid-cols-5 ${s.gap}`}>
        {grid.map((row, r) =>
          row.map((value, c) => {
            const key = `${r}-${c}`;
            const isFree = value === null;
            const marked = isFree || (value !== null && markedSet.has(value));
            const onWinLine = winCellKeys.has(key);
            const canTap =
              isPlay && !autoOn && value !== null && drawn.has(value) && !markedSet.has(value);

            if (isFree) {
              return (
                <div
                  key={key}
                  className={`flex aspect-square items-center justify-center rounded-full bg-green-500 text-yellow-300 ${s.freeText} ${
                    onWinLine ? "animate-pulse ring-2 ring-yellow-300" : ""
                  }`}
                >
                  ★
                </div>
              );
            }

            return (
              <button
                key={key}
                type="button"
                disabled={!canTap}
                onClick={() => handleCellClick(value)}
                className={`flex aspect-square items-center justify-center rounded-full font-bold transition-all duration-150 ${s.cellText} ${
                  onWinLine
                    ? "animate-pulse bg-yellow-400 text-purple-950 ring-2 ring-yellow-200 shadow-md scale-105"
                    : marked
                      ? "bg-green-500 text-white shadow-inner"
                      : canTap
                        ? "bg-amber-100 text-stone-800 ring-1 ring-amber-400 active:scale-90 dark:bg-amber-500/20 dark:text-amber-50"
                        : isPlay
                          ? "bg-stone-100 text-stone-800 dark:bg-white/10 dark:text-stone-100"
                          : "bg-stone-50 text-stone-500 dark:bg-white/5 dark:text-stone-400"
                }`}
              >
                {value}
              </button>
            );
          }),
        )}
      </div>
    </div>
  );
}
