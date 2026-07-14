import { RefreshCw, Volume2, VolumeX, Zap } from "lucide-react";
import { callLabel } from "../../utils/cartela";
import { columnColorForNumber } from "./colors";

interface CurrentCallProps {
  currentBall: number | null;
  drawn: number[];
  soundOn: boolean;
  autoOn: boolean;
  onToggleSound: () => void;
  onToggleAuto: () => void;
  onRefresh: () => void;
  compact?: boolean;
  showAuto?: boolean;
  /** Glow the current-call ball during the winner hold beat. */
  emphasizeCall?: boolean;
}

export function CurrentCall({
  currentBall,
  drawn,
  soundOn,
  autoOn,
  onToggleSound,
  onToggleAuto,
  onRefresh,
  compact = false,
  showAuto = true,
  emphasizeCall = false,
}: CurrentCallProps) {
  const recent = [...drawn].reverse().slice(0, compact ? 4 : 5);

  return (
    <div className={`flex flex-col ${compact ? "gap-1.5" : "gap-2"}`}>
      <div
        className={`flex items-center justify-between rounded-2xl bg-gradient-to-br from-[#4C1D95] to-[#7C3AED] shadow-md ${
          compact ? "px-3 py-2.5" : "px-3.5 py-3.5"
        } ${emphasizeCall ? "ring-2 ring-yellow-300 ring-offset-1 ring-offset-transparent" : ""}`}
      >
        <span className={`font-bold text-white ${compact ? "text-sm" : "text-base"}`}>
          Current Call
        </span>
        <div
          className={`flex items-center justify-center rounded-full bg-orange-500 font-extrabold text-white shadow-lg transition-transform ${
            compact ? "h-11 w-11 text-sm" : "h-12 w-12 text-base"
          } ${emphasizeCall ? "scale-110 animate-pulse ring-4 ring-yellow-300" : ""}`}
        >
          {currentBall !== null ? callLabel(currentBall) : "--"}
        </div>
      </div>

      <div
        className={`flex items-center gap-1.5 overflow-x-auto rounded-2xl bg-purple-100/70 px-2 dark:bg-white/5 ${
          compact ? "min-h-10 py-1.5" : "min-h-11 py-2"
        }`}
      >
        {recent.length === 0 ? (
          <span className="px-1 text-xs text-purple-400">Waiting…</span>
        ) : (
          recent.map((n, idx) => {
            const color = columnColorForNumber(n);
            const isLatest = idx === 0;
            return (
              <div
                key={`${n}-${drawn.lastIndexOf(n)}`}
                className={`flex shrink-0 items-center justify-center rounded-full font-bold shadow ${
                  compact ? "h-8 w-8 text-[10px]" : "h-9 w-9 text-[11px]"
                } ${isLatest && emphasizeCall ? "ring-2 ring-yellow-300 scale-110" : ""}`}
                style={{ backgroundColor: color.bg, color: color.text }}
              >
                {callLabel(n)}
              </div>
            );
          })
        )}
      </div>

      <div className={`grid gap-1.5 ${showAuto ? "grid-cols-3" : "grid-cols-2"}`}>
        <button
          type="button"
          onClick={onRefresh}
          className="flex items-center justify-center gap-1 rounded-xl bg-blue-600 py-2 text-xs font-bold text-white shadow active:scale-95"
        >
          <RefreshCw size={14} />
          Refresh
        </button>

        <button
          type="button"
          onClick={onToggleSound}
          className={`flex items-center justify-center gap-1 rounded-xl py-2 text-xs font-bold shadow active:scale-95 ${
            soundOn
              ? "bg-purple-700 text-white"
              : "bg-white/80 text-purple-700 ring-1 ring-purple-200 dark:bg-white/10 dark:text-purple-200 dark:ring-white/10"
          }`}
        >
          {soundOn ? <Volume2 size={14} /> : <VolumeX size={14} />}
          Sound
        </button>

        {showAuto && (
          <button
            type="button"
            onClick={onToggleAuto}
            className={`flex items-center justify-center gap-1 rounded-xl py-2 text-xs font-bold text-white shadow active:scale-95 ${
              autoOn ? "bg-green-500" : "bg-gray-400"
            }`}
          >
            <Zap size={14} />
            Auto {autoOn ? "ON" : "OFF"}
          </button>
        )}
      </div>
    </div>
  );
}
