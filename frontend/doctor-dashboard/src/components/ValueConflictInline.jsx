import { Button } from "@/components/ui/button";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

/**
 * Inline confirmation buttons for value conflicts, shown within a chat message.
 * Compact design that fits naturally after the confirmation text.
 */
export function ValueConflictInline({ conflicts, onConfirm, onCancel }) {
  const { t } = useLanguage();

  if (!conflicts?.length) return null;

  const confirmable = conflicts.filter((c) => c.requires_confirmation);
  if (!confirmable.length) return null;

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-950/30">
      <AlertTriangle className="size-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden />
      <div className="flex min-w-0 flex-1 items-center gap-1.5 text-sm flex-wrap">
        {confirmable.map((conflict) => (
          <span key={conflict.field} className="text-amber-800 dark:text-amber-200">
            <span className="font-medium">{conflict.label}:</span>{" "}
            <span className="font-mono text-xs">
              <span className="line-through opacity-60">{conflict.old_value}</span>
              <span className="mx-1">→</span>
              <span className="font-semibold">{conflict.new_value}</span>
            </span>
          </span>
        ))}
      </div>
      <div className="flex shrink-0 items-center gap-1.5 [&>button]:relative [&>button]:z-10">
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium text-amber-700 hover:bg-amber-100 dark:text-amber-300 dark:hover:bg-amber-900/40"
        >
          <XCircle className="size-3.5" aria-hidden />
          {t("chat.conflict.cancel")}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="inline-flex h-7 items-center gap-1 rounded-md bg-amber-600 px-2 text-xs font-medium text-white hover:bg-amber-700 dark:bg-amber-600 dark:hover:bg-amber-500"
        >
          <CheckCircle2 className="size-3.5" aria-hidden />
          {t("chat.conflict.confirm")}
        </button>
      </div>
    </div>
  );
}
