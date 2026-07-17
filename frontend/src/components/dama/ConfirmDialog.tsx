import type { ReactNode } from "react";
import { useI18n } from "../../i18n";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useI18n();
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]">
      <div
        role="dialog"
        aria-modal
        className="w-full max-w-sm rounded-3xl bg-white p-5 shadow-2xl ring-1 ring-black/5 dark:bg-[#1E1B2E] dark:ring-white/10"
      >
        <h3 className="text-lg font-extrabold text-purple-950 dark:text-white">{title}</h3>
        <p className="mt-2 text-sm font-medium text-purple-600 dark:text-purple-300/85">
          {message}
        </p>
        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-2xl bg-purple-50 py-2.5 text-sm font-bold text-purple-800 dark:bg-white/10 dark:text-purple-100"
          >
            {cancelLabel ?? t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`flex-1 rounded-2xl py-2.5 text-sm font-bold text-white shadow ${
              danger ? "bg-rose-500" : "bg-orange-500"
            }`}
          >
            {confirmLabel ?? t("common.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

interface BannerProps {
  children: ReactNode;
  className?: string;
}

export function SoftBanner({ children, className = "" }: BannerProps) {
  return (
    <div
      className={`rounded-2xl px-3 py-2 text-center text-xs font-bold ${className}`}
    >
      {children}
    </div>
  );
}
