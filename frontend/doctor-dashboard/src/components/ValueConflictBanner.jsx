import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

/**
 * Banner displayed when clinically significant value conflicts require user confirmation.
 * Shows what changed (old → new) and provides Confirm/Cancel buttons.
 */
export function ValueConflictBanner({ conflicts, onConfirm, onCancel, disabled }) {
  const { t } = useLanguage();

  if (!conflicts?.length) return null;

  // Filter to only conflicts that require explicit confirmation
  const confirmable = conflicts.filter((c) => c.requires_confirmation);
  if (!confirmable.length) return null;

  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800 dark:bg-amber-950/30">
      <div className="mx-auto max-w-3xl">
        {/* Header */}
        <div className="mb-2 flex items-start gap-2">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden />
          <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
            {t("chat.conflict.title")}
          </p>
        </div>

        {/* Conflict list */}
        <ul className="mb-3 ml-6 space-y-1">
          {confirmable.map((conflict) => (
            <li key={conflict.field} className="flex items-center gap-2 text-sm text-amber-800 dark:text-amber-300">
              <span className="font-medium">{conflict.label}:</span>
              <span className="font-mono">
                <span className="line-through opacity-60">{conflict.old_value}</span>
                <span className="mx-1.5">→</span>
                <span className="font-semibold">{conflict.new_value}</span>
              </span>
            </li>
          ))}
        </ul>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className={cn(
              "h-8 gap-1.5 border-amber-300 text-amber-800 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-900/40",
              disabled && "opacity-50 cursor-not-allowed",
            )}
            onClick={onCancel}
            disabled={disabled}
            type="button"
          >
            <CheckCircle2 className="size-3.5" aria-hidden />
            {t("chat.conflict.cancel")}
          </Button>
          <Button
            size="sm"
            className={cn(
              "h-8 gap-1.5 bg-amber-600 text-white hover:bg-amber-700 dark:bg-amber-600 dark:hover:bg-amber-500",
              disabled && "opacity-50 cursor-not-allowed",
            )}
            onClick={onConfirm}
            disabled={disabled}
            type="button"
          >
            <CheckCircle2 className="size-3.5" aria-hidden />
            {t("chat.conflict.confirm")}
          </Button>
          <span className="ml-1 text-xs text-amber-700 dark:text-amber-400">
            {t("chat.conflict.hint")}
          </span>
        </div>
      </div>
    </div>
  );
}
