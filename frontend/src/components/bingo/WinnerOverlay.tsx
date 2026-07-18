import { useEffect, useRef, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Crown, Medal, Share2, Sparkles, Trophy, X } from "lucide-react";
import { useI18n } from "../../i18n";
import { BINGO_COLUMN_LETTERS, cartelaForBoard, patternCells } from "../../utils/cartela";
import { shareInviteLink } from "../../utils/inviteShare";
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
  inviteLink?: string | null;
  onDismiss?: () => void;
}

const WIN_GREEN = "#22C55E";
const MATCH_YELLOW = "#FBE38A";

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function useCountUp(target: number, active: boolean, durationMs = 900): number {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!active || !Number.isFinite(target) || target <= 0) {
      setValue(Number.isFinite(target) ? target : 0);
      return;
    }
    if (prefersReducedMotion()) {
      setValue(target);
      return;
    }

    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - t) ** 3;
      setValue(target * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, durationMs, target]);

  return value;
}

function CompactCartela({
  boardId,
  pattern,
  drawnSet,
}: {
  boardId: number;
  pattern: string;
  drawnSet: Set<number>;
}) {
  const { t } = useI18n();
  const grid = cartelaForBoard(boardId);
  const lineSet = new Set(patternCells(pattern).map(([r, c]) => `${r}-${c}`));

  return (
    <div className="mx-auto w-full max-w-[11.5rem] overflow-hidden rounded-xl bg-white/95 p-1.5 shadow-sm ring-1 ring-orange-200/70 dark:bg-[#1a1410] dark:ring-amber-500/25">
      <div className="grid grid-cols-5 gap-0.5">
        {BINGO_COLUMN_LETTERS.map((letter) => {
          const color = COLUMN_COLORS[letter];
          return (
            <div
              key={letter}
              className="flex h-5 items-center justify-center rounded text-[10px] font-extrabold"
              style={{ backgroundColor: color.bg, color: color.text }}
            >
              {letter}
            </div>
          );
        })}
      </div>

      <div className="mt-0.5 grid grid-cols-5 gap-0.5">
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
                className="flex aspect-square items-center justify-center rounded border border-stone-200/90 text-[9px] font-bold dark:border-white/15"
                style={{ backgroundColor: background, color: inLine ? "#ffffff" : "#1f2937" }}
              >
                {isFree ? "★" : value}
              </div>
            );
          }),
        )}
      </div>

      <p className="mt-1 text-center text-[10px] font-bold text-orange-600 dark:text-amber-300">
        {t("bingo.winner.board", { id: boardId })}
      </p>
    </div>
  );
}

function ConfettiBurst({ active }: { active: boolean }) {
  if (!active) return null;
  const bits = [
    { left: "12%", delay: "0ms", color: "bg-amber-300" },
    { left: "28%", delay: "80ms", color: "bg-emerald-400" },
    { left: "46%", delay: "40ms", color: "bg-orange-400" },
    { left: "62%", delay: "120ms", color: "bg-yellow-200" },
    { left: "78%", delay: "60ms", color: "bg-rose-400" },
    { left: "88%", delay: "100ms", color: "bg-sky-300" },
  ];

  return (
    <div className="pointer-events-none absolute inset-x-0 top-6 h-20 overflow-hidden" aria-hidden>
      {bits.map((bit, i) => (
        <span
          key={i}
          className={`absolute top-0 h-2 w-2 rounded-sm ${bit.color} animate-[winnerBurst_1.1s_ease-out_forwards] motion-reduce:animate-none motion-reduce:opacity-40`}
          style={{ left: bit.left, animationDelay: bit.delay }}
        />
      ))}
    </div>
  );
}

type WinnerSlide = {
  key: string;
  name: string;
  boardId: number | null;
  pattern: string;
  rank: number;
};

export function WinnerOverlay({
  winners,
  winnerName,
  derash,
  derashShare,
  drawn,
  youWon,
  seconds,
  inviteLink = null,
  onDismiss,
}: WinnerOverlayProps) {
  const { t, formatNumber } = useI18n();
  const [countdown, setCountdown] = useState(seconds);
  const [shareFlash, setShareFlash] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setCountdown(seconds);
    const id = setInterval(() => {
      setCountdown((c) => (c > 0 ? c - 1 : 0));
    }, 1000);

    return () => clearInterval(id);
  }, [seconds]);

  useEffect(() => {
    if (!shareFlash) return;
    const id = window.setTimeout(() => setShareFlash(false), 1600);
    return () => window.clearTimeout(id);
  }, [shareFlash]);

  const drawnSet = new Set(drawn);
  const boards = winners ?? [];

  const slides: WinnerSlide[] =
    boards.length > 0
      ? boards.map((w, i) => ({
          key: `${w.card_id}-${i}`,
          name: w.name,
          boardId: Number(w.card_id),
          pattern: w.pattern,
          rank: i + 1,
        }))
      : winnerName
        ? [{ key: "name-only", name: winnerName, boardId: null, pattern: "", rank: 1 }]
        : [];

  const winnerCount = new Set(slides.map((s) => s.name)).size || (winnerName ? 1 : 0);
  const boardCount = boards.length;
  const showSplit = winnerCount > 1 && derash != null && derashShare != null;
  const hasWinner = slides.length > 0;
  const prizeRaw = showSplit
    ? Number(derashShare)
    : derash != null
      ? Number(derash)
      : NaN;
  const prizeTarget = Number.isFinite(prizeRaw) ? prizeRaw : 0;
  const prizeDisplay = useCountUp(prizeTarget, hasWinner && prizeTarget > 0);
  const prizeLabel = formatNumber(prizeDisplay, {
    minimumFractionDigits: prizeTarget % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  });
  const link = (inviteLink ?? "").trim();
  const canShare = Boolean(link) && youWon && hasWinner;
  const multi = slides.length > 1;
  const safeIndex = Math.min(activeIndex, Math.max(0, slides.length - 1));

  const scrollToIndex = (index: number) => {
    const el = scrollerRef.current;
    if (!el) return;
    const clamped = Math.max(0, Math.min(index, slides.length - 1));
    const child = el.children[clamped] as HTMLElement | undefined;
    if (child) {
      child.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", inline: "center", block: "nearest" });
    }
    setActiveIndex(clamped);
  };

  const handleScroll = () => {
    const el = scrollerRef.current;
    if (!el || slides.length === 0) return;
    const slideWidth = el.clientWidth;
    if (slideWidth <= 0) return;
    const next = Math.round(el.scrollLeft / slideWidth);
    setActiveIndex(Math.max(0, Math.min(next, slides.length - 1)));
  };

  const handleShare = async () => {
    if (!canShare) return;
    const amount = formatNumber(prizeTarget, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
    const result = await shareInviteLink({
      url: link,
      title: t("bingo.winner.title"),
      text: t("bingo.winner.shareText", { amount }),
    });
    if (result === "copied" || result === "shared") setShareFlash(true);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55 px-3 pb-[max(5.5rem,calc(env(safe-area-inset-bottom)+4.75rem))] pt-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur-[3px] sm:items-center sm:pb-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("bingo.winner.title")}
        className="relative flex w-full max-w-sm flex-col overflow-hidden rounded-[1.75rem] bg-[#FFF8F0] shadow-[0_24px_60px_rgba(0,0,0,0.45)] animate-[winnerPop_0.45s_cubic-bezier(0.22,1,0.36,1)] motion-reduce:animate-none dark:bg-[#1A120C]"
      >
        <div
          className={`relative overflow-hidden px-4 pb-3.5 pt-5 text-center ${
            youWon
              ? "bg-gradient-to-br from-[#B45309] via-[#EA580C] to-[#F59E0B]"
              : hasWinner
                ? "bg-gradient-to-br from-[#9A3412] via-[#C2410C] to-[#D97706]"
                : "bg-gradient-to-br from-[#44403C] via-[#57534E] to-[#78716C]"
          }`}
        >
          <div className="pointer-events-none absolute -right-10 -top-12 h-36 w-36 rounded-full bg-white/20 blur-2xl" aria-hidden />
          <div className="pointer-events-none absolute -bottom-14 left-4 h-28 w-28 rounded-full bg-black/15 blur-2xl" aria-hidden />
          {youWon && <ConfettiBurst active />}

          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/20 text-white/90 outline-none ring-white/40 transition hover:bg-black/30 focus-visible:ring-2"
              aria-label={t("common.close")}
            >
              <X size={16} />
            </button>
          )}

          <div className="relative mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-white/20 ring-2 ring-white/35 backdrop-blur-sm animate-[winnerPulse_1.8s_ease-in-out_infinite] motion-reduce:animate-none">
            {youWon ? (
              <Crown size={26} className="text-amber-100" strokeWidth={2.2} aria-hidden />
            ) : hasWinner ? (
              <Trophy size={24} className="text-amber-100" strokeWidth={2.2} aria-hidden />
            ) : (
              <Medal size={24} className="text-stone-200" strokeWidth={2.2} aria-hidden />
            )}
          </div>

          <p className="relative text-[10px] font-extrabold uppercase tracking-[0.22em] text-white/80">
            {t("bingo.winner.title")}
          </p>

          {hasWinner ? (
            <>
              <h1 className="relative mt-1 text-[1.65rem] font-black leading-tight tracking-tight text-white drop-shadow-sm sm:text-3xl">
                {youWon ? t("bingo.winner.youWonTitle") : t("bingo.winner.theyWonTitle")}
              </h1>
              <p className="relative mt-1 text-sm font-semibold text-white/90">
                {youWon ? t("bingo.winner.congrats") : t("bingo.winner.theyWon")}
              </p>
            </>
          ) : (
            <h1 className="relative mt-2 text-xl font-black text-white">{t("bingo.winner.none")}</h1>
          )}

          {hasWinner && prizeTarget > 0 && (
            <div className="relative mt-3 inline-flex flex-col items-center rounded-2xl bg-black/25 px-4 py-2 ring-1 ring-white/25 animate-[prizeBounce_0.7s_cubic-bezier(0.22,1.4,0.36,1)] motion-reduce:animate-none">
              <span className="text-[10px] font-bold uppercase tracking-wider text-white/70">
                {t("bingo.winner.prizeLabel")}
              </span>
              <span className="text-[1.75rem] font-black tabular-nums leading-none text-white">
                {t("bingo.winner.prizeAmount", { amount: prizeLabel })}
              </span>
            </div>
          )}

          {showSplit && (
            <p className="relative mt-1.5 text-[11px] font-semibold text-orange-50/95">
              {t(
                boardCount !== winnerCount ? "bingo.winner.sharedBoards" : "bingo.winner.shared",
                {
                  total: Number(derash),
                  share: Number(derashShare),
                  winners: winnerCount,
                  boards: boardCount,
                },
              )}
            </p>
          )}

          {!youWon && hasWinner && (
            <p className="relative mt-1.5 text-[11px] font-medium text-white/75">
              {t("bingo.winner.spectatorHint")}
            </p>
          )}
        </div>

        {slides.length > 0 && (
          <div className="relative shrink-0 px-2 pb-1 pt-2.5">
            {multi && (
              <>
                <button
                  type="button"
                  onClick={() => scrollToIndex(safeIndex - 1)}
                  disabled={safeIndex <= 0}
                  className="absolute left-1 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 text-orange-800 shadow ring-1 ring-orange-200/80 outline-none transition enabled:active:scale-95 disabled:opacity-30 focus-visible:ring-2 focus-visible:ring-orange-500 dark:bg-[#2A1E14] dark:text-amber-200 dark:ring-amber-500/30"
                  aria-label={t("bingo.winner.prevSlide")}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  type="button"
                  onClick={() => scrollToIndex(safeIndex + 1)}
                  disabled={safeIndex >= slides.length - 1}
                  className="absolute right-1 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 text-orange-800 shadow ring-1 ring-orange-200/80 outline-none transition enabled:active:scale-95 disabled:opacity-30 focus-visible:ring-2 focus-visible:ring-orange-500 dark:bg-[#2A1E14] dark:text-amber-200 dark:ring-amber-500/30"
                  aria-label={t("bingo.winner.nextSlide")}
                >
                  <ChevronRight size={18} />
                </button>
              </>
            )}

            <div
              ref={scrollerRef}
              onScroll={handleScroll}
              className="flex snap-x snap-mandatory gap-0 overflow-x-auto overscroll-x-contain scroll-smooth [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
              role="list"
              aria-label={t("bingo.winner.slidesLabel")}
            >
              {slides.map((slide) => (
                <div
                  key={slide.key}
                  role="listitem"
                  className="w-full shrink-0 snap-center px-3"
                >
                  <div className="rounded-2xl bg-white/70 px-3 py-2.5 ring-1 ring-orange-200/60 dark:bg-white/[0.04] dark:ring-amber-500/20">
                    <div className="mb-2 flex items-center justify-center gap-1.5">
                      {multi && (
                        <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wide text-orange-700 dark:bg-amber-400/15 dark:text-amber-200">
                          {t("bingo.winner.rank", { n: slide.rank })}
                        </span>
                      )}
                      <p className="inline-flex max-w-full items-center gap-1.5 text-center text-[1.35rem] font-black leading-tight text-orange-950 dark:text-amber-50">
                        {youWon && slide.rank === 1 && (
                          <Sparkles size={16} className="shrink-0 text-amber-500" aria-hidden />
                        )}
                        <span className="truncate">{slide.name}</span>
                      </p>
                    </div>

                    {slide.boardId != null ? (
                      <CompactCartela
                        boardId={slide.boardId}
                        pattern={slide.pattern}
                        drawnSet={drawnSet}
                      />
                    ) : (
                      <p className="py-3 text-center text-xs font-semibold text-orange-700/70 dark:text-amber-200/70">
                        {t("bingo.winner.boardUnavailable")}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {multi && (
              <div className="mt-2 flex items-center justify-center gap-1.5" role="tablist" aria-label={t("bingo.winner.slidesLabel")}>
                {slides.map((slide, i) => (
                  <button
                    key={slide.key}
                    type="button"
                    role="tab"
                    aria-selected={i === safeIndex}
                    onClick={() => scrollToIndex(i)}
                    className={`h-1.5 rounded-full transition-all outline-none focus-visible:ring-2 focus-visible:ring-orange-500 ${
                      i === safeIndex
                        ? "w-5 bg-orange-500 dark:bg-amber-400"
                        : "w-1.5 bg-orange-300/70 dark:bg-amber-500/40"
                    }`}
                    aria-label={t("bingo.winner.goToSlide", { n: i + 1 })}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        <div className="shrink-0 space-y-1.5 border-t border-orange-200/70 bg-[#FFF1E0] px-3 py-2.5 dark:border-amber-500/20 dark:bg-[#22180F]">
          <div className="flex gap-2">
            {canShare && (
              <button
                type="button"
                onClick={() => void handleShare()}
                className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-white px-3 py-2.5 text-sm font-extrabold text-orange-800 shadow-sm ring-1 ring-orange-200 outline-none transition active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-orange-500 dark:bg-[#2A1E14] dark:text-amber-200 dark:ring-amber-500/30"
              >
                {shareFlash ? <Check size={16} /> : <Share2 size={16} />}
                {shareFlash ? t("bingo.winner.copied") : t("bingo.winner.shareWin")}
              </button>
            )}
            <button
              type="button"
              onClick={() => onDismiss?.()}
              className={`inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 px-3 py-2.5 text-sm font-extrabold text-white shadow-md outline-none transition active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-2 ${
                canShare ? "flex-1" : "w-full"
              }`}
            >
              {t("bingo.winner.continue")}
            </button>
          </div>
          <p className="text-center text-[11px] font-bold tabular-nums text-orange-800/70 dark:text-amber-200/70">
            {t("bingo.winner.nextRound", { seconds: countdown })}
          </p>
        </div>
      </div>
    </div>
  );
}
