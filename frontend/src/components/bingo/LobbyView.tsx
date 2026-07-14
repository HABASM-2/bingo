import { BoardGrid } from "./BoardGrid";
import { Cartela } from "./Cartela";

interface LobbyViewProps {
  secondsLeft: number;
  balance: string;
  boardPrice: string;
  poolMax: number;
  maxBoards: number;
  myBoards: number[];
  takenBoards: number[];
  onToggleBoard: (boardId: number) => void;
  onDeselectAll: () => void;
}

function formatBalance(balance: string): string {
  const parsed = Number(balance);

  return Number.isFinite(parsed) ? parsed.toFixed(0) : balance;
}

function StatCard({
  label,
  value,
  valueClass,
  accent,
}: {
  label: string;
  value: string;
  valueClass: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`flex flex-1 flex-col items-center justify-center rounded-2xl py-2.5 shadow-sm ring-1 transition-transform duration-300 ${
        accent
          ? "bg-gradient-to-b from-orange-50 to-white ring-orange-200 dark:from-orange-500/20 dark:to-[#1E1B2E] dark:ring-orange-400/30"
          : "bg-white/90 ring-purple-100 dark:bg-[#1E1B2E] dark:ring-white/10"
      }`}
    >
      <span className="text-[10px] font-semibold uppercase tracking-wide text-purple-600 dark:text-purple-300">
        {label}
      </span>
      <span className={`text-2xl font-black tabular-nums ${valueClass}`}>{value}</span>
    </div>
  );
}

export function LobbyView({
  secondsLeft,
  balance,
  boardPrice,
  poolMax,
  maxBoards,
  myBoards,
  takenBoards,
  onToggleBoard,
  onDeselectAll,
}: LobbyViewProps) {
  const mine = new Set(myBoards);
  const taken = new Set(takenBoards);
  const price = Number(boardPrice);
  const bal = Number(balance);
  const affordableMax =
    Number.isFinite(price) && price > 0 && Number.isFinite(bal)
      ? Math.max(0, Math.floor(bal / price))
      : maxBoards;
  const locked = myBoards.length >= maxBoards || myBoards.length >= affordableMax;
  const previewSize = myBoards.length >= 2 ? "xs" : "sm";

  return (
    <div className="flex flex-col gap-3 px-3 py-3 animate-[fadeIn_0.35s_ease-out]">
      <div className="flex gap-2.5">
        <StatCard
          label="Starting in"
          value={String(secondsLeft)}
          valueClass="text-orange-500"
          accent
        />
        <StatCard
          label="Wallet"
          value={formatBalance(balance)}
          valueClass="text-purple-900 dark:text-white"
        />
        <StatCard
          label="Stake"
          value={boardPrice}
          valueClass="text-purple-900 dark:text-white"
        />
      </div>

      <div className="flex items-center justify-between rounded-xl bg-white/60 px-3 py-2 ring-1 ring-purple-100 dark:bg-white/5 dark:ring-white/10">
        <span className="text-sm font-bold text-green-600 dark:text-green-400">
          Boards {myBoards.length}/{Math.min(maxBoards, affordableMax)}
        </span>
        {myBoards.length > 0 ? (
          <button
            type="button"
            onClick={onDeselectAll}
            className="text-xs font-semibold text-purple-700 underline-offset-2 hover:underline dark:text-purple-300"
          >
            Deselect all
          </button>
        ) : affordableMax <= 0 ? (
          <span className="text-[11px] font-medium text-red-500">Need balance to play</span>
        ) : (
          <span className="text-[11px] font-medium text-purple-400">Tap a board to join</span>
        )}
      </div>

      <BoardGrid
        poolMax={poolMax}
        mine={mine}
        taken={taken}
        locked={locked}
        onToggle={onToggleBoard}
      />

      {myBoards.length > 0 && (
        <div
          className={`grid gap-2 pt-0.5 ${myBoards.length === 1 ? "grid-cols-1 max-w-[220px] mx-auto w-full" : "grid-cols-2"}`}
        >
          {myBoards.map((boardId) => (
            <div
              key={boardId}
              className="flex flex-col gap-1 animate-[fadeIn_0.3s_ease-out]"
            >
              <span className="text-center text-xs font-bold text-green-600 dark:text-green-400">
                Cartela #{boardId}
              </span>
              <Cartela boardId={boardId} variant="preview" size={previewSize} />
            </div>
          ))}
        </div>
      )}

      {myBoards.length === 0 && (
        <p className="pt-1 text-center text-sm text-purple-500 dark:text-purple-300/80">
          Pick up to {maxBoards} boards before the countdown ends to join the round.
        </p>
      )}
    </div>
  );
}
