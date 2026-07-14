import type { RoomStateMessage } from "../../types/bingo";
import { CalledColumns } from "./CalledColumns";
import { CurrentCall } from "./CurrentCall";

interface SpectatorViewProps {
  room: RoomStateMessage;
  drawn: number[];
  currentBall: number | null;
  soundOn: boolean;
  onToggleSound: () => void;
  winHold?: boolean;
}

function Stat({
  label,
  value,
  valueClass = "text-purple-900 dark:text-white",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center rounded-xl bg-white/95 px-1 py-1.5 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
      <span className="text-[10px] font-semibold text-purple-600 dark:text-purple-300">{label}</span>
      <span className={`truncate text-sm font-extrabold ${valueClass}`}>{value}</span>
    </div>
  );
}

export function SpectatorView({
  room,
  drawn,
  currentBall,
  soundOn,
  onToggleSound,
  winHold = false,
}: SpectatorViewProps) {
  return (
    <div className="flex flex-1 flex-col overflow-hidden animate-[fadeIn_0.3s_ease-out]">
      <div className="flex gap-1.5 px-2 py-2">
        <Stat label="Game ID" value={room.game_id ?? "—"} />
        <Stat label="Derash" value={room.derash} valueClass="text-green-600 dark:text-green-400" />
        <Stat label="Players" value={String(room.players_in_round)} />
        <Stat label="Call" value={String(drawn.length)} />
      </div>

      <div className="flex flex-1 gap-2 overflow-y-auto px-2 pb-2">
        <div className="w-[42%] shrink-0">
          <CalledColumns drawn={drawn} currentBall={currentBall} />
        </div>

        <div className="flex flex-1 flex-col gap-4">
          <CurrentCall
            currentBall={currentBall}
            drawn={drawn}
            soundOn={soundOn}
            autoOn={false}
            onToggleSound={onToggleSound}
            onToggleAuto={() => undefined}
            onRefresh={() => window.location.reload()}
            showAuto={false}
            emphasizeCall={winHold}
          />

          {winHold && (
            <p className="animate-pulse text-center text-sm font-bold text-orange-500">
              BINGO! Showing the last call…
            </p>
          )}

          <div className="flex flex-1 items-center justify-center rounded-2xl bg-white/50 px-4 py-6 ring-1 ring-purple-100 dark:bg-white/5 dark:ring-white/10">
            <p className="text-center text-base font-semibold leading-relaxed text-purple-700 dark:text-purple-200">
              እባክዎ ይህ ጨዋታ እስኪጨርስ ይጠብቁ
              <br />
              <span className="mt-2 block text-sm font-medium text-purple-400 dark:text-purple-300/70">
                You did not select a board — please wait until this game finishes
              </span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
