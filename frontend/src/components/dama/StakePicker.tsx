import { useMemo, useState } from "react";
import { Wallet } from "lucide-react";
import { useI18n } from "../../i18n";
import {
  DAMA_MAX_STAKE,
  DAMA_MIN_STAKE,
  isValidDamaStake,
} from "../../games/dama/constants";

export const DAMA_STAKE_PRESETS = ["5", "10", "15"] as const;
export { DAMA_MIN_STAKE, DAMA_MAX_STAKE, isValidDamaStake };

interface StakePickerProps {
  balance: string | null;
  stake: string;
  onStakeChange: (stake: string) => void;
  title?: string;
  subtitle?: string;
}

function formatEtb(value: string | null): string {
  if (value == null) return "—";
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : value;
}

export function stakePrizePreview(stake: string): { pot: string; fee: string; prize: string } {
  const s = Math.max(0, Number(stake) || 0);
  const pot = s * 2;
  const fee = Math.floor(pot * 0.1 * 100) / 100;
  const prize = Math.round((pot - fee) * 100) / 100;
  return {
    pot: pot.toFixed(2),
    fee: fee.toFixed(2),
    prize: prize.toFixed(2),
  };
}

export function StakePicker({
  balance,
  stake,
  onStakeChange,
  title,
  subtitle,
}: StakePickerProps) {
  const { t } = useI18n();
  const [custom, setCustom] = useState("");
  const preview = useMemo(() => stakePrizePreview(stake), [stake]);
  const bal = Number(balance);
  const stakeOk = isValidDamaStake(stake);
  const canAfford = Number.isFinite(bal) && bal >= Number(stake);

  return (
    <div className="rounded-3xl bg-white/95 p-4 shadow-md ring-1 ring-orange-100 dark:bg-[#1E1B2E] dark:ring-white/10">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-extrabold text-purple-950 dark:text-white">
            {title ?? t("dama.chooseStake")}
          </h2>
          <p className="mt-0.5 text-[11px] font-medium text-purple-500 dark:text-purple-300/75">
            {subtitle ?? t("dama.chooseStakeHint")}
          </p>
        </div>
        <div className="rounded-2xl bg-violet-500/10 px-2.5 py-1.5 text-right">
          <p className="flex items-center justify-end gap-1 text-[10px] font-bold uppercase tracking-wide text-violet-600 dark:text-violet-300">
            <Wallet size={11} />
            {t("common.wallet")}
          </p>
          <p className="text-sm font-black tabular-nums text-purple-950 dark:text-white">
            {formatEtb(balance)}
            <span className="ml-0.5 text-[10px] font-bold text-purple-400">{t("common.etb")}</span>
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {DAMA_STAKE_PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => {
              setCustom("");
              onStakeChange(p);
            }}
            className={`rounded-2xl px-4 py-2.5 text-sm font-extrabold transition ${
              stake === p && !custom
                ? "bg-orange-500 text-white shadow"
                : "bg-purple-50 text-purple-800 ring-1 ring-purple-100 dark:bg-white/10 dark:text-purple-100 dark:ring-white/10"
            }`}
          >
            {p} {t("common.etb")}
          </button>
        ))}
      </div>

      <label className="mt-3 block">
        <span className="text-[11px] font-bold uppercase tracking-wide text-purple-400">
          {t("dama.custom")}
        </span>
        <input
          inputMode="decimal"
          value={custom}
          placeholder={t("dama.customPlaceholder")}
          onChange={(e) => {
            const v = e.target.value.replace(/[^\d.]/g, "");
            setCustom(v);
            if (v) onStakeChange(v);
          }}
          className="mt-1 w-full rounded-2xl border-0 bg-purple-50/80 px-3 py-2.5 text-sm font-bold text-purple-950 outline-none ring-1 ring-purple-100 focus:ring-2 focus:ring-orange-300 dark:bg-white/5 dark:text-white dark:ring-white/10"
        />
      </label>

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-xl bg-stone-100/80 px-2 py-2 dark:bg-white/5">
          <p className="text-[10px] font-bold uppercase text-stone-500">{t("common.pot")}</p>
          <p className="text-sm font-black tabular-nums text-stone-800 dark:text-white">
            {preview.pot}
          </p>
        </div>
        <div className="rounded-xl bg-stone-100/80 px-2 py-2 dark:bg-white/5">
          <p className="text-[10px] font-bold uppercase text-stone-500">{t("common.fee")}</p>
          <p className="text-sm font-black tabular-nums text-stone-800 dark:text-white">
            {preview.fee}
          </p>
        </div>
        <div className="rounded-xl bg-emerald-50 px-2 py-2 dark:bg-emerald-950/30">
          <p className="text-[10px] font-bold uppercase text-emerald-600">{t("common.win")}</p>
          <p className="text-sm font-black tabular-nums text-emerald-700 dark:text-emerald-300">
            {preview.prize}
          </p>
        </div>
      </div>

      {Number(stake) > 0 && !stakeOk && (
        <p className="mt-2 text-center text-xs font-semibold text-rose-600">
          {t("dama.stakeTooLow", { min: String(DAMA_MIN_STAKE) })}
        </p>
      )}
      {stakeOk && !canAfford && Number(stake) > 0 && (
        <p className="mt-2 text-center text-xs font-semibold text-rose-600">
          {t("dama.notEnoughBalance", { stake })}
        </p>
      )}
    </div>
  );
}
