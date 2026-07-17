import type { BingoCard, RoomStateMessage, WinnerInfo } from "../../types/bingo";
import { useI18n } from "../../i18n";
import { CalledColumns } from "./CalledColumns";
import { CallControls, CurrentCall } from "./CurrentCall";
import { Cartela } from "./Cartela";

interface ActiveGameViewProps {
  room: RoomStateMessage;
  drawn: number[];
  currentBall: number | null;
  cards: BingoCard[];
  soundOn: boolean;
  audioBlocked?: boolean;
  autoOn: boolean;
  onToggleSound: () => void;
  onEnableAudio?: () => void;
  onToggleAuto: () => void;
  onClaim: (cardId: string) => void;
  onRefresh: () => void;
  winHold?: boolean;
  winners?: WinnerInfo[];
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center rounded-xl bg-white/95 px-1 py-1.5 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-purple-600 dark:text-purple-300">
        {label}
      </span>
      <span className="truncate text-sm font-extrabold tabular-nums text-purple-900 dark:text-white">
        {value}
      </span>
    </div>
  );
}

export function ActiveGameView({
  room,
  drawn,
  currentBall,
  cards,
  soundOn,
  audioBlocked = false,
  autoOn,
  onToggleSound,
  onEnableAudio,
  onToggleAuto,
  onClaim,
  onRefresh,
  winHold = false,
  winners = [],
}: ActiveGameViewProps) {
  const { t } = useI18n();
  const drawnSet = new Set(drawn);
  const myStake = (Number(room.board_price) * cards.length).toFixed(0);
  const twoCards = cards.length >= 2;

  const patternByCard = new Map(
    winners.map((w) => [String(w.card_id), w.pattern] as const),
  );

  return (
    <div className="flex flex-1 flex-col overflow-hidden animate-[fadeIn_0.3s_ease-out]">
      <div className="flex gap-1.5 px-2 py-2">
        <Chip label={t("bingo.game")} value={room.game_id ?? "—"} />
        <Chip label={t("bingo.derash")} value={room.derash} />
        <Chip label={t("common.players")} value={String(room.players_in_round)} />
        <Chip label={t("common.bet")} value={myStake} />
        <Chip label={t("bingo.call")} value={String(drawn.length)} />
      </div>

      <div className="flex min-h-0 flex-1 gap-1.5 overflow-hidden px-1.5 pb-1.5">
        {/* Left: all call information and controls, stacked vertically. */}
        <div className="flex min-w-0 flex-1 basis-0 flex-col gap-1.5 overflow-y-auto rounded-2xl bg-white/35 p-1 dark:bg-white/[0.03]">
          <CurrentCall
            currentBall={currentBall}
            drawn={drawn}
            soundOn={soundOn}
            audioBlocked={audioBlocked}
            autoOn={autoOn}
            onToggleSound={onToggleSound}
            onEnableAudio={onEnableAudio}
            onToggleAuto={onToggleAuto}
            onRefresh={onRefresh}
            compact
            showControls={false}
            emphasizeCall={winHold}
          />

          {winHold && (
            <p className="animate-pulse text-center text-[10px] font-bold text-orange-500">
              {t("bingo.winHoldActive")}
            </p>
          )}

          {/* The complete B-I-N-G-O 1–75 holder sits below the controls. */}
          <CalledColumns drawn={drawn} currentBall={currentBall} />
        </div>

        {/* Right: cartelas only, with the full remaining width. */}
        <div className="flex min-h-0 min-w-0 flex-1 basis-0 flex-col gap-1 overflow-y-auto rounded-2xl bg-gradient-to-b from-purple-100/60 to-transparent p-1 dark:from-white/[0.06]">
          <CallControls
            soundOn={soundOn}
            audioBlocked={audioBlocked}
            autoOn={autoOn}
            onToggleSound={onToggleSound}
            onEnableAudio={onEnableAudio}
            onToggleAuto={onToggleAuto}
            onRefresh={onRefresh}
            compact
          />

          <div className="flex w-full min-w-0 flex-col items-center gap-1.5">
            {cards.map((card) => {
              const boardId = Number(card.card_id);
              const winPattern = winHold ? (patternByCard.get(String(card.card_id)) ?? null) : null;

              return (
                <div
                  key={card.card_id}
                  className={`flex w-full max-w-[180px] flex-col gap-0.5 rounded-xl bg-white/95 p-1 shadow-md ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10 ${
                    winPattern ? "ring-2 ring-yellow-400" : ""
                  }`}
                >
                  <div className="flex items-center justify-between gap-1 px-0.5">
                    <span className="text-[10px] font-bold text-green-600 dark:text-green-400">
                      #{card.card_id}
                    </span>
                    <button
                      type="button"
                      onClick={() => onClaim(card.card_id)}
                      className="rounded-full bg-orange-500 px-2.5 py-0.5 text-[10px] font-extrabold tracking-wide text-white shadow active:scale-95"
                    >
                      {t("bingo.bingoButton")}
                    </button>
                  </div>
                  <Cartela
                    boardId={boardId}
                    drawnSet={drawnSet}
                    variant="play"
                    size={twoCards ? "xs" : "sm"}
                    autoOn={autoOn}
                    winPattern={winPattern}
                  />
                </div>
              );
            })}
          </div>

          {twoCards && <div className="h-1 shrink-0" aria-hidden />}
        </div>
      </div>
    </div>
  );
}
