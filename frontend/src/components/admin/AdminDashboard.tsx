import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import {
  ChevronLeft, ChevronRight, Loader2, RefreshCw, Search, ShieldCheck, X,
} from "lucide-react";
import axios from "axios";
import { useI18n } from "../../i18n";
import {
  ADMIN_PAGE_SIZE,
  addAdmin, adjustBalance, createPaymentAccount, decideWithdrawal, deleteAdminUser,
  deleteAllAdminUsers, deletePaymentAccount, getAdminMe, getAudit, getBingoBot,
  getDashboard, getDeposits, getGamePlayers, getLottoBot, getUserDetail, getUsers,
  getWithdrawals, listAdmins, listPaymentAccounts, previewDataRetention, purgeDataRetention,
  removeAdmin, sendAdminBroadcast, setBingoBot, setLottoBot, updatePaymentAccount,
  type AdminMe, type AdminUser, type AuditItem, type BingoBotStatus, type BroadcastResult,
  type Dashboard, type LottoBotStatus, type ManagedAdmin, type Payment, type PaymentAccount,
  type PaymentAccountKind, type RetentionOption, type RetentionPreview,
} from "../../services/admin";

type Section =
  | "overview"
  | "users"
  | "deposits"
  | "withdrawals"
  | "accounts"
  | "games"
  | "messages"
  | "admins"
  | "audit"
  | "maintenance";
type Range = "today" | "7d" | "30d" | "all";
const BASE_SECTIONS: Section[] = [
  "overview", "users", "deposits", "withdrawals", "accounts", "games", "messages", "admins", "audit",
];
const GAMES = ["bingo", "dama", "aviator", "plinko", "lotto"];
const BROADCAST_GAMES = ["", "lotto", "bingo", "dama", "aviator", "plinko"];
const RETENTION_OPTIONS: RetentionOption[] = [
  "all", "games_only", "7d", "14d", "21d", "30d", "60d", "90d", "120d", "150d",
];
const SEARCH_DEBOUNCE_MS = 350;

const defaultCaps = (): Pick<
  AdminMe,
  "is_admin" | "is_super" | "can_maintenance" | "can_adjust_balance" | "can_manage_admins"
> => ({
  is_admin: true,
  is_super: false,
  can_maintenance: false,
  can_adjust_balance: false,
  can_manage_admins: false,
});

const fromDate = (range: Range): string | undefined => {
  if (range === "all") return "2020-01-01T00:00:00Z";
  const date = new Date();
  if (range === "today") date.setHours(0, 0, 0, 0);
  else date.setDate(date.getDate() - Number.parseInt(range, 10));
  return date.toISOString();
};

const money = (value: string | number | undefined) =>
  `${Number(value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ETB`;

const shortTime = (value: string | Date | undefined) => {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
};

function StatusChip({ status }: { status: string }) {
  const tone = status.toUpperCase();
  const styles =
    tone === "PENDING" ? "bg-amber-500/15 text-amber-700 dark:text-amber-300" :
    tone === "APPROVED" || tone === "COMPLETED" ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" :
    tone === "REJECTED" || tone === "CANCELLED" ? "bg-rose-500/15 text-rose-700 dark:text-rose-300" :
    "bg-slate-500/10 text-slate-600 dark:text-slate-300";
  return (
    <span className={`inline-flex max-w-full truncate rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${styles}`}>
      {status}
    </span>
  );
}

function Empty({ text, onRetry, retryLabel }: { text: string; onRetry?: () => void; retryLabel?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300/80 bg-white/60 px-4 py-8 text-center dark:border-white/15 dark:bg-white/[0.03]">
      <p className="text-sm leading-relaxed text-slate-500 dark:text-slate-400">{text}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-3 text-sm font-semibold text-sky-700 underline dark:text-sky-300">
          {retryLabel}
        </button>
      )}
    </div>
  );
}

function Kpi({ title, value, accent }: { title: string; value: string; accent?: string }) {
  return (
    <article className="min-w-0 rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
      <div className={`mb-2 h-0.5 w-8 rounded-full ${accent ?? "bg-slate-400"}`} />
      <p className="text-[11px] font-medium leading-snug text-slate-500 dark:text-slate-400">{title}</p>
      <p className="mt-1 break-words text-base font-semibold leading-tight text-slate-900 dark:text-slate-50 sm:text-lg">{value}</p>
    </article>
  );
}

const LIABILITIES_INCLUDE_BOTS_KEY = "admin.liabilities.includeBots";

function LiabilitiesKpi({ dashboard }: { dashboard: Dashboard }) {
  const { t } = useI18n();
  const [includeBots, setIncludeBots] = useState(() => {
    try {
      return window.localStorage.getItem(LIABILITIES_INCLUDE_BOTS_KEY) === "1";
    } catch {
      return false;
    }
  });

  const withoutBots =
    dashboard.wallet_liabilities_without_bots ?? dashboard.wallet_liabilities;
  const withBots =
    dashboard.wallet_liabilities_with_bots ?? dashboard.wallet_liabilities;
  const value = includeBots ? withBots : withoutBots;

  const setMode = (next: boolean) => {
    setIncludeBots(next);
    try {
      window.localStorage.setItem(LIABILITIES_INCLUDE_BOTS_KEY, next ? "1" : "0");
    } catch {
      /* ignore quota / private mode */
    }
  };

  return (
    <article className="col-span-2 min-w-0 rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820] sm:col-span-1">
      <div className="mb-2 h-0.5 w-8 rounded-full bg-indigo-500" />
      <p className="text-[11px] font-medium leading-snug text-slate-500 dark:text-slate-400">
        {t("admin.liabilities")}
      </p>
      <p className="mt-1 break-words text-base font-semibold leading-tight text-slate-900 dark:text-slate-50 sm:text-lg">
        {money(value)}
      </p>
      <div
        className="mt-2 flex rounded-lg bg-slate-100 p-0.5 dark:bg-white/10"
        role="group"
        aria-label={t("admin.liabilities")}
      >
        <button
          type="button"
          onClick={() => setMode(false)}
          className={`min-w-0 flex-1 rounded-md px-2 py-1.5 text-[10px] font-semibold leading-tight transition ${
            !includeBots
              ? "bg-white text-slate-900 shadow-sm dark:bg-[#1c222c] dark:text-slate-50"
              : "text-slate-500 dark:text-slate-400"
          }`}
        >
          {t("admin.liabilitiesWithoutBots")}
        </button>
        <button
          type="button"
          onClick={() => setMode(true)}
          className={`min-w-0 flex-1 rounded-md px-2 py-1.5 text-[10px] font-semibold leading-tight transition ${
            includeBots
              ? "bg-white text-slate-900 shadow-sm dark:bg-[#1c222c] dark:text-slate-50"
              : "text-slate-500 dark:text-slate-400"
          }`}
        >
          {t("admin.liabilitiesWithBots")}
        </button>
      </div>
      <p className="mt-1.5 text-[10px] leading-snug text-slate-400 dark:text-slate-500">
        {t("admin.liabilitiesHint")}
      </p>
    </article>
  );
}

function Pager({
  offset, total, pageSize, onPrev, onNext, recordsLabel,
}: {
  offset: number;
  total: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
  recordsLabel: string;
}) {
  if (total <= 0) return null;
  return (
    <div className="flex items-center justify-between gap-2">
      <button
        type="button"
        disabled={!offset}
        onClick={onPrev}
        className="rounded-lg border border-slate-200 p-2 disabled:opacity-40 dark:border-white/10"
      >
        <ChevronLeft size={16} />
      </button>
      <span className="text-center text-[11px] text-slate-500">
        {offset + 1}–{Math.min(total, offset + pageSize)} / {total} {recordsLabel}
      </span>
      <button
        type="button"
        disabled={offset + pageSize >= total}
        onClick={onNext}
        className="rounded-lg border border-slate-200 p-2 disabled:opacity-40 dark:border-white/10"
      >
        <ChevronRight size={16} />
      </button>
    </div>
  );
}

function RangeStepper({
  label,
  value,
  min,
  max,
  busy,
  onCommit,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  busy: boolean;
  onCommit: (next: number) => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);

  const commit = (next: number) => {
    const clamped = Math.max(min, Math.min(max, next));
    setDraft(clamped);
    if (clamped !== value) onCommit(clamped);
  };

  return (
    <label className="block min-w-0 flex-1 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
      {label}
      <div className="mt-1 flex items-center gap-1.5">
        <button
          type="button"
          disabled={busy || draft <= min}
          onClick={() => commit(draft - 1)}
          className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm disabled:opacity-40 dark:border-white/10"
        >
          −
        </button>
        <input
          type="number"
          min={min}
          max={max}
          value={draft}
          disabled={busy}
          onChange={(e) => {
            const raw = Number.parseInt(e.target.value, 10);
            if (Number.isNaN(raw)) return;
            setDraft(Math.max(min, Math.min(max, raw)));
          }}
          onBlur={() => commit(draft)}
          className="w-full rounded-xl border border-slate-200 bg-transparent p-2 text-center text-sm dark:border-white/10"
        />
        <button
          type="button"
          disabled={busy || draft >= max}
          onClick={() => commit(draft + 1)}
          className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm disabled:opacity-40 dark:border-white/10"
        >
          +
        </button>
      </div>
    </label>
  );
}

function BingoBotControl({
  status,
  busy,
  onToggle,
  onReserveRange,
}: {
  status: BingoBotStatus | null;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onReserveRange: (min: number, max: number) => void;
}) {
  const { t } = useI18n();

  if (!status) {
    return (
      <section className="flex items-center justify-center rounded-xl border border-slate-200/90 bg-white p-4 dark:border-white/10 dark:bg-[#141820]">
        <Loader2 className="animate-spin text-sky-600" size={18} aria-label="Loading" />
      </section>
    );
  }

  const statusKey = `admin.bingoBotStatus.${status.status}` as const;
  const sourceKey = `admin.bingoBotSource.${status.source}` as const;
  const allowedMin = status.allowed_min ?? 0;
  const allowedMax = status.allowed_max ?? 50;

  return (
    <section className="rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{t("admin.bingoBot")}</h2>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
            {t("admin.bingoBotHint")}
          </p>
        </div>
        {busy && <Loader2 className="mt-0.5 shrink-0 animate-spin text-sky-600" size={16} aria-hidden />}
      </div>
      <div className="mt-3 flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-white/[0.06]">
        <button
          type="button"
          disabled={busy || status.enabled}
          onClick={() => onToggle(true)}
          className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold transition ${
            status.enabled
              ? "bg-emerald-600 text-white shadow-sm"
              : "text-slate-600 hover:bg-white/70 dark:text-slate-300 dark:hover:bg-white/10"
          } disabled:opacity-60`}
        >
          {t("admin.bingoBotActive")}
        </button>
        <button
          type="button"
          disabled={busy || !status.enabled}
          onClick={() => onToggle(false)}
          className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold transition ${
            !status.enabled
              ? "bg-slate-700 text-white shadow-sm dark:bg-slate-600"
              : "text-slate-600 hover:bg-white/70 dark:text-slate-300 dark:hover:bg-white/10"
          } disabled:opacity-60`}
        >
          {t("admin.bingoBotInactive")}
        </button>
      </div>
      <p className="mt-3 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
        {t("admin.bingoBotReserveRange")}
      </p>
      <div className="mt-1 flex items-end gap-2">
        <RangeStepper
          label={t("admin.bingoBotReserveFrom")}
          value={status.reserve_min}
          min={allowedMin}
          max={status.reserve_max}
          busy={busy}
          onCommit={(next) => onReserveRange(next, status.reserve_max)}
        />
        <span className="mb-2 text-xs text-slate-400">–</span>
        <RangeStepper
          label={t("admin.bingoBotReserveTo")}
          value={status.reserve_max}
          min={status.reserve_min}
          max={allowedMax}
          busy={busy}
          onCommit={(next) => onReserveRange(status.reserve_min, next)}
        />
      </div>
      <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
        {t("admin.bingoBotReserveHint", { min: allowedMin, max: allowedMax })}
      </p>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
        <span>{t(statusKey as any)}</span>
        <span>{t("admin.bingoBotBoards")}: {status.boards_held}</span>
        <span>{t(sourceKey as any)}</span>
      </div>
    </section>
  );
}

function LottoBotControl({
  status,
  busy,
  onToggle,
  onReserveRange,
}: {
  status: LottoBotStatus | null;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onReserveRange: (min: number, max: number) => void;
}) {
  const { t } = useI18n();

  if (!status) {
    return (
      <section className="flex items-center justify-center rounded-xl border border-slate-200/90 bg-white p-4 dark:border-white/10 dark:bg-[#141820]">
        <Loader2 className="animate-spin text-sky-600" size={18} aria-label="Loading" />
      </section>
    );
  }

  const statusKey = `admin.lottoBotStatus.${status.status}` as const;
  const sourceKey = `admin.lottoBotSource.${status.source}` as const;
  const allowedMin = status.allowed_min ?? 1;
  const allowedMax = status.allowed_max ?? 25;

  return (
    <section className="rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{t("admin.lottoBot")}</h2>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
            {t("admin.lottoBotHint")}
          </p>
        </div>
        {busy && <Loader2 className="mt-0.5 shrink-0 animate-spin text-sky-600" size={16} aria-hidden />}
      </div>
      <div className="mt-3 flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-white/[0.06]">
        <button
          type="button"
          disabled={busy || status.enabled}
          onClick={() => onToggle(true)}
          className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold transition ${
            status.enabled
              ? "bg-emerald-600 text-white shadow-sm"
              : "text-slate-600 hover:bg-white/70 dark:text-slate-300 dark:hover:bg-white/10"
          } disabled:opacity-60`}
        >
          {t("admin.lottoBotActive")}
        </button>
        <button
          type="button"
          disabled={busy || !status.enabled}
          onClick={() => onToggle(false)}
          className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold transition ${
            !status.enabled
              ? "bg-slate-700 text-white shadow-sm dark:bg-slate-600"
              : "text-slate-600 hover:bg-white/70 dark:text-slate-300 dark:hover:bg-white/10"
          } disabled:opacity-60`}
        >
          {t("admin.lottoBotInactive")}
        </button>
      </div>
      <p className="mt-3 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
        {t("admin.lottoBotReserveRange")}
      </p>
      <div className="mt-1 flex items-end gap-2">
        <RangeStepper
          label={t("admin.lottoBotReserveFrom")}
          value={status.reserve_min}
          min={allowedMin}
          max={status.reserve_max}
          busy={busy}
          onCommit={(next) => onReserveRange(next, status.reserve_max)}
        />
        <span className="mb-2 text-xs text-slate-400">–</span>
        <RangeStepper
          label={t("admin.lottoBotReserveTo")}
          value={status.reserve_max}
          min={status.reserve_min}
          max={allowedMax}
          busy={busy}
          onCommit={(next) => onReserveRange(status.reserve_min, next)}
        />
      </div>
      <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
        {t("admin.lottoBotReserveHint", {
          min: allowedMin,
          max: allowedMax,
          threshold: status.real_player_threshold ?? 15,
        })}
      </p>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
        <span>{t(statusKey as any)}</span>
        <span>{t("admin.lottoBotNumbers")}: {status.numbers_held}</span>
        <span>{t(sourceKey as any)}</span>
      </div>
    </section>
  );
}

export function AdminDashboard({ onAccessDenied }: { onAccessDenied: () => void }) {
  const { t } = useI18n();
  const [caps, setCaps] = useState(defaultCaps);
  const [section, setSection] = useState<Section>("overview");
  const [range, setRange] = useState<Range>("7d");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [userTotal, setUserTotal] = useState(0);
  const [userOffset, setUserOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [userFilter, setUserFilter] = useState<"all" | "active" | "bot">("all");
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const [adjusting, setAdjusting] = useState<AdminUser | null>(null);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [depositStatus, setDepositStatus] = useState("all");
  const [withdrawStatus, setWithdrawStatus] = useState("pending");
  const [payments, setPayments] = useState<Payment[]>([]);
  const [paymentTotal, setPaymentTotal] = useState(0);
  const [paymentOffset, setPaymentOffset] = useState(0);
  const [paymentWorkflow, setPaymentWorkflow] = useState("");
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditOffset, setAuditOffset] = useState(0);
  const [game, setGame] = useState("bingo");
  const [players, setPlayers] = useState<any[]>([]);
  const [playerTotal, setPlayerTotal] = useState(0);
  const [playerOffset, setPlayerOffset] = useState(0);
  const [bingoBot, setBingoBotState] = useState<BingoBotStatus | null>(null);
  const [bingoBotBusy, setBingoBotBusy] = useState(false);
  const [lottoBot, setLottoBotState] = useState<LottoBotStatus | null>(null);
  const [lottoBotBusy, setLottoBotBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [retentionOption, setRetentionOption] = useState<RetentionOption>("30d");
  const [retentionPreview, setRetentionPreview] = useState<RetentionPreview | null>(null);
  const [retentionConfirm, setRetentionConfirm] = useState("");
  const [retentionReason, setRetentionReason] = useState("");
  const [retentionMessage, setRetentionMessage] = useState("");
  const [deleteQuery, setDeleteQuery] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteReason, setDeleteReason] = useState("");
  const [deleteForce, setDeleteForce] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState("");
  const [deleteAllConfirm, setDeleteAllConfirm] = useState("");
  const [deleteAllReason, setDeleteAllReason] = useState("");
  const [deleteAllForce, setDeleteAllForce] = useState(false);
  const [deleteAllMessage, setDeleteAllMessage] = useState("");
  const [broadcastMessage, setBroadcastMessage] = useState("");
  const [broadcastGame, setBroadcastGame] = useState("");
  const [broadcastUrl, setBroadcastUrl] = useState("");
  const [broadcastLabel, setBroadcastLabel] = useState("");
  const [broadcastResult, setBroadcastResult] = useState<BroadcastResult | null>(null);
  const [broadcastBusy, setBroadcastBusy] = useState(false);
  const [admins, setAdmins] = useState<ManagedAdmin[]>([]);
  const [newAdminUsername, setNewAdminUsername] = useState("");
  const [adminsMessage, setAdminsMessage] = useState("");
  const [paymentAccounts, setPaymentAccounts] = useState<PaymentAccount[]>([]);
  const [accountKindFilter, setAccountKindFilter] = useState<PaymentAccountKind | "all">("deposit");
  const [withdrawHouseAccounts, setWithdrawHouseAccounts] = useState<PaymentAccount[]>([]);
  const [accountForm, setAccountForm] = useState({
    bank: "",
    account_name: "",
    account_number: "",
    kind: "deposit" as PaymentAccountKind,
  });
  const [editingAccount, setEditingAccount] = useState<PaymentAccount | null>(null);
  const [accountsMessage, setAccountsMessage] = useState("");
  /** Bumps on every section enter so lists refetch on navigation (not only on filter change). */
  const [sectionVisit, setSectionVisit] = useState(0);
  const sectionLoadedRef = useRef<Partial<Record<Section, boolean>>>({});
  const tabRefs = useRef<Partial<Record<Section, HTMLButtonElement | null>>>({});

  const sections = useMemo(() => {
    const items = [...BASE_SECTIONS];
    if (caps.can_maintenance) items.push("maintenance");
    return items;
  }, [caps.can_maintenance]);

  const fail = useEffectEvent((caught: unknown) => {
    if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
      onAccessDenied();
      return;
    }
    setError(t("admin.error"));
  });

  useEffect(() => {
    let cancelled = false;
    getAdminMe()
      .then((me) => {
        if (cancelled) return;
        setCaps({
          is_admin: me.is_admin,
          is_super: me.is_super,
          can_maintenance: me.can_maintenance,
          can_adjust_balance: me.can_adjust_balance,
          can_manage_admins: me.can_manage_admins,
        });
        if (!me.is_admin) onAccessDenied();
      })
      .catch((caught) => {
        if (!cancelled) fail(caught);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (section === "maintenance" && !caps.can_maintenance) {
      setSection("overview");
    }
  }, [section, caps.can_maintenance]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    tabRefs.current[section]?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, [section]);

  // Section-scoped load key: changing unrelated filters must not refetch other sections.
  const loadKey = useMemo(() => {
    switch (section) {
      case "overview":
        return `overview|${range}|${refresh}|${sectionVisit}`;
      case "users":
        return `users|${debouncedSearch}|${userFilter}|${userOffset}|${refresh}|${sectionVisit}`;
      case "deposits":
        return `deposits|${depositStatus}|${paymentOffset}|${refresh}|${sectionVisit}`;
      case "withdrawals":
        return `withdrawals|${withdrawStatus}|${paymentOffset}|${refresh}|${sectionVisit}`;
      case "accounts":
        return `accounts|${accountKindFilter}|${refresh}|${sectionVisit}`;
      case "games":
        return `games|${game}|${range}|${playerOffset}|${refresh}|${sectionVisit}`;
      case "messages":
        return `messages|${refresh}|${sectionVisit}`;
      case "admins":
        return `admins|${refresh}|${sectionVisit}`;
      case "audit":
        return `audit|${auditOffset}|${refresh}|${sectionVisit}`;
      case "maintenance":
        return `maintenance|${retentionOption}|${refresh}|${sectionVisit}`;
      default:
        return `${section}|${refresh}|${sectionVisit}`;
    }
  }, [
    section, range, refresh, sectionVisit, debouncedSearch, userFilter, userOffset,
    depositStatus, withdrawStatus, paymentOffset, accountKindFilter, game, playerOffset,
    auditOffset, retentionOption,
  ]);

  useEffect(() => {
    let cancelled = false;
    const soft = !!sectionLoadedRef.current[section];
    if (soft) setRefreshing(true);
    else setLoading(true);
    setError("");

    const load = async () => {
      try {
        const from = fromDate(range);
        if (section === "overview") {
          const data = await getDashboard(from);
          if (cancelled) return;
          setDashboard(data);
          const [bingo, lotto] = await Promise.all([getBingoBot(), getLottoBot()]);
          if (cancelled) return;
          setBingoBotState(bingo);
          setLottoBotState(lotto);
        } else if (section === "users") {
          const data = await getUsers({
            search: debouncedSearch || undefined,
            status: userFilter === "all" ? undefined : userFilter,
            offset: userOffset,
            limit: ADMIN_PAGE_SIZE,
            sort: "joined_desc",
          });
          if (cancelled) return;
          setUsers(data.items);
          setUserTotal(data.total);
        } else if (section === "deposits") {
          const data = await getDeposits({
            status: depositStatus,
            limit: ADMIN_PAGE_SIZE,
            offset: paymentOffset,
          });
          if (cancelled) return;
          setPayments(data.items);
          setPaymentTotal(data.total);
          setPaymentWorkflow(data.workflow || "");
        } else if (section === "withdrawals") {
          const [data, house] = await Promise.all([
            getWithdrawals({
              status: withdrawStatus,
              limit: ADMIN_PAGE_SIZE,
              offset: paymentOffset,
            }),
            listPaymentAccounts("withdraw"),
          ]);
          if (cancelled) return;
          setPayments(data.items);
          setPaymentTotal(data.total);
          setPaymentWorkflow("");
          setWithdrawHouseAccounts(house.items.filter((row) => row.is_enabled));
        } else if (section === "accounts") {
          const data = await listPaymentAccounts(
            accountKindFilter === "all" ? undefined : accountKindFilter,
          );
          if (cancelled) return;
          setPaymentAccounts(data.items);
        } else if (section === "games") {
          const data = await getGamePlayers(game, {
            from,
            limit: ADMIN_PAGE_SIZE,
            offset: playerOffset,
          });
          if (cancelled) return;
          setPlayers(data.items);
          setPlayerTotal(data.total);
          if (game === "bingo") {
            const bot = await getBingoBot();
            if (cancelled) return;
            setBingoBotState(bot);
          } else if (game === "lotto") {
            const bot = await getLottoBot();
            if (cancelled) return;
            setLottoBotState(bot);
          }
        } else if (section === "messages") {
          // Composer is client-side only; no list fetch.
        } else if (section === "admins") {
          const data = await listAdmins();
          if (cancelled) return;
          setAdmins(data.items);
        } else if (section === "audit") {
          const data = await getAudit({ limit: ADMIN_PAGE_SIZE, offset: auditOffset });
          if (cancelled) return;
          setAudit(data.items);
          setAuditTotal(data.total);
        } else if (section === "maintenance") {
          if (!caps.can_maintenance) return;
          setRetentionMessage("");
          const data = await previewDataRetention(retentionOption);
          if (cancelled) return;
          setRetentionPreview(data);
          setRetentionConfirm("");
        }
        sectionLoadedRef.current[section] = true;
        setUpdatedAt(new Date());
      } catch (caught) {
        if (!cancelled) fail(caught);
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [loadKey]);

  const maxGgr = useMemo(
    () => Math.max(1, ...(dashboard?.games.map((item) => Math.abs(Number(item.ggr))) ?? [1])),
    [dashboard],
  );

  const pendingWithdrawals = dashboard?.action_queue?.pending_withdrawals?.count
    ?? dashboard?.withdrawals.pending?.count
    ?? 0;
  const pendingWithdrawalAmount = dashboard?.action_queue?.pending_withdrawals?.amount
    ?? dashboard?.withdrawals.pending?.amount;
  const rangePendingWithdrawals = dashboard?.withdrawals.pending?.count ?? 0;
  const pendingDepositCount = dashboard?.deposits.pending_count ?? 0;

  const goSection = (next: Section, opts?: { withdrawStatus?: string; depositStatus?: string }) => {
    if (opts?.withdrawStatus) {
      setWithdrawStatus(opts.withdrawStatus);
      setPaymentOffset(0);
    }
    if (opts?.depositStatus) {
      setDepositStatus(opts.depositStatus);
      setPaymentOffset(0);
    }
    if (next !== section) {
      setSectionVisit((value) => value + 1);
      if (next === "users") setUserOffset(0);
      if (next === "deposits" || next === "withdrawals") setPaymentOffset(0);
      if (next === "games") setPlayerOffset(0);
      if (next === "audit") setAuditOffset(0);
    }
    setSection(next);
    setError("");
  };

  const submitAdjustment = async () => {
    if (!caps.can_adjust_balance || !adjusting || !amount || reason.trim().length < 3) return;
    setPendingAction(adjusting.id);
    try {
      await adjustBalance(adjusting.id, amount, reason.trim(), crypto.randomUUID());
      setAdjusting(null); setAmount(""); setReason(""); setRefresh((value) => value + 1);
    } catch (caught) { fail(caught); }
    finally { setPendingAction(null); }
  };

  const submitBroadcast = async () => {
    if (!broadcastMessage.trim() || broadcastBusy) return;
    if (!window.confirm(t("admin.broadcastConfirm"))) return;
    setBroadcastBusy(true);
    setBroadcastResult(null);
    try {
      const result = await sendAdminBroadcast({
        message: broadcastMessage.trim(),
        buttonUrl: broadcastUrl.trim() || undefined,
        buttonLabel: broadcastLabel.trim() || undefined,
        game: broadcastGame || undefined,
        requestId: crypto.randomUUID(),
      });
      setBroadcastResult(result);
    } catch (caught) {
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      setError(t("admin.broadcastError"));
    } finally {
      setBroadcastBusy(false);
    }
  };

  const submitAddAdmin = async () => {
    if (!caps.can_manage_admins || !newAdminUsername.trim()) return;
    setPendingAction("add-admin");
    setAdminsMessage("");
    try {
      await addAdmin(newAdminUsername.trim(), crypto.randomUUID());
      setNewAdminUsername("");
      setAdminsMessage(t("admin.adminsAddSuccess"));
      setRefresh((value) => value + 1);
    } catch (caught) {
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      setAdminsMessage(t("admin.adminsAddError"));
    } finally {
      setPendingAction(null);
    }
  };

  const submitRemoveAdmin = async (username: string) => {
    if (!caps.can_manage_admins) return;
    if (!window.confirm(t("admin.adminsRemoveConfirm", { username }))) return;
    setPendingAction(`remove-${username}`);
    setAdminsMessage("");
    try {
      await removeAdmin(username, crypto.randomUUID());
      setAdminsMessage(t("admin.adminsRemoveSuccess", { username }));
      setRefresh((value) => value + 1);
    } catch (caught) {
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      setAdminsMessage(t("admin.adminsRemoveError"));
    } finally {
      setPendingAction(null);
    }
  };

  const toggleBingoBot = async (enabled: boolean) => {
    if (bingoBotBusy || (bingoBot && bingoBot.enabled === enabled)) return;
    const previous = bingoBot;
    setBingoBotBusy(true);
    setBingoBotState((current) =>
      current ? { ...current, enabled, status: enabled ? "active" : "inactive" } : current
    );
    try {
      const next = await setBingoBot({ enabled }, crypto.randomUUID());
      setBingoBotState(next);
    } catch (caught) {
      setBingoBotState(previous);
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      setError(t("admin.bingoBotToggleError"));
    } finally {
      setBingoBotBusy(false);
    }
  };

  const updateBingoBotReserve = async (reserveMin: number, reserveMax: number) => {
    if (
      bingoBotBusy
      || (bingoBot
        && bingoBot.reserve_min === reserveMin
        && bingoBot.reserve_max === reserveMax)
    ) return;
    const previous = bingoBot;
    setBingoBotBusy(true);
    setBingoBotState((current) =>
      current ? { ...current, reserve_min: reserveMin, reserve_max: reserveMax } : current
    );
    try {
      const next = await setBingoBot(
        { reserve_min: reserveMin, reserve_max: reserveMax },
        crypto.randomUUID(),
      );
      setBingoBotState(next);
    } catch (caught) {
      setBingoBotState(previous);
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      setError(t("admin.bingoBotToggleError"));
    } finally {
      setBingoBotBusy(false);
    }
  };

  const toggleLottoBot = async (enabled: boolean) => {
    if (lottoBotBusy || (lottoBot && lottoBot.enabled === enabled)) return;
    const previous = lottoBot;
    setLottoBotBusy(true);
    setLottoBotState((current) =>
      current ? { ...current, enabled, status: enabled ? "active" : "inactive" } : current
    );
    try {
      const next = await setLottoBot({ enabled }, crypto.randomUUID());
      setLottoBotState(next);
    } catch (caught) {
      setLottoBotState(previous);
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      setError(t("admin.lottoBotToggleError"));
    } finally {
      setLottoBotBusy(false);
    }
  };

  const updateLottoBotReserve = async (reserveMin: number, reserveMax: number) => {
    if (
      lottoBotBusy
      || (lottoBot
        && lottoBot.reserve_min === reserveMin
        && lottoBot.reserve_max === reserveMax)
    ) return;
    const previous = lottoBot;
    setLottoBotBusy(true);
    setLottoBotState((current) =>
      current ? { ...current, reserve_min: reserveMin, reserve_max: reserveMax } : current
    );
    try {
      const next = await setLottoBot(
        { reserve_min: reserveMin, reserve_max: reserveMax },
        crypto.randomUUID(),
      );
      setLottoBotState(next);
    } catch (caught) {
      setLottoBotState(previous);
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      setError(t("admin.lottoBotToggleError"));
    } finally {
      setLottoBotBusy(false);
    }
  };

  const reviewWithdrawal = async (item: Payment, action: "approve" | "reject") => {
    const note = action === "reject" ? window.prompt(t("admin.rejectReason")) : null;
    if (action === "reject" && !note?.trim()) return;
    let paidFromAccountId: string | null = null;
    if (action === "approve" && withdrawHouseAccounts.length > 0) {
      const lines = withdrawHouseAccounts.map(
        (row, index) => `${index + 1}. ${row.bank} · ${row.account_name} · ${row.account_number}`,
      );
      const pick = window.prompt(
        `${t("admin.payoutAccountPrompt")}\n\n${lines.join("\n")}\n\n${t("admin.payoutAccountSkip")}`,
      );
      if (pick != null && pick.trim()) {
        const index = Number(pick.trim()) - 1;
        if (Number.isInteger(index) && index >= 0 && index < withdrawHouseAccounts.length) {
          paidFromAccountId = withdrawHouseAccounts[index].id;
        }
      }
    }
    if (!window.confirm(t(action === "approve" ? "admin.approveConfirm" : "admin.rejectConfirm"))) return;
    setPendingAction(item.id);
    try {
      await decideWithdrawal(
        item.id,
        action,
        note?.trim() || null,
        crypto.randomUUID(),
        paidFromAccountId,
      );
      setRefresh((value) => value + 1);
    } catch (caught) { fail(caught); }
    finally { setPendingAction(null); }
  };

  const submitAccountForm = async () => {
    if (pendingAction === "account-save") return;
    const bank = (editingAccount ? (editingAccount.bank) : accountForm.bank).trim();
    const accountName = (editingAccount ? editingAccount.account_name : accountForm.account_name).trim();
    const accountNumber = (editingAccount ? editingAccount.account_number : accountForm.account_number).trim();
    if (!bank || !accountName || !accountNumber) return;
    setPendingAction("account-save");
    setAccountsMessage("");
    try {
      if (editingAccount) {
        await updatePaymentAccount(editingAccount.id, {
          bank,
          account_name: accountName,
          account_number: accountNumber,
          requestId: crypto.randomUUID(),
        });
        setAccountsMessage(t("admin.accountsUpdated"));
        setEditingAccount(null);
      } else {
        await createPaymentAccount({
          kind: accountForm.kind,
          bank,
          account_name: accountName,
          account_number: accountNumber,
          requestId: crypto.randomUUID(),
        });
        setAccountsMessage(t("admin.accountsCreated"));
        setAccountForm({ bank: "", account_name: "", account_number: "", kind: accountForm.kind });
      }
      setRefresh((value) => value + 1);
    } catch (caught) {
      fail(caught);
      setAccountsMessage(t("admin.accountsError"));
    } finally {
      setPendingAction(null);
    }
  };

  const toggleAccountEnabled = async (row: PaymentAccount) => {
    if (pendingAction === `toggle-${row.id}`) return;
    setPendingAction(`toggle-${row.id}`);
    try {
      await updatePaymentAccount(row.id, {
        is_enabled: !row.is_enabled,
        requestId: crypto.randomUUID(),
      });
      setRefresh((value) => value + 1);
    } catch (caught) { fail(caught); }
    finally { setPendingAction(null); }
  };

  const removeAccount = async (row: PaymentAccount) => {
    if (!window.confirm(t("admin.accountsDeleteConfirm", { bank: row.bank }))) return;
    if (pendingAction === `delete-${row.id}`) return;
    setPendingAction(`delete-${row.id}`);
    try {
      await deletePaymentAccount(row.id, crypto.randomUUID());
      setAccountsMessage(t("admin.accountsDeleted"));
      setRefresh((value) => value + 1);
    } catch (caught) { fail(caught); }
    finally { setPendingAction(null); }
  };

  const submitPurge = async () => {
    if (!retentionPreview || pendingAction === "purge") return;
    const word = retentionPreview.confirmation_required;
    if (retentionConfirm.trim() !== word || retentionReason.trim().length < 3) return;
    setPendingAction("purge");
    setRetentionMessage("");
    try {
      const result = await purgeDataRetention({
        option: retentionOption,
        confirmation: retentionConfirm.trim(),
        reason: retentionReason.trim(),
        requestId: crypto.randomUUID(),
      });
      const deletedTotal = Object.values(result.deleted || {}).reduce((sum, n) => sum + n, 0);
      setRetentionMessage(
        t("admin.retentionSuccess", { count: deletedTotal, users: result.users_kept }),
      );
      setRetentionReason("");
      setRetentionConfirm("");
      const preview = await previewDataRetention(retentionOption);
      setRetentionPreview(preview);
    } catch (caught) {
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      setRetentionMessage(t("admin.retentionError"));
    } finally {
      setPendingAction(null);
    }
  };

  const submitDeleteUser = async () => {
    if (pendingAction === "delete-user") return;
    if (deleteConfirm.trim() !== "DELETE_USERS" || deleteReason.trim().length < 3 || !deleteQuery.trim()) {
      return;
    }
    setPendingAction("delete-user");
    setDeleteMessage("");
    try {
      const result = await deleteAdminUser({
        query: deleteQuery.trim(),
        confirmation: deleteConfirm.trim(),
        reason: deleteReason.trim(),
        requestId: crypto.randomUUID(),
        force: deleteForce,
      });
      const username = (result.deleted_user as { username?: string } | undefined)?.username;
      setDeleteMessage(
        t("admin.deleteUserSuccess", { user: username || deleteQuery.trim() }),
      );
      setDeleteQuery("");
      setDeleteConfirm("");
      setDeleteReason("");
      setDeleteForce(false);
    } catch (caught) {
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      const detail = axios.isAxiosError(caught)
        ? String(caught.response?.data?.detail ?? "")
        : "";
      setDeleteMessage(detail || t("admin.deleteUserError"));
    } finally {
      setPendingAction(null);
    }
  };

  const submitDeleteAllUsers = async () => {
    if (pendingAction === "delete-all-users") return;
    if (deleteAllConfirm.trim() !== "DELETE_ALL_USERS" || deleteAllReason.trim().length < 3) {
      return;
    }
    setPendingAction("delete-all-users");
    setDeleteAllMessage("");
    try {
      const result = await deleteAllAdminUsers({
        confirmation: deleteAllConfirm.trim(),
        reason: deleteAllReason.trim(),
        requestId: crypto.randomUUID(),
        force: deleteAllForce,
      });
      setDeleteAllMessage(
        t("admin.deleteAllUsersSuccess", {
          count: result.deleted_count ?? 0,
          skipped: result.skipped?.length ?? 0,
        }),
      );
      setDeleteAllConfirm("");
      setDeleteAllReason("");
      setDeleteAllForce(false);
    } catch (caught) {
      if (axios.isAxiosError(caught) && (caught.response?.status === 401 || caught.response?.status === 403)) {
        onAccessDenied();
        return;
      }
      setDeleteAllMessage(t("admin.deleteAllUsersError"));
    } finally {
      setPendingAction(null);
    }
  };

  const showInitialSpinner = loading && !sectionLoadedRef.current[section];

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[#f4f6f8] text-slate-900 dark:bg-[#0b0e13] dark:text-slate-100">
      <header className="shrink-0 border-b border-slate-200/90 bg-[#f4f6f8]/95 px-3 pb-2 pt-[max(0.5rem,env(safe-area-inset-top))] backdrop-blur dark:border-white/10 dark:bg-[#0b0e13]/95">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h1 className="flex items-center gap-1.5 text-[15px] font-semibold tracking-tight">
              <ShieldCheck size={16} className="shrink-0 text-sky-600 dark:text-sky-400" aria-hidden />
              <span className="truncate">{t("admin.title")}</span>
            </h1>
            <p className="truncate text-[11px] text-slate-500 dark:text-slate-400">{t("admin.secure")}</p>
            {updatedAt && (
              <p className="mt-0.5 text-[10px] text-slate-400">
                {t("admin.lastUpdated")}: {updatedAt.toLocaleTimeString()}
                {refreshing ? ` · ${t("common.loading")}` : ""}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() => setRefresh((v) => v + 1)}
            disabled={loading || refreshing}
            className="shrink-0 rounded-lg border border-slate-200 bg-white p-2 dark:border-white/10 dark:bg-white/[0.06] disabled:opacity-50"
            aria-label={t("common.refresh")}
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : undefined} />
          </button>
        </div>
        <nav
          className="mt-2 flex gap-1 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          aria-label={t("admin.title")}
        >
          {sections.map((item) => (
            <button
              key={item}
              ref={(node) => { tabRefs.current[item] = node; }}
              type="button"
              onClick={() => goSection(item)}
              className={`shrink-0 whitespace-nowrap rounded-lg px-3 py-1.5 text-[11px] font-semibold transition-colors ${
                section === item
                  ? "bg-slate-800 text-white dark:bg-sky-600"
                  : "bg-white text-slate-600 dark:bg-white/[0.06] dark:text-slate-300"
              }`}
            >
              {t(`admin.${item}` as any)}
            </button>
          ))}
        </nav>
      </header>

      <main className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-[max(5.5rem,calc(env(safe-area-inset-bottom)+4.75rem))] pt-3">
        {(section === "overview" || section === "games") && (
          <div className="flex flex-wrap gap-1 rounded-xl bg-slate-200/80 p-1 dark:bg-white/[0.07]">
            {(["today", "7d", "30d", "all"] as Range[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => {
                  setRange(item);
                  if (section === "games") setPlayerOffset(0);
                }}
                className={`min-w-[4.5rem] flex-1 rounded-lg px-2 py-1.5 text-[11px] font-semibold ${
                  range === item ? "bg-white text-slate-900 shadow-sm dark:bg-sky-600 dark:text-white" : "text-slate-500 dark:text-slate-300"
                }`}
              >
                {t(`admin.range.${item}` as any)}
              </button>
            ))}
          </div>
        )}

        {error && (
          <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
            {error}
            <button type="button" onClick={() => setRefresh((v) => v + 1)} className="ml-2 font-semibold underline">{t("common.retry")}</button>
          </div>
        )}

        {showInitialSpinner ? (
          <div className="flex justify-center p-10"><Loader2 className="animate-spin text-sky-600" aria-label="Loading" /></div>
        ) : (
          <div className={`space-y-3 transition-opacity ${refreshing ? "opacity-70" : ""}`}>
            {section === "overview" && dashboard && (
              <>
                {(pendingWithdrawals > 0 || pendingDepositCount > 0) && (
                  <section className="space-y-2 rounded-xl border border-amber-200/80 bg-amber-50/90 p-3 dark:border-amber-500/20 dark:bg-amber-500/10">
                    <h2 className="text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">{t("admin.actionQueue")}</h2>
                    {pendingWithdrawals > 0 && (
                      <button
                        type="button"
                        onClick={() => goSection("withdrawals", { withdrawStatus: "pending" })}
                        className="flex w-full items-center justify-between gap-2 rounded-lg bg-white/80 px-3 py-2 text-left text-sm dark:bg-black/20"
                      >
                        <span>{t("admin.pendingWithdrawals")}</span>
                        <span className="font-semibold">{pendingWithdrawals} · {money(pendingWithdrawalAmount)}</span>
                      </button>
                    )}
                    {pendingDepositCount > 0 && (
                      <button
                        type="button"
                        onClick={() => goSection("deposits", { depositStatus: "all" })}
                        className="flex w-full items-center justify-between gap-2 rounded-lg bg-white/80 px-3 py-2 text-left text-sm dark:bg-black/20"
                      >
                        <span>{t("admin.deposits")}</span>
                        <span className="font-semibold">{pendingDepositCount}</span>
                      </button>
                    )}
                  </section>
                )}

                <section className="grid grid-cols-2 gap-2">
                  <Kpi title={t("admin.users")} value={dashboard.total_users.toLocaleString()} accent="bg-sky-500" />
                  <Kpi title={t("admin.activeUsers")} value={dashboard.active_users.toLocaleString()} accent="bg-cyan-500" />
                  <LiabilitiesKpi dashboard={dashboard} />
                  <Kpi title={t("admin.deposits")} value={money(dashboard.deposits.approved_amount)} accent="bg-emerald-500" />
                  <Kpi title={t("admin.pendingWithdrawals")} value={`${rangePendingWithdrawals} · ${money(dashboard.withdrawals.pending?.amount)}`} accent="bg-amber-500" />
                  <Kpi title={t("admin.turnover")} value={money(dashboard.turnover)} accent="bg-slate-500" />
                  <Kpi title={t("admin.payouts")} value={money(dashboard.payouts)} accent="bg-rose-400" />
                  <Kpi title={t("admin.ggr")} value={money(dashboard.ggr)} accent="bg-teal-500" />
                </section>

                <section className="rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
                  <h2 className="mb-3 text-sm font-semibold">{t("admin.gamePerformance")}</h2>
                  <div className="space-y-3">
                    {dashboard.games.map((item) => (
                      <div key={item.game}>
                        <div className="flex items-baseline justify-between gap-2 text-sm">
                          <span className="min-w-0 truncate font-medium capitalize">{t(`admin.game.${item.game}` as any)}</span>
                          <span className="shrink-0 font-semibold">{money(item.ggr)}</span>
                        </div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-white/10">
                          <div
                            className={`h-full rounded-full ${Number(item.ggr) >= 0 ? "bg-emerald-500" : "bg-rose-500"}`}
                            style={{ width: `${Math.max(3, Math.abs(Number(item.ggr)) / maxGgr * 100)}%` }}
                          />
                        </div>
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
                          <span>{t("admin.turnover")}: {money(item.turnover)}</span>
                          <span>{item.unique_players} {t("common.players")}</span>
                          {item.game === "bingo" && item.explicit_system_fee != null && (
                            <span>{t("admin.ggr")}: {money(item.explicit_system_fee)}</span>
                          )}
                          {item.game === "bingo" && item.bot_pnl != null && (
                            <span>{t("admin.botPnl")}: {money(item.bot_pnl)}</span>
                          )}
                          {item.game === "bingo" && (item.bot_rounds ?? 0) > 0 && (
                            <span>{t("admin.botRoundsNote", { count: item.bot_rounds })}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <BingoBotControl
                  status={bingoBot}
                  busy={bingoBotBusy}
                  onToggle={toggleBingoBot}
                  onReserveRange={updateBingoBotReserve}
                />
                <LottoBotControl
                  status={lottoBot}
                  busy={lottoBotBusy}
                  onToggle={toggleLottoBot}
                  onReserveRange={updateLottoBotReserve}
                />
              </>
            )}

            {section === "users" && (
              <>
                <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 dark:border-white/10 dark:bg-[#141820]">
                  <Search size={16} className="shrink-0 text-slate-400" />
                  <input
                    value={search}
                    onChange={(e) => { setSearch(e.target.value); setUserOffset(0); }}
                    placeholder={t("admin.searchUsers")}
                    className="min-w-0 flex-1 bg-transparent py-2.5 text-sm outline-none"
                  />
                </label>
                <div className="flex flex-wrap gap-1">
                  {(["all", "active", "bot"] as const).map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => { setUserFilter(item); setUserOffset(0); }}
                      className={`rounded-lg px-3 py-1.5 text-[11px] font-semibold ${
                        userFilter === item ? "bg-slate-800 text-white dark:bg-sky-600" : "bg-white dark:bg-white/[0.06]"
                      }`}
                    >
                      {t(`admin.filter.${item}` as any)}
                    </button>
                  ))}
                </div>
                <div className="space-y-2">
                  {users.length ? users.map((user) => (
                    <article key={user.id} className="rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
                      <div className="flex items-start justify-between gap-2">
                        <button
                          type="button"
                          onClick={async () => {
                            try { setSelectedUser(await getUserDetail(user.id)); }
                            catch (caught) { fail(caught); }
                          }}
                          className="min-w-0 text-left"
                        >
                          <p className="truncate text-sm font-semibold">
                            @{user.username || "—"} · {user.first_name}
                            {user.is_bot ? (
                              <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-800 dark:bg-amber-500/20 dark:text-amber-200">
                                {t("admin.botBadge")}
                              </span>
                            ) : null}
                          </p>
                          <p className="truncate text-[11px] text-slate-500">{user.telegram_id} · {user.games_played} {t("admin.plays")}</p>
                        </button>
                        <span className="shrink-0 text-sm font-bold">{money(user.balance)}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                        <span className="text-[11px] text-slate-500">{shortTime(user.joined_at)}</span>
                        {caps.can_adjust_balance && (
                          <button
                            type="button"
                            onClick={() => setAdjusting(user)}
                            className="rounded-lg bg-slate-800 px-3 py-1.5 text-[11px] font-semibold text-white dark:bg-sky-600"
                          >
                            {t("admin.adjustBalance")}
                          </button>
                        )}
                      </div>
                    </article>
                  )) : <Empty text={t("admin.empty")} onRetry={() => setRefresh((v) => v + 1)} retryLabel={t("common.refresh")} />}
                </div>
                <Pager
                  offset={userOffset}
                  total={userTotal}
                  pageSize={ADMIN_PAGE_SIZE}
                  onPrev={() => setUserOffset(Math.max(0, userOffset - ADMIN_PAGE_SIZE))}
                  onNext={() => setUserOffset(userOffset + ADMIN_PAGE_SIZE)}
                  recordsLabel={t("admin.records")}
                />
              </>
            )}

            {section === "deposits" && (
              <>
                <div className="flex flex-wrap gap-1">
                  {["all", "completed"].map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => { setDepositStatus(item); setPaymentOffset(0); }}
                      className={`rounded-lg px-3 py-1.5 text-[11px] font-semibold ${
                        depositStatus === item ? "bg-slate-800 text-white dark:bg-sky-600" : "bg-white dark:bg-white/[0.06]"
                      }`}
                    >
                      {t(`admin.status.${item}` as any)}
                    </button>
                  ))}
                </div>
                {paymentWorkflow && (
                  <p className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">{paymentWorkflow}</p>
                )}
                <div className="space-y-2 md:hidden">
                  {payments.length ? payments.map((item) => (
                    <article key={item.id} className="rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">@{item.username || "—"} · {item.name}</p>
                          <p className="truncate text-[11px] text-slate-500">
                            {item.method || item.provider} · {item.reference || item.id}
                          </p>
                        </div>
                        <p className="shrink-0 text-sm font-bold">{money(item.amount)}</p>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                        <StatusChip status={item.status} />
                        <time className="text-[11px] text-slate-500">{shortTime(item.completed_at || item.created_at)}</time>
                      </div>
                    </article>
                  )) : (
                    <Empty
                      text={t("admin.emptyDeposits")}
                      onRetry={() => setRefresh((v) => v + 1)}
                      retryLabel={t("common.refresh")}
                    />
                  )}
                </div>
                <div className="hidden overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-white/10 dark:bg-[#141820] md:block">
                  <table className="min-w-full text-left text-sm">
                    <thead className="border-b border-slate-100 text-[11px] uppercase text-slate-500 dark:border-white/10">
                      <tr>
                        <th className="px-3 py-2">{t("admin.users")}</th>
                        <th className="px-3 py-2">{t("admin.amount")}</th>
                        <th className="px-3 py-2">{t("admin.status.completed")}</th>
                        <th className="px-3 py-2">Ref</th>
                        <th className="px-3 py-2">Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payments.map((item) => (
                        <tr key={item.id} className="border-t border-slate-50 dark:border-white/5">
                          <td className="px-3 py-2">@{item.username || "—"}</td>
                          <td className="px-3 py-2 font-semibold">{money(item.amount)}</td>
                          <td className="px-3 py-2"><StatusChip status={item.status} /></td>
                          <td className="px-3 py-2 text-xs text-slate-500">{item.reference || "—"}</td>
                          <td className="px-3 py-2 text-xs text-slate-500">{shortTime(item.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!payments.length && <div className="p-4"><Empty text={t("admin.emptyDeposits")} /></div>}
                </div>
                <Pager
                  offset={paymentOffset}
                  total={paymentTotal}
                  pageSize={ADMIN_PAGE_SIZE}
                  onPrev={() => setPaymentOffset(Math.max(0, paymentOffset - ADMIN_PAGE_SIZE))}
                  onNext={() => setPaymentOffset(paymentOffset + ADMIN_PAGE_SIZE)}
                  recordsLabel={t("admin.records")}
                />
              </>
            )}

            {section === "withdrawals" && (
              <>
                {withdrawHouseAccounts.length > 0 && (
                  <div className="rounded-xl border border-slate-200/90 bg-white p-3 text-xs dark:border-white/10 dark:bg-[#141820]">
                    <p className="font-semibold text-slate-700 dark:text-slate-200">
                      {t("admin.housePayoutAccounts")}
                    </p>
                    <p className="mt-1 text-slate-500 dark:text-slate-400">
                      {t("admin.housePayoutAccountsHint")}
                    </p>
                    <ul className="mt-2 space-y-1 text-slate-600 dark:text-slate-300">
                      {withdrawHouseAccounts.map((row) => (
                        <li key={row.id}>
                          {row.bank} · {row.account_name} · {row.account_number}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="flex flex-wrap gap-1">
                  {["pending", "approved", "rejected", "all"].map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => { setWithdrawStatus(item); setPaymentOffset(0); }}
                      className={`rounded-lg px-3 py-1.5 text-[11px] font-semibold ${
                        withdrawStatus === item ? "bg-slate-800 text-white dark:bg-sky-600" : "bg-white dark:bg-white/[0.06]"
                      }`}
                    >
                      {t(`admin.status.${item}` as any)}
                    </button>
                  ))}
                </div>
                <div className="space-y-2">
                  {payments.length ? payments.map((item) => (
                    <article key={item.id} className="rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">@{item.username || "—"} · {item.name}</p>
                          <p className="truncate text-[11px] text-slate-500">
                            {item.method} · {item.account_number_masked || item.id.slice(0, 8)}
                          </p>
                        </div>
                        <p className="shrink-0 text-sm font-bold">{money(item.amount)}</p>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusChip status={item.status} />
                          <time className="text-[11px] text-slate-500">{shortTime(item.created_at)}</time>
                        </div>
                        {item.status === "PENDING" && (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              disabled={pendingAction === item.id}
                              onClick={() => reviewWithdrawal(item, "reject")}
                              className="rounded-lg border border-rose-300 px-3 py-1.5 text-[11px] font-semibold text-rose-600 disabled:opacity-50 dark:border-rose-500/40 dark:text-rose-300"
                            >
                              {t("admin.reject")}
                            </button>
                            <button
                              type="button"
                              disabled={pendingAction === item.id}
                              onClick={() => reviewWithdrawal(item, "approve")}
                              className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-semibold text-white disabled:opacity-50"
                            >
                              {pendingAction === item.id ? <Loader2 size={12} className="animate-spin" /> : null}
                              {t("admin.approve")}
                            </button>
                          </div>
                        )}
                      </div>
                    </article>
                  )) : (
                    <Empty
                      text={t("admin.emptyWithdrawals")}
                      onRetry={() => setRefresh((v) => v + 1)}
                      retryLabel={t("common.refresh")}
                    />
                  )}
                </div>
                <Pager
                  offset={paymentOffset}
                  total={paymentTotal}
                  pageSize={ADMIN_PAGE_SIZE}
                  onPrev={() => setPaymentOffset(Math.max(0, paymentOffset - ADMIN_PAGE_SIZE))}
                  onNext={() => setPaymentOffset(paymentOffset + ADMIN_PAGE_SIZE)}
                  recordsLabel={t("admin.records")}
                />
              </>
            )}

            {section === "accounts" && (
              <section className="space-y-3 rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
                <div>
                  <h2 className="text-sm font-semibold">{t("admin.accounts")}</h2>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                    {t("admin.accountsHint")}
                  </p>
                </div>
                <div className="flex flex-wrap gap-1">
                  {(["deposit", "withdraw", "all"] as const).map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setAccountKindFilter(item)}
                      className={`rounded-lg px-3 py-1.5 text-[11px] font-semibold ${
                        accountKindFilter === item
                          ? "bg-slate-800 text-white dark:bg-sky-600"
                          : "bg-slate-100 dark:bg-white/[0.06]"
                      }`}
                    >
                      {t(`admin.accountsKind.${item}` as any)}
                    </button>
                  ))}
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {!editingAccount && (
                    <label className="block text-xs font-semibold sm:col-span-2">
                      {t("admin.accountsKindLabel")}
                      <select
                        value={accountForm.kind}
                        onChange={(e) =>
                          setAccountForm((current) => ({
                            ...current,
                            kind: e.target.value as PaymentAccountKind,
                          }))
                        }
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                      >
                        <option value="deposit">{t("admin.accountsKind.deposit")}</option>
                        <option value="withdraw">{t("admin.accountsKind.withdraw")}</option>
                      </select>
                    </label>
                  )}
                  <label className="block text-xs font-semibold">
                    {t("admin.accountsBank")}
                    <input
                      value={editingAccount ? editingAccount.bank : accountForm.bank}
                      onChange={(e) => {
                        const value = e.target.value;
                        if (editingAccount) {
                          setEditingAccount({ ...editingAccount, bank: value });
                        } else {
                          setAccountForm((current) => ({ ...current, bank: value }));
                        }
                      }}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                    />
                  </label>
                  <label className="block text-xs font-semibold">
                    {t("admin.accountsName")}
                    <input
                      value={editingAccount ? editingAccount.account_name : accountForm.account_name}
                      onChange={(e) => {
                        const value = e.target.value;
                        if (editingAccount) {
                          setEditingAccount({ ...editingAccount, account_name: value });
                        } else {
                          setAccountForm((current) => ({ ...current, account_name: value }));
                        }
                      }}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                    />
                  </label>
                  <label className="block text-xs font-semibold sm:col-span-2">
                    {t("admin.accountsNumber")}
                    <input
                      value={editingAccount ? editingAccount.account_number : accountForm.account_number}
                      onChange={(e) => {
                        const value = e.target.value;
                        if (editingAccount) {
                          setEditingAccount({ ...editingAccount, account_number: value });
                        } else {
                          setAccountForm((current) => ({ ...current, account_number: value }));
                        }
                      }}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                    />
                  </label>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={pendingAction === "account-save"}
                    onClick={() => void submitAccountForm()}
                    className="rounded-xl bg-slate-800 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-sky-600"
                  >
                    {editingAccount ? t("admin.accountsSave") : t("admin.accountsAdd")}
                  </button>
                  {editingAccount && (
                    <button
                      type="button"
                      onClick={() => setEditingAccount(null)}
                      className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold dark:border-white/10"
                    >
                      {t("admin.accountsCancelEdit")}
                    </button>
                  )}
                </div>
                {accountsMessage && (
                  <p className="text-xs text-slate-600 dark:text-slate-300">{accountsMessage}</p>
                )}
                <div className="space-y-2">
                  {paymentAccounts.length ? paymentAccounts.map((row) => (
                    <article
                      key={row.id}
                      className={`rounded-xl border p-3 ${
                        row.is_enabled
                          ? "border-emerald-200/80 bg-emerald-50/40 dark:border-emerald-500/25 dark:bg-emerald-500/5"
                          : "border-slate-200/80 bg-slate-50 opacity-80 dark:border-white/10 dark:bg-white/[0.04]"
                      }`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">
                            {row.bank}
                            <span className="ml-2 rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-700 dark:bg-white/10 dark:text-slate-200">
                              {t(`admin.accountsKind.${row.kind}` as any)}
                            </span>
                            <span
                              className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                                row.is_enabled
                                  ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200"
                                  : "bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-slate-300"
                              }`}
                            >
                              {row.is_enabled ? t("admin.accountsEnabled") : t("admin.accountsDisabled")}
                            </span>
                          </p>
                          <p className="mt-1 truncate text-[11px] text-slate-500">
                            {row.account_name} · {row.account_number}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={pendingAction === `toggle-${row.id}`}
                            onClick={() => void toggleAccountEnabled(row)}
                            className="rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] font-semibold disabled:opacity-50 dark:border-white/10"
                          >
                            {row.is_enabled ? t("admin.accountsDisable") : t("admin.accountsEnable")}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setEditingAccount(row);
                              setAccountsMessage("");
                            }}
                            className="rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] font-semibold dark:border-white/10"
                          >
                            {t("admin.accountsEdit")}
                          </button>
                          <button
                            type="button"
                            disabled={pendingAction === `delete-${row.id}`}
                            onClick={() => void removeAccount(row)}
                            className="rounded-lg border border-rose-200 px-3 py-1.5 text-[11px] font-semibold text-rose-700 disabled:opacity-50 dark:border-rose-500/30 dark:text-rose-300"
                          >
                            {t("admin.accountsDelete")}
                          </button>
                        </div>
                      </div>
                    </article>
                  )) : <Empty text={t("admin.accountsEmpty")} />}
                </div>
              </section>
            )}

            {section === "games" && (
              <>
                <div className="flex gap-1 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                  {GAMES.map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => { setGame(item); setPlayerOffset(0); }}
                      className={`shrink-0 rounded-lg px-3 py-1.5 text-[11px] font-semibold capitalize ${
                        game === item ? "bg-slate-800 text-white dark:bg-sky-600" : "bg-white dark:bg-white/[0.06]"
                      }`}
                    >
                      {t(`admin.game.${item}` as any)}
                    </button>
                  ))}
                </div>
                {game === "bingo" && (
                  <BingoBotControl
                    status={bingoBot}
                    busy={bingoBotBusy}
                    onToggle={toggleBingoBot}
                    onReserveRange={updateBingoBotReserve}
                  />
                )}
                {game === "lotto" && (
                  <LottoBotControl
                    status={lottoBot}
                    busy={lottoBotBusy}
                    onToggle={toggleLottoBot}
                    onReserveRange={updateLottoBotReserve}
                  />
                )}
                <div className="space-y-2">
                  {players.length ? players.map((item) => (
                    <article key={item.user_id} className="grid grid-cols-2 gap-2 rounded-xl border border-slate-200/90 bg-white p-3 text-sm dark:border-white/10 dark:bg-[#141820]">
                      <div className="min-w-0">
                        <p className="truncate font-semibold">
                          @{item.username || "—"}
                          {item.is_bot ? (
                            <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-800 dark:bg-amber-500/20 dark:text-amber-200">
                              {t("admin.botBadge")}
                            </span>
                          ) : null}
                        </p>
                        <p className="truncate text-[11px] text-slate-500">{item.first_name}</p>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold">{money(item.turnover)}</p>
                        <p className="text-[11px] text-slate-500">{item.plays} {t("admin.plays")}</p>
                      </div>
                    </article>
                  )) : <Empty text={t("admin.empty")} onRetry={() => setRefresh((v) => v + 1)} retryLabel={t("common.refresh")} />}
                </div>
                <Pager
                  offset={playerOffset}
                  total={playerTotal}
                  pageSize={ADMIN_PAGE_SIZE}
                  onPrev={() => setPlayerOffset(Math.max(0, playerOffset - ADMIN_PAGE_SIZE))}
                  onNext={() => setPlayerOffset(playerOffset + ADMIN_PAGE_SIZE)}
                  recordsLabel={t("admin.records")}
                />
              </>
            )}

            {section === "messages" && (
              <section className="space-y-3 rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
                <div>
                  <h2 className="text-sm font-semibold">{t("admin.messages")}</h2>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                    {t("admin.broadcastHint")}
                  </p>
                </div>
                <label className="block text-xs font-semibold">
                  {t("admin.broadcastMessage")}
                  <textarea
                    value={broadcastMessage}
                    onChange={(e) => setBroadcastMessage(e.target.value)}
                    rows={4}
                    maxLength={4000}
                    placeholder={t("admin.broadcastMessagePlaceholder")}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  />
                </label>
                <label className="block text-xs font-semibold">
                  {t("admin.broadcastGame")}
                  <select
                    value={broadcastGame}
                    onChange={(e) => setBroadcastGame(e.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  >
                    {BROADCAST_GAMES.map((item) => (
                      <option key={item || "none"} value={item}>
                        {item
                          ? t(`admin.game.${item}` as any)
                          : t("admin.broadcastGameNone")}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs font-semibold">
                  {t("admin.broadcastUrl")}
                  <input
                    value={broadcastUrl}
                    onChange={(e) => setBroadcastUrl(e.target.value)}
                    disabled={!!broadcastGame}
                    placeholder="https://…"
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm disabled:opacity-50 dark:border-white/10"
                  />
                </label>
                <label className="block text-xs font-semibold">
                  {t("admin.broadcastLabel")}
                  <input
                    value={broadcastLabel}
                    onChange={(e) => setBroadcastLabel(e.target.value)}
                    placeholder={t("admin.broadcastLabelPlaceholder")}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  />
                </label>
                {broadcastResult && (
                  <div className="rounded-lg bg-slate-100 p-3 text-xs dark:bg-white/[0.06]">
                    <p className="font-semibold">{t("admin.broadcastResult")}</p>
                    <p className="mt-1">
                      {t("admin.broadcastCounts", {
                        intended: broadcastResult.intended,
                        succeeded: broadcastResult.succeeded,
                        failed: broadcastResult.failed,
                      })}
                    </p>
                    {broadcastResult.errors?.length > 0 && (
                      <ul className="mt-2 max-h-32 space-y-0.5 overflow-y-auto text-[11px] text-rose-700 dark:text-rose-300">
                        {broadcastResult.errors.map((item) => (
                          <li key={`${item.telegram_id}-${item.error}`}>
                            {item.telegram_id}: {item.error}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
                <button
                  type="button"
                  disabled={broadcastBusy || !broadcastMessage.trim()}
                  onClick={() => void submitBroadcast()}
                  className="w-full rounded-xl bg-slate-800 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-sky-600"
                >
                  {broadcastBusy ? t("common.loading") : t("admin.broadcastSend")}
                </button>
              </section>
            )}

            {section === "admins" && (
              <section className="space-y-3 rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
                <div>
                  <h2 className="text-sm font-semibold">{t("admin.admins")}</h2>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                    {t("admin.adminsHint")}
                  </p>
                </div>
                {caps.can_manage_admins && (
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <input
                      value={newAdminUsername}
                      onChange={(e) => setNewAdminUsername(e.target.value)}
                      placeholder={t("admin.adminsUsernamePlaceholder")}
                      className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                    />
                    <button
                      type="button"
                      disabled={pendingAction === "add-admin" || !newAdminUsername.trim()}
                      onClick={() => void submitAddAdmin()}
                      className="rounded-xl bg-slate-800 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-sky-600"
                    >
                      {t("admin.adminsAdd")}
                    </button>
                  </div>
                )}
                {adminsMessage && (
                  <p className="text-xs text-slate-600 dark:text-slate-300">{adminsMessage}</p>
                )}
                <div className="space-y-2">
                  {admins.length ? admins.map((row) => (
                    <article
                      key={row.username}
                      className="flex items-center justify-between gap-2 rounded-xl border border-slate-200/80 bg-slate-50 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold">
                          @{row.username}
                          {row.is_super ? (
                            <span className="ml-2 rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-sky-800 dark:bg-sky-500/20 dark:text-sky-200">
                              {t("admin.adminsSuper")}
                            </span>
                          ) : null}
                        </p>
                        <p className="truncate text-[11px] text-slate-500">
                          {row.created_by
                            ? t("admin.adminsCreatedBy", { username: row.created_by })
                            : t("admin.adminsBuiltIn")}
                        </p>
                      </div>
                      {caps.can_manage_admins && row.managed && !row.is_super && (
                        <button
                          type="button"
                          disabled={pendingAction === `remove-${row.username}`}
                          onClick={() => void submitRemoveAdmin(row.username)}
                          className="shrink-0 rounded-lg border border-rose-200 px-3 py-1.5 text-[11px] font-semibold text-rose-700 disabled:opacity-50 dark:border-rose-500/30 dark:text-rose-300"
                        >
                          {t("admin.adminsRemove")}
                        </button>
                      )}
                    </article>
                  )) : <Empty text={t("admin.empty")} />}
                </div>
              </section>
            )}

            {section === "audit" && (
              <>
                <div className="space-y-2">
                  {audit.length ? audit.map((item) => (
                    <article key={item.id} className="rounded-xl border border-slate-200/90 bg-white p-3 dark:border-white/10 dark:bg-[#141820]">
                      <div className="flex items-start justify-between gap-3">
                        <p className="min-w-0 break-words text-sm font-semibold">{item.action}</p>
                        <time className="shrink-0 text-[11px] text-slate-500">{shortTime(item.created_at)}</time>
                      </div>
                      <p className="mt-1 truncate text-[11px] text-slate-500">@{item.admin_username} · {item.target_type} {item.target_id}</p>
                      {item.reason && <p className="mt-2 break-words text-sm">{item.reason}</p>}
                    </article>
                  )) : <Empty text={t("admin.empty")} onRetry={() => setRefresh((v) => v + 1)} retryLabel={t("common.refresh")} />}
                </div>
                <Pager
                  offset={auditOffset}
                  total={auditTotal}
                  pageSize={ADMIN_PAGE_SIZE}
                  onPrev={() => setAuditOffset(Math.max(0, auditOffset - ADMIN_PAGE_SIZE))}
                  onNext={() => setAuditOffset(auditOffset + ADMIN_PAGE_SIZE)}
                  recordsLabel={t("admin.records")}
                />
              </>
            )}

            {section === "maintenance" && caps.can_maintenance && (
              <div className="space-y-4">
              <section className="space-y-3 rounded-xl border border-rose-200/80 bg-white p-3 dark:border-rose-500/25 dark:bg-[#141820]">
                <div>
                  <h2 className="text-sm font-semibold text-rose-800 dark:text-rose-200">
                    {t("admin.retentionTitle")}
                  </h2>
                  <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                    {t("admin.retentionHint")}
                  </p>
                </div>
                <div
                  role="alert"
                  className="rounded-lg border border-rose-300/80 bg-rose-50 px-3 py-2 text-xs text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200"
                >
                  {t("admin.retentionWarning")}
                </div>
                <label className="block text-xs font-semibold">
                  {t("admin.retentionOption")}
                  <select
                    value={retentionOption}
                    onChange={(e) => {
                      setRetentionOption(e.target.value as RetentionOption);
                      setRetentionConfirm("");
                      setRetentionMessage("");
                    }}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  >
                    {RETENTION_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {t(`admin.retention.option.${option}` as any)}
                      </option>
                    ))}
                  </select>
                </label>
                {retentionPreview && (
                  <div className="rounded-lg bg-slate-100 p-3 text-xs dark:bg-white/[0.06]">
                    <p className="font-semibold">{t("admin.retentionPreview")}</p>
                    <p className="mt-1">
                      {t("admin.retentionPreviewTotal", { count: retentionPreview.total_rows })}
                    </p>
                    <p>{t("admin.retentionUsersKept", { count: retentionPreview.users_kept })}</p>
                    {retentionPreview.zeros_balances && (
                      <p className="mt-1 text-rose-700 dark:text-rose-300">
                        {t("admin.retentionZeroBalances")}
                      </p>
                    )}
                    {retentionPreview.keeps_payments && (
                      <p className="mt-1 text-emerald-700 dark:text-emerald-300">
                        {t("admin.retentionKeepPayments")}
                      </p>
                    )}
                    {retentionPreview.flushes_redis_game_keys && (
                      <p className="text-rose-700 dark:text-rose-300">
                        {t("admin.retentionFlushRedis")}
                      </p>
                    )}
                    <ul className="mt-2 max-h-40 space-y-0.5 overflow-y-auto text-[11px] text-slate-500">
                      {Object.entries(retentionPreview.counts)
                        .filter(([, n]) => n > 0)
                        .map(([table, n]) => (
                          <li key={table} className="flex justify-between gap-2">
                            <span className="truncate">{table}</span>
                            <span className="shrink-0 font-medium">{n}</span>
                          </li>
                        ))}
                    </ul>
                  </div>
                )}
                <label className="block text-xs font-semibold">
                  {t("admin.retentionConfirmLabel", {
                    word: retentionPreview?.confirmation_required ?? "DELETE",
                  })}
                  <input
                    value={retentionConfirm}
                    onChange={(e) => setRetentionConfirm(e.target.value)}
                    autoComplete="off"
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  />
                </label>
                <label className="block text-xs font-semibold">
                  {t("admin.reason")}
                  <textarea
                    value={retentionReason}
                    onChange={(e) => setRetentionReason(e.target.value)}
                    rows={3}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  />
                </label>
                {retentionMessage && (
                  <p className="text-xs text-slate-600 dark:text-slate-300">{retentionMessage}</p>
                )}
                <button
                  type="button"
                  disabled={
                    pendingAction === "purge"
                    || !retentionPreview
                    || retentionConfirm.trim() !== retentionPreview.confirmation_required
                    || retentionReason.trim().length < 3
                  }
                  onClick={submitPurge}
                  className="w-full rounded-xl bg-rose-700 py-3 font-semibold text-white disabled:opacity-40 dark:bg-rose-600"
                >
                  {pendingAction === "purge" ? t("common.loading") : t("admin.retentionPurge")}
                </button>
              </section>

              <section className="space-y-3 rounded-xl border border-amber-200/80 bg-white p-3 dark:border-amber-500/25 dark:bg-[#141820]">
                <div>
                  <h2 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                    {t("admin.deleteUsersTitle")}
                  </h2>
                  <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                    {t("admin.deleteUsersHint")}
                  </p>
                </div>
                <label className="block text-xs font-semibold">
                  {t("admin.deleteUserQuery")}
                  <input
                    value={deleteQuery}
                    onChange={(e) => setDeleteQuery(e.target.value)}
                    placeholder={t("admin.deleteUserQueryPlaceholder")}
                    autoComplete="off"
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  />
                </label>
                <label className="block text-xs font-semibold">
                  {t("admin.retentionConfirmLabel", { word: "DELETE_USERS" })}
                  <input
                    value={deleteConfirm}
                    onChange={(e) => setDeleteConfirm(e.target.value)}
                    autoComplete="off"
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  />
                </label>
                <label className="block text-xs font-semibold">
                  {t("admin.reason")}
                  <textarea
                    value={deleteReason}
                    onChange={(e) => setDeleteReason(e.target.value)}
                    rows={2}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  />
                </label>
                <label className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={deleteForce}
                    onChange={(e) => setDeleteForce(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>{t("admin.deleteUserForce")}</span>
                </label>
                {deleteMessage && (
                  <p className="text-xs text-slate-600 dark:text-slate-300">{deleteMessage}</p>
                )}
                <button
                  type="button"
                  disabled={
                    pendingAction === "delete-user"
                    || deleteConfirm.trim() !== "DELETE_USERS"
                    || deleteReason.trim().length < 3
                    || !deleteQuery.trim()
                  }
                  onClick={submitDeleteUser}
                  className="w-full rounded-xl bg-amber-700 py-3 font-semibold text-white disabled:opacity-40 dark:bg-amber-600"
                >
                  {pendingAction === "delete-user" ? t("common.loading") : t("admin.deleteUserSubmit")}
                </button>
              </section>

              <section className="space-y-3 rounded-xl border border-rose-300/90 bg-white p-3 dark:border-rose-500/40 dark:bg-[#141820]">
                <div>
                  <h2 className="text-sm font-semibold text-rose-900 dark:text-rose-200">
                    {t("admin.deleteAllUsersTitle")}
                  </h2>
                  <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                    {t("admin.deleteAllUsersHint")}
                  </p>
                </div>
                <label className="block text-xs font-semibold">
                  {t("admin.retentionConfirmLabel", { word: "DELETE_ALL_USERS" })}
                  <input
                    value={deleteAllConfirm}
                    onChange={(e) => setDeleteAllConfirm(e.target.value)}
                    autoComplete="off"
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  />
                </label>
                <label className="block text-xs font-semibold">
                  {t("admin.reason")}
                  <textarea
                    value={deleteAllReason}
                    onChange={(e) => setDeleteAllReason(e.target.value)}
                    rows={2}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10"
                  />
                </label>
                <label className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={deleteAllForce}
                    onChange={(e) => setDeleteAllForce(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>{t("admin.deleteUserForce")}</span>
                </label>
                {deleteAllMessage && (
                  <p className="text-xs text-slate-600 dark:text-slate-300">{deleteAllMessage}</p>
                )}
                <button
                  type="button"
                  disabled={
                    pendingAction === "delete-all-users"
                    || deleteAllConfirm.trim() !== "DELETE_ALL_USERS"
                    || deleteAllReason.trim().length < 3
                  }
                  onClick={submitDeleteAllUsers}
                  className="w-full rounded-xl bg-rose-900 py-3 font-semibold text-white disabled:opacity-40"
                >
                  {pendingAction === "delete-all-users" ? t("common.loading") : t("admin.deleteAllUsersSubmit")}
                </button>
              </section>
              </div>
            )}
          </div>
        )}
      </main>

      {adjusting && caps.can_adjust_balance && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:items-center">
          <div className="max-h-[min(85dvh,32rem)] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-4 shadow-2xl dark:bg-[#151a22]">
            <div className="flex justify-between gap-2">
              <h2 className="font-semibold">{t("admin.adjustBalance")}</h2>
              <button type="button" onClick={() => setAdjusting(null)} aria-label={t("common.close")}><X size={18} /></button>
            </div>
            <p className="mt-1 text-sm text-slate-500">@{adjusting.username} · {money(adjusting.balance)}</p>
            <label className="mt-4 block text-xs font-semibold">{t("admin.amount")}
              <input autoFocus type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10" />
            </label>
            <label className="mt-3 block text-xs font-semibold">{t("admin.reason")}
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm dark:border-white/10" rows={3} />
            </label>
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{t("admin.adjustWarning")}</p>
            <button
              type="button"
              disabled={!amount || reason.trim().length < 3 || !!pendingAction}
              onClick={submitAdjustment}
              className="mt-4 w-full rounded-xl bg-slate-800 py-3 font-semibold text-white disabled:opacity-40 dark:bg-sky-600"
            >
              {pendingAction ? t("common.loading") : t("common.confirm")}
            </button>
          </div>
        </div>
      )}

      {selectedUser && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-40 flex justify-end bg-black/40">
          <div className="h-full w-full max-w-md overflow-y-auto bg-white p-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-2xl dark:bg-[#151a22]">
            <div className="flex justify-between">
              <h2 className="font-semibold">{t("admin.userDetail")}</h2>
              <button type="button" onClick={() => setSelectedUser(null)} aria-label={t("common.close")}><X size={18} /></button>
            </div>
            <p className="mt-4 text-lg font-bold">
              @{selectedUser.profile.username || "—"}
              {selectedUser.profile.is_bot ? (
                <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-800 dark:bg-amber-500/20 dark:text-amber-200">
                  {t("admin.botBadge")}
                </span>
              ) : null}
            </p>
            <p className="text-sm text-slate-500">{selectedUser.profile.first_name} {selectedUser.profile.last_name}</p>
            <p className="mt-3 text-2xl font-bold">{money(selectedUser.profile.balance)}</p>
            <h3 className="mt-6 text-sm font-semibold">{t("admin.gamePerformance")}</h3>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {Object.entries(selectedUser.game_stats).map(([name, raw]) => {
                const stat = raw as any;
                return (
                  <div key={name} className="rounded-xl bg-slate-100 p-3 dark:bg-white/[0.06]">
                    <p className="capitalize">{name}</p>
                    <p className="text-xs text-slate-500">{stat.plays} {t("admin.plays")} · {money(stat.turnover)}</p>
                  </div>
                );
              })}
            </div>
            <h3 className="mt-6 text-sm font-semibold">{t("admin.recentLedger")}</h3>
            <div className="mt-2 space-y-2">
              {selectedUser.ledger.map((item: any) => (
                <div key={item.id} className="flex justify-between gap-2 rounded-xl border border-slate-200 p-3 text-sm dark:border-white/10">
                  <span className="min-w-0 truncate">{item.type}</span>
                  <span className="shrink-0 font-semibold">{money(item.amount)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
