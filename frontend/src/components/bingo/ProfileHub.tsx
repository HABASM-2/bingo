import {
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Crown,
  Loader2,
  Plane,
  Sparkles,
  Trophy,
  Wallet,
} from "lucide-react";
import {
  getGameHistory,
  getMyPayments,
  type ProfileGameKey,
  type ProfileLottoItem,
  type ProfilePaymentItem,
  type ProfilePaymentType,
  type ProfilePlinkoItem,
} from "../../services/profile";
import type { AviatorHistoryBet } from "../../services/aviator";
import type { GameHistoryEntry } from "../../types/bingo";
import type { DamaHistoryEntry } from "../../types/dama";
import { useI18n } from "../../i18n";
import type { TranslationKey } from "../../i18n";
import { LanguagePreference } from "./LanguagePreference";
import { ThemePreference } from "./ThemePreference";

const PAGE_SIZE = 5;

const GAME_KEYS: ProfileGameKey[] = ["bingo", "dama", "aviator", "plinko", "lotto"];
const PAYMENT_TYPES: ProfilePaymentType[] = ["deposit", "withdraw"];

interface ProfileHubProps {
  firstName: string;
  balance: string | null;
  boardPrice: string;
}

type Translate = ReturnType<typeof useI18n>["t"];
type FormatDate = ReturnType<typeof useI18n>["formatDate"];

function formatBalance(balance: string | null): string {
  if (balance == null) return "—";
  const n = Number(balance);
  return Number.isFinite(n) ? n.toFixed(2) : balance;
}

function formatMoney(value: string | number | null | undefined): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(0) : String(value ?? "—");
}

function formatShortDate(iso: string | null | undefined, formatDate: FormatDate): string {
  if (!iso) return "";
  return formatDate(iso, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function pageRangeLabel(offset: number, count: number, total: number, t: Translate): string {
  if (total <= 0) return t("profile.pageRange", { from: 0, to: 0, total: 0 });
  const from = offset + 1;
  const to = offset + count;
  return t("profile.pageRange", { from, to, total });
}

function SectionShell({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-500/15 text-violet-700 dark:text-violet-300">
          {icon}
        </div>
        <h2 className="text-sm font-bold text-purple-900 dark:text-white">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <p className="py-6 text-center text-sm text-purple-500 dark:text-purple-300">{message}</p>
  );
}

function SoftLoader() {
  return (
    <div className="flex justify-center py-8">
      <Loader2 size={22} className="animate-spin text-purple-400" />
    </div>
  );
}

function RowShell({
  children,
  tint = "purple",
}: {
  children: ReactNode;
  tint?: "purple" | "orange" | "sky" | "emerald" | "rose";
}) {
  const tintClass =
    tint === "orange"
      ? "bg-orange-50/70 dark:bg-white/5"
      : tint === "sky"
        ? "bg-sky-50/70 dark:bg-white/5"
        : tint === "emerald"
          ? "bg-emerald-50/70 dark:bg-white/5"
          : tint === "rose"
            ? "bg-rose-50/70 dark:bg-white/5"
            : "bg-purple-50/80 dark:bg-white/5";
  return (
    <li className={`flex items-center justify-between gap-3 rounded-2xl px-3.5 py-3 ${tintClass}`}>
      {children}
    </li>
  );
}

function PageControls({
  offset,
  count,
  total,
  loading,
  onPrev,
  onNext,
  t,
}: {
  offset: number;
  count: number;
  total: number;
  loading: boolean;
  onPrev: () => void;
  onNext: () => void;
  t: Translate;
}) {
  const canPrev = offset > 0 && !loading;
  const canNext = offset + PAGE_SIZE < total && !loading;
  if (total <= 0) return null;

  return (
    <div className="mt-3 flex items-center justify-between gap-2">
      <button
        type="button"
        onClick={onPrev}
        disabled={!canPrev}
        className="inline-flex h-9 items-center gap-1 rounded-xl bg-purple-100/80 px-3 text-xs font-bold text-purple-800 outline-none transition enabled:active:scale-[0.98] disabled:opacity-35 focus-visible:ring-2 focus-visible:ring-violet-500 dark:bg-white/10 dark:text-purple-100"
        aria-label={t("profile.prevPage")}
      >
        <ChevronLeft size={14} />
        {t("profile.prev")}
      </button>
      <p className="text-[11px] font-semibold tabular-nums text-purple-500 dark:text-purple-300">
        {pageRangeLabel(offset, count, total, t)}
      </p>
      <button
        type="button"
        onClick={onNext}
        disabled={!canNext}
        className="inline-flex h-9 items-center gap-1 rounded-xl bg-purple-100/80 px-3 text-xs font-bold text-purple-800 outline-none transition enabled:active:scale-[0.98] disabled:opacity-35 focus-visible:ring-2 focus-visible:ring-violet-500 dark:bg-white/10 dark:text-purple-100"
        aria-label={t("profile.nextPage")}
      >
        {t("profile.next")}
        <ChevronRight size={14} />
      </button>
    </div>
  );
}

function SegmentTabs<T extends string>({
  keys,
  active,
  onSelect,
  label,
  icon,
}: {
  keys: readonly T[];
  active: T;
  onSelect: (key: T) => void;
  label: (key: T) => string;
  icon: (key: T) => ReactNode;
}) {
  return (
    <div
      className="mb-3 flex gap-1.5 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      role="tablist"
    >
      {keys.map((key) => {
        const selected = key === active;
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onSelect(key)}
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold outline-none transition focus-visible:ring-2 focus-visible:ring-violet-500 ${
              selected
                ? "bg-violet-600 text-white shadow-sm dark:bg-violet-500"
                : "bg-purple-50 text-purple-700 dark:bg-white/5 dark:text-purple-200"
            }`}
          >
            <span className={selected ? "text-white/90" : "text-violet-600 dark:text-violet-300"}>
              {icon(key)}
            </span>
            {label(key)}
          </button>
        );
      })}
    </div>
  );
}

function DotIndicators({
  count,
  activeIndex,
  onSelect,
  label,
}: {
  count: number;
  activeIndex: number;
  onSelect: (index: number) => void;
  label: (index: number) => string;
}) {
  return (
    <div className="mb-2 flex items-center justify-center gap-1.5" role="tablist" aria-label="pages">
      {Array.from({ length: count }, (_, i) => (
        <button
          key={i}
          type="button"
          role="tab"
          aria-selected={i === activeIndex}
          aria-label={label(i)}
          onClick={() => onSelect(i)}
          className={`h-1.5 rounded-full transition-all outline-none focus-visible:ring-2 focus-visible:ring-violet-500 ${
            i === activeIndex
              ? "w-5 bg-violet-600 dark:bg-violet-400"
              : "w-1.5 bg-purple-200 dark:bg-white/20"
          }`}
        />
      ))}
    </div>
  );
}

function useSnapIndex(count: number, activeIndex: number, onIndexChange: (index: number) => void) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const scrollingRef = useRef(false);

  const syncFromScroll = useEffectEvent(() => {
    const el = scrollerRef.current;
    if (!el || scrollingRef.current) return;
    const width = el.clientWidth || 1;
    const next = Math.round(el.scrollLeft / width);
    const clamped = Math.max(0, Math.min(count - 1, next));
    if (clamped !== activeIndex) onIndexChange(clamped);
  });

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const width = el.clientWidth || 1;
    const target = activeIndex * width;
    if (Math.abs(el.scrollLeft - target) < 2) return;
    scrollingRef.current = true;
    el.scrollTo({ left: target, behavior: "smooth" });
    const timer = window.setTimeout(() => {
      scrollingRef.current = false;
    }, 320);
    return () => window.clearTimeout(timer);
  }, [activeIndex, count]);

  return { scrollerRef, onScroll: syncFromScroll };
}

function BingoRow({
  game,
  t,
  formatDate,
}: {
  game: GameHistoryEntry;
  t: Translate;
  formatDate: FormatDate;
}) {
  const winnerNames = game.winner_names ?? [];
  const winnerCount = game.winner_count ?? winnerNames.length;
  const hasWinners = winnerCount > 0 || winnerNames.length > 0;
  const gross = Number(game.derash);
  const fee = Number(game.system_fee ?? 0);
  const prize =
    game.prize_pool != null
      ? Number(game.prize_pool)
      : Number.isFinite(gross) && Number.isFinite(fee)
        ? gross - fee
        : gross;
  const wonAmount = Number(game.amount_won);

  return (
    <RowShell>
      <div className="min-w-0">
        <p className="truncate text-sm font-bold text-purple-900 dark:text-white">
          #{game.game_id}
        </p>
        <p className="text-[11px] text-purple-500 dark:text-purple-300">
          {t("profile.boardsStakePlayers", {
            count: game.boards_count,
            boards: game.boards_count,
            stake: formatMoney(game.stake),
            players: game.total_boards,
          })}
        </p>
        {hasWinners ? (
          <p className="truncate text-[11px] font-semibold text-orange-500 dark:text-orange-300">
            {winnerNames.length > 0
              ? t(winnerNames.length === 1 ? "profile.winnerNamed" : "profile.winnersNamed", {
                  names: winnerNames.join(", "),
                })
              : t("profile.winners")}
            {" · "}
            {t("profile.winnersTotal", { count: winnerCount })}
          </p>
        ) : (
          <p className="text-[11px] text-purple-400">{t("profile.noWinner")}</p>
        )}
        <p className="text-[10px] text-purple-400">
          {fee > 0
            ? t("profile.potFeePrize", {
                pot: Number.isFinite(gross) ? formatMoney(gross) : game.derash,
                fee: formatMoney(fee),
                prize: Number.isFinite(prize) ? formatMoney(prize) : prize,
              })
            : t("profile.potOnly", {
                pot: Number.isFinite(gross) ? formatMoney(gross) : game.derash,
              })}
          {game.created_at ? ` · ${formatShortDate(game.created_at, formatDate)}` : ""}
        </p>
      </div>
      <div className="shrink-0 text-right">
        {game.is_winner ? (
          <>
            <p className="text-sm font-extrabold text-green-600 dark:text-green-400">
              +{Number.isFinite(wonAmount) ? formatMoney(wonAmount) : game.amount_won}
            </p>
            <p className="text-[10px] font-medium text-green-600/80 dark:text-green-400/80">
              {t("profile.netWin")}
            </p>
          </>
        ) : (
          <>
            <p className="text-sm font-semibold text-red-400">-{formatMoney(game.stake)}</p>
            <p className="text-[10px] text-purple-400">
              {t("profile.prizeAmount", {
                prize: Number.isFinite(prize) ? formatMoney(prize) : "—",
              })}
            </p>
          </>
        )}
      </div>
    </RowShell>
  );
}

function DamaRow({
  game,
  t,
  formatDate,
}: {
  game: DamaHistoryEntry;
  t: Translate;
  formatDate: FormatDate;
}) {
  const wonAmount = Number(game.amount_won);
  const stake = Number(game.stake);
  return (
    <RowShell tint="orange">
      <div className="min-w-0">
        <p className="truncate text-sm font-bold text-purple-900 dark:text-white">
          #{game.game_id}
        </p>
        <p className="text-[11px] text-purple-500 dark:text-purple-300">
          {game.mode === "ai" ? t("profile.vsComputer") : t("profile.online")} ·{" "}
          {t("common.stake")} {Number.isFinite(stake) ? formatMoney(stake) : game.stake}{" "}
          {t("common.etb")}
        </p>
        <p className="text-[10px] text-purple-400">
          {Number(game.system_fee) > 0
            ? t("profile.potFeePrize", {
                pot: formatMoney(game.pot),
                fee: formatMoney(game.system_fee),
                prize: formatMoney(game.prize_pool),
              })
            : t("profile.potOnly", { pot: formatMoney(game.pot) })}
          {game.created_at ? ` · ${formatShortDate(game.created_at, formatDate)}` : ""}
        </p>
      </div>
      <div className="shrink-0 text-right">
        {game.outcome === "draw" ? (
          <>
            <p className="text-sm font-extrabold text-sky-600 dark:text-sky-300">±0</p>
            <p className="text-[10px] text-purple-400">{t("common.refund")}</p>
          </>
        ) : game.is_winner ? (
          <>
            <p className="text-sm font-extrabold text-green-600 dark:text-green-400">
              +{Number.isFinite(wonAmount) ? formatMoney(wonAmount) : game.amount_won}
            </p>
            <p className="text-[10px] font-medium text-green-600/80">{t("common.win")}</p>
          </>
        ) : (
          <>
            <p className="text-sm font-semibold text-red-400">
              -{Number.isFinite(stake) ? formatMoney(stake) : game.stake}
            </p>
            <p className="text-[10px] text-purple-400">{t("common.loss")}</p>
          </>
        )}
      </div>
    </RowShell>
  );
}

function AviatorRow({
  bet,
  t,
  formatDate,
}: {
  bet: AviatorHistoryBet;
  t: Translate;
  formatDate: FormatDate;
}) {
  const won = bet.outcome === "won";
  return (
    <RowShell tint="sky">
      <div className="min-w-0">
        <p className="truncate text-sm font-bold text-purple-900 dark:text-white">
          #{bet.round_code || bet.bet_id.slice(0, 8)}
        </p>
        <p className="text-[11px] text-purple-500 dark:text-purple-300">
          {t("common.stake")} {formatMoney(bet.stake)}
          {bet.cashout_multiplier ? ` · ${Number(bet.cashout_multiplier).toFixed(2)}x` : ""}
          {bet.crash_multiplier ? ` · crash ${Number(bet.crash_multiplier).toFixed(2)}x` : ""}
        </p>
        <p className="text-[10px] text-purple-400">
          {formatShortDate(bet.created_at, formatDate)}
        </p>
      </div>
      <div className="shrink-0 text-right">
        {won ? (
          <>
            <p className="text-sm font-extrabold text-green-600 dark:text-green-400">
              +{formatMoney(bet.amount_won)}
            </p>
            <p className="text-[10px] text-green-600/80">{t("common.win")}</p>
          </>
        ) : (
          <>
            <p className="text-sm font-semibold text-red-400">-{formatMoney(bet.stake)}</p>
            <p className="text-[10px] text-purple-400">{t("common.loss")}</p>
          </>
        )}
      </div>
    </RowShell>
  );
}

function PlinkoRow({
  item,
  t,
  formatDate,
}: {
  item: ProfilePlinkoItem;
  t: Translate;
  formatDate: FormatDate;
}) {
  const net = Number(item.net);
  const positive = net > 0;
  return (
    <RowShell tint="emerald">
      <div className="min-w-0">
        <p className="truncate text-sm font-bold text-purple-900 dark:text-white">
          {Number(item.multiplier).toFixed(2)}x · {item.risk} · {item.rows}r
        </p>
        <p className="text-[11px] text-purple-500 dark:text-purple-300">
          {t("common.stake")} {formatMoney(item.stake)}
          {item.is_demo ? ` · ${t("profile.demo")}` : ""}
        </p>
        <p className="text-[10px] text-purple-400">
          {formatShortDate(item.created_at, formatDate)}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p
          className={`text-sm font-extrabold ${
            positive
              ? "text-green-600 dark:text-green-400"
              : net < 0
                ? "text-red-400"
                : "text-purple-500"
          }`}
        >
          {positive ? "+" : ""}
          {formatMoney(item.net)}
        </p>
        <p className="text-[10px] text-purple-400">
          {t("profile.payout", { amount: formatMoney(item.payout) })}
        </p>
      </div>
    </RowShell>
  );
}

function LottoRow({
  item,
  t,
  formatDate,
}: {
  item: ProfileLottoItem;
  t: Translate;
  formatDate: FormatDate;
}) {
  const net = Number(item.net);
  const positive = net > 0;
  return (
    <RowShell tint="rose">
      <div className="min-w-0">
        <p className="truncate text-sm font-bold text-purple-900 dark:text-white">
          #{item.round_code}
        </p>
        <p className="text-[11px] text-purple-500 dark:text-purple-300">
          {t("common.stake")} {formatMoney(item.stake)} · {item.numbers.length}{" "}
          {t("profile.numbers")}
        </p>
        <p className="text-[10px] text-purple-400">
          {formatShortDate(item.completed_at, formatDate)}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p
          className={`text-sm font-extrabold ${
            positive
              ? "text-green-600 dark:text-green-400"
              : net < 0
                ? "text-red-400"
                : "text-purple-500"
          }`}
        >
          {positive ? "+" : ""}
          {formatMoney(item.net)}
        </p>
        <p className="text-[10px] text-purple-400">
          {t("profile.prizeAmount", { prize: formatMoney(item.total_prize) })}
        </p>
      </div>
    </RowShell>
  );
}

function PaymentRow({
  item,
  kind,
  t,
  formatDate,
}: {
  item: ProfilePaymentItem;
  kind: ProfilePaymentType;
  t: Translate;
  formatDate: FormatDate;
}) {
  return (
    <RowShell tint={kind === "deposit" ? "emerald" : "rose"}>
      <div className="min-w-0">
        <p className="truncate text-sm font-bold capitalize text-purple-900 dark:text-white">
          {item.method}
        </p>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-purple-500 dark:text-purple-300">
          {item.status}
          {item.account_masked ? ` · ${item.account_masked}` : ""}
        </p>
        <p className="text-[10px] text-purple-400">
          {formatShortDate(item.created_at, formatDate)}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p
          className={`text-sm font-extrabold ${
            kind === "deposit"
              ? "text-green-600 dark:text-green-400"
              : "text-purple-900 dark:text-white"
          }`}
        >
          {kind === "deposit" ? "+" : "-"}
          {formatMoney(item.amount)}
        </p>
        <p className="text-[10px] text-purple-400">{t("common.etb")}</p>
      </div>
    </RowShell>
  );
}

function gameIcon(key: ProfileGameKey): ReactNode {
  switch (key) {
    case "bingo":
      return <Trophy size={13} />;
    case "dama":
      return <Crown size={13} />;
    case "aviator":
      return <Plane size={13} />;
    case "plinko":
      return <Sparkles size={13} />;
    case "lotto":
      return <Trophy size={13} />;
  }
}

function gameTitleKey(key: ProfileGameKey): TranslationKey {
  switch (key) {
    case "bingo":
      return "profile.sectionBingo";
    case "dama":
      return "profile.sectionDama";
    case "aviator":
      return "profile.sectionAviator";
    case "plinko":
      return "profile.sectionPlinko";
    case "lotto":
      return "profile.sectionLotto";
  }
}

function gameEmptyKey(key: ProfileGameKey): TranslationKey {
  switch (key) {
    case "bingo":
      return "profile.noBingo";
    case "dama":
      return "profile.noDama";
    case "aviator":
      return "profile.noAviator";
    case "plinko":
      return "profile.noPlinko";
    case "lotto":
      return "profile.noLotto";
  }
}

function renderGameItem(
  game: ProfileGameKey,
  item: unknown,
  t: Translate,
  formatDate: FormatDate,
): ReactNode {
  switch (game) {
    case "bingo": {
      const row = item as GameHistoryEntry;
      return (
        <BingoRow
          key={`${row.game_id}-${row.created_at}`}
          game={row}
          t={t}
          formatDate={formatDate}
        />
      );
    }
    case "dama": {
      const row = item as DamaHistoryEntry;
      return (
        <DamaRow
          key={`${row.game_id}-${row.created_at}`}
          game={row}
          t={t}
          formatDate={formatDate}
        />
      );
    }
    case "aviator": {
      const row = item as AviatorHistoryBet;
      return <AviatorRow key={row.bet_id} bet={row} t={t} formatDate={formatDate} />;
    }
    case "plinko": {
      const row = item as ProfilePlinkoItem;
      return <PlinkoRow key={row.play_id} item={row} t={t} formatDate={formatDate} />;
    }
    case "lotto": {
      const row = item as ProfileLottoItem;
      return <LottoRow key={row.round_id} item={row} t={t} formatDate={formatDate} />;
    }
  }
}

function GameHistoryCarousel({ t, formatDate }: { t: Translate; formatDate: FormatDate }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [offsets, setOffsets] = useState<Record<ProfileGameKey, number>>(() =>
    Object.fromEntries(GAME_KEYS.map((k) => [k, 0])) as Record<ProfileGameKey, number>,
  );
  const [items, setItems] = useState<unknown[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const activeGame = GAME_KEYS[activeIndex] ?? "bingo";
  const offset = offsets[activeGame] ?? 0;
  const { scrollerRef, onScroll } = useSnapIndex(GAME_KEYS.length, activeIndex, setActiveIndex);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(false);

    getGameHistory(activeGame, PAGE_SIZE, offset, controller.signal)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items ?? []);
        setTotal(page.total ?? 0);
      })
      .catch((err: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        const name = (err as { name?: string; code?: string })?.name;
        const code = (err as { code?: string })?.code;
        if (name === "CanceledError" || name === "AbortError" || code === "ERR_CANCELED") {
          return;
        }
        setError(true);
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled && !controller.signal.aborted) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeGame, offset]);

  const selectGame = (key: ProfileGameKey) => {
    const idx = GAME_KEYS.indexOf(key);
    if (idx >= 0) setActiveIndex(idx);
  };

  return (
    <SectionShell icon={<Trophy size={16} />} title={t("profile.gameHistory")}>
      <SegmentTabs
        keys={GAME_KEYS}
        active={activeGame}
        onSelect={selectGame}
        label={(key) => t(gameTitleKey(key))}
        icon={gameIcon}
      />
      <DotIndicators
        count={GAME_KEYS.length}
        activeIndex={activeIndex}
        onSelect={setActiveIndex}
        label={(i) => t(gameTitleKey(GAME_KEYS[i]!))}
      />

      <div
        ref={scrollerRef}
        onScroll={onScroll}
        className="flex snap-x snap-mandatory gap-0 overflow-x-auto overscroll-x-contain scroll-smooth [-ms-overflow-style:none] [-webkit-overflow-scrolling:touch] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        role="region"
        aria-label={t("profile.gameHistory")}
      >
        {GAME_KEYS.map((key) => {
          const isActive = key === activeGame;
          return (
            <div key={key} className="w-full shrink-0 snap-center px-0.5" role="tabpanel">
              {!isActive ? (
                <div className="min-h-[8rem]" aria-hidden />
              ) : error ? (
                <p className="rounded-2xl bg-red-50 px-4 py-3 text-center text-sm text-red-500 dark:bg-red-500/10">
                  {t("profile.historyError")}
                </p>
              ) : loading ? (
                <SoftLoader />
              ) : items.length === 0 ? (
                <EmptyState message={t(gameEmptyKey(key))} />
              ) : (
                <ul className="flex flex-col gap-2">
                  {items.map((item) => renderGameItem(key, item, t, formatDate))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      <PageControls
        offset={offset}
        count={items.length}
        total={total}
        loading={loading}
        onPrev={() =>
          setOffsets((prev) => ({
            ...prev,
            [activeGame]: Math.max(0, (prev[activeGame] ?? 0) - PAGE_SIZE),
          }))
        }
        onNext={() =>
          setOffsets((prev) => ({
            ...prev,
            [activeGame]: (prev[activeGame] ?? 0) + PAGE_SIZE,
          }))
        }
        t={t}
      />
    </SectionShell>
  );
}

function PaymentsCarousel({ t, formatDate }: { t: Translate; formatDate: FormatDate }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [offsets, setOffsets] = useState<Record<ProfilePaymentType, number>>({
    deposit: 0,
    withdraw: 0,
  });
  const [items, setItems] = useState<ProfilePaymentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const activeType = PAYMENT_TYPES[activeIndex] ?? "deposit";
  const offset = offsets[activeType] ?? 0;
  const { scrollerRef, onScroll } = useSnapIndex(PAYMENT_TYPES.length, activeIndex, setActiveIndex);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(false);

    getMyPayments(activeType, PAGE_SIZE, offset, controller.signal)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items ?? []);
        setTotal(page.total ?? 0);
      })
      .catch((err: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        const name = (err as { name?: string })?.name;
        const code = (err as { code?: string })?.code;
        if (name === "CanceledError" || name === "AbortError" || code === "ERR_CANCELED") {
          return;
        }
        setError(true);
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled && !controller.signal.aborted) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeType, offset]);

  const selectType = (type: ProfilePaymentType) => {
    const idx = PAYMENT_TYPES.indexOf(type);
    if (idx >= 0) setActiveIndex(idx);
  };

  const typeLabel = (type: ProfilePaymentType) =>
    type === "deposit" ? t("profile.myDeposits") : t("profile.myWithdrawals");

  const typeIcon = (type: ProfilePaymentType) =>
    type === "deposit" ? <ArrowDownLeft size={13} /> : <ArrowUpRight size={13} />;

  return (
    <SectionShell icon={<Wallet size={16} />} title={t("profile.payments")}>
      <SegmentTabs
        keys={PAYMENT_TYPES}
        active={activeType}
        onSelect={selectType}
        label={typeLabel}
        icon={typeIcon}
      />
      <DotIndicators
        count={PAYMENT_TYPES.length}
        activeIndex={activeIndex}
        onSelect={setActiveIndex}
        label={(i) => typeLabel(PAYMENT_TYPES[i]!)}
      />

      <div
        ref={scrollerRef}
        onScroll={onScroll}
        className="flex snap-x snap-mandatory gap-0 overflow-x-auto overscroll-x-contain scroll-smooth [-ms-overflow-style:none] [-webkit-overflow-scrolling:touch] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        role="region"
        aria-label={t("profile.payments")}
      >
        {PAYMENT_TYPES.map((type) => {
          const isActive = type === activeType;
          return (
            <div key={type} className="w-full shrink-0 snap-center px-0.5" role="tabpanel">
              {!isActive ? (
                <div className="min-h-[8rem]" aria-hidden />
              ) : error ? (
                <p className="rounded-2xl bg-red-50 px-4 py-3 text-center text-sm text-red-500 dark:bg-red-500/10">
                  {t("profile.historyError")}
                </p>
              ) : loading ? (
                <SoftLoader />
              ) : items.length === 0 ? (
                <EmptyState
                  message={
                    type === "deposit" ? t("profile.noDeposits") : t("profile.noWithdrawals")
                  }
                />
              ) : (
                <ul className="flex flex-col gap-2">
                  {items.map((item) => (
                    <PaymentRow
                      key={item.id}
                      item={item}
                      kind={type}
                      t={t}
                      formatDate={formatDate}
                    />
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      <PageControls
        offset={offset}
        count={items.length}
        total={total}
        loading={loading}
        onPrev={() =>
          setOffsets((prev) => ({
            ...prev,
            [activeType]: Math.max(0, (prev[activeType] ?? 0) - PAGE_SIZE),
          }))
        }
        onNext={() =>
          setOffsets((prev) => ({
            ...prev,
            [activeType]: (prev[activeType] ?? 0) + PAGE_SIZE,
          }))
        }
        t={t}
      />
    </SectionShell>
  );
}

export function ProfileHub({ firstName, balance, boardPrice }: ProfileHubProps) {
  const { t, formatDate } = useI18n();
  const initial = (firstName.trim()[0] || "P").toUpperCase();

  return (
    <div className="flex flex-col gap-4 px-4 py-5 animate-[fadeIn_0.3s_ease-out]">
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#4C1D95] via-[#6D28D9] to-[#7C3AED] p-5 text-white shadow-lg">
        <div className="pointer-events-none absolute -right-6 -top-6 h-28 w-28 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -bottom-8 left-10 h-24 w-24 rounded-full bg-pink-400/20" />

        <div className="relative flex items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/20 text-2xl font-black backdrop-blur-sm ring-1 ring-white/30">
            {initial}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wider text-white/70">
              {t("profile.title")}
            </p>
            <h1 className="truncate text-xl font-black">{firstName}</h1>
          </div>
        </div>
      </div>

      <SectionShell icon={<Wallet size={16} />} title={t("common.wallet")}>
        <p className="text-3xl font-black tabular-nums text-purple-950 dark:text-white">
          {formatBalance(balance)}
          <span className="ml-1.5 text-base font-bold text-purple-400">{t("common.etb")}</span>
        </p>
        <p className="mt-1 text-xs text-purple-500 dark:text-purple-300">
          {t("profile.walletHint", { price: boardPrice })}
        </p>
      </SectionShell>

      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <ThemePreference />
      </section>

      <section className="rounded-3xl bg-white/90 p-4 shadow-sm ring-1 ring-purple-100/80 dark:bg-[#1E1B2E] dark:ring-white/10">
        <LanguagePreference />
      </section>

      <GameHistoryCarousel t={t} formatDate={formatDate} />
      <PaymentsCarousel t={t} formatDate={formatDate} />
    </div>
  );
}
