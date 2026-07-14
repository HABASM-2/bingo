interface BoardGridProps {
  poolMax: number;
  mine: Set<number>;
  taken: Set<number>;
  locked: boolean;
  onToggle: (boardId: number) => void;
}

/**
 * Scrollable 1..poolMax cartela picker (9 per row).
 * - Mine: green
 * - Others: gray + disabled
 * - Free: tappable
 */
export function BoardGrid({ poolMax, mine, taken, locked, onToggle }: BoardGridProps) {
  const boards = Array.from({ length: poolMax }, (_, i) => i + 1);

  return (
    <div className="max-h-[42vh] overflow-y-auto rounded-2xl bg-white/80 p-2 shadow-inner ring-1 ring-purple-200/80 dark:bg-[#1E1B2E]/80 dark:ring-white/10">
      <div className="grid grid-cols-9 gap-1">
        {boards.map((id) => {
          const isMine = mine.has(id);
          const isOthers = !isMine && taken.has(id);
          const disabled = isOthers || (locked && !isMine);

          return (
            <button
              key={id}
              type="button"
              disabled={disabled}
              onClick={() => onToggle(id)}
              aria-label={
                isMine
                  ? `Your board ${id}`
                  : isOthers
                    ? `Board ${id} taken by another player`
                    : `Select board ${id}`
              }
              className={`flex h-8 items-center justify-center rounded-lg text-[11px] font-bold transition-all duration-150 ${
                isMine
                  ? "bg-green-500 text-white shadow ring-2 ring-green-600/30"
                  : isOthers
                    ? "cursor-not-allowed bg-gray-400 text-gray-100 line-through opacity-75"
                    : "bg-stone-100 text-stone-600 hover:bg-purple-100 active:scale-95 dark:bg-white/10 dark:text-stone-200 dark:hover:bg-violet-500/30"
              }`}
            >
              {id}
            </button>
          );
        })}
      </div>
    </div>
  );
}
