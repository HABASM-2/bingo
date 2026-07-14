import { useEffect, useState } from "react";
import { BINGO_COLUMN_LETTERS, cartelaForBoard, patternCells } from "../../utils/cartela";
import { COLUMN_COLORS } from "./colors";
import type { WinnerInfo } from "../../types/bingo";

interface WinnerOverlayProps {
  winners: WinnerInfo[];
  winnerName: string | null;
  derash: string | null;
  derashShare?: string | null;
  drawn: number[];
  youWon: boolean;
  seconds: number;
}

const WIN_GREEN = "#22C55E";
const MATCH_YELLOW = "#FBE38A";

function WinnerCard({
  boardId,
  pattern,
  drawnSet,
}: {
  boardId: number;
  pattern: string;
  drawnSet: Set<number>;
}) {
  const grid = cartelaForBoard(boardId);
  const lineSet = new Set(patternCells(pattern).map(([r, c]) => `${r}-${c}`));

  return (
    <div className="rounded-2xl bg-white p-2 shadow ring-1 ring-purple-100">
      <div className="grid grid-cols-5 gap-1">
        {BINGO_COLUMN_LETTERS.map((letter) => {
          const color = COLUMN_COLORS[letter];
          return (
            <div
              key={letter}
              className="flex h-7 items-center justify-center rounded-md text-sm font-extrabold"
              style={{ backgroundColor: color.bg, color: color.text }}
            >
              {letter}
            </div>
          );
        })}
      </div>

      <div className="mt-1 grid grid-cols-5 gap-1">
        {grid.map((row, r) =>
          row.map((value, c) => {
            const key = `${r}-${c}`;
            const inLine = lineSet.has(key);
            const isFree = value === null;
            const matched = isFree || (value !== null && drawnSet.has(value));
            const background = inLine ? WIN_GREEN : matched ? MATCH_YELLOW : "#ffffff";

            return (
              <div
                key={key}
                className="flex aspect-square items-center justify-center rounded-md text-sm font-bold"
                style={{ backgroundColor: background, color: inLine ? "#ffffff" : "#1f2937" }}
              >
                {isFree ? "★" : value}
              </div>
            );
          }),
        )}
      </div>

      <p className="mt-1.5 text-center text-sm font-bold text-orange-500">
        Board number {boardId}
      </p>
    </div>
  );
}

export function WinnerOverlay({
  winners,
  winnerName,
  derash,
  derashShare,
  drawn,
  youWon,
  seconds,
}: WinnerOverlayProps) {
  const [countdown, setCountdown] = useState(seconds);

  useEffect(() => {
    setCountdown(seconds);
    const id = setInterval(() => {
      setCountdown((c) => (c > 0 ? c - 1 : 0));
    }, 1000);

    return () => clearInterval(id);
  }, [seconds]);

  const drawnSet = new Set(drawn);
  const boards = winners ?? [];
  const names =
    boards.length > 0
      ? Array.from(new Set(boards.map((w) => w.name)))
      : winnerName
        ? [winnerName]
        : [];
  const nameLabel = names.join(", ");
  const winnerCount = names.length;
  const boardCount = boards.length;
  const showSplit = winnerCount > 1 && derash != null && derashShare != null;
  const hasWinner = boards.length > 0 || winnerName != null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-sm flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div className="bg-orange-500 px-5 pb-4 pt-5 text-center">
          <h1 className="text-4xl font-black tracking-wide text-white drop-shadow">BINGO!</h1>

          {hasWinner ? (
            <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
              {nameLabel && (
                <span className="rounded-md bg-green-500 px-3 py-1 text-sm font-bold text-white shadow-sm">
                  {nameLabel}
                </span>
              )}
              <span className="text-base font-semibold text-white">
                {youWon ? "you have won the game." : "have won the game."}
              </span>
            </div>
          ) : (
            <p className="mt-3 text-base font-semibold text-white">No winner this round</p>
          )}

          {showSplit && (
            <p className="mt-2 text-sm font-semibold text-orange-50">
              Shared {Number(derash)} → {Number(derashShare)} each ({winnerCount} players
              {boardCount !== winnerCount ? `, ${boardCount} boards` : ""})
            </p>
          )}
        </div>

        <div className="flex flex-col gap-3 overflow-y-auto bg-white px-4 py-4">
          {boards.map((w) => (
            <WinnerCard
              key={w.card_id}
              boardId={Number(w.card_id)}
              pattern={w.pattern}
              drawnSet={drawnSet}
            />
          ))}
        </div>

        <div className="bg-orange-500 py-3 text-center">
          <span className="text-3xl font-black text-white">{countdown}</span>
        </div>
      </div>
    </div>
  );
}
