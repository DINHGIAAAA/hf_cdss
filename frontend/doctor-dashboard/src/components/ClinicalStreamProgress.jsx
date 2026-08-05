import { Check, Circle, LoaderCircle } from "lucide-react";

import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { resolveStreamPhaseState } from "@/lib/clinicalStreamPipeline";
import { cn } from "@/lib/utils";

export function ClinicalStreamProgress({ step, label, compact = false, className }) {
  const { t } = useLanguage();
  const phases = resolveStreamPhaseState(step);

  return (
    <div
      aria-live="polite"
      className={cn(
        "rounded-xl border border-border bg-muted/40 text-sm",
        compact ? "px-3 py-2.5" : "px-4 py-3",
        className,
      )}
      role="status"
    >
      <div className={cn("flex flex-wrap gap-x-3 gap-y-2", compact ? "items-center" : "items-start")}>
        {phases.map((phase, index) => (
          <div className="flex min-w-0 items-center gap-2" key={phase.id}>
            {index > 0 ? (
              <span aria-hidden className="hidden text-muted-foreground sm:inline">
                →
              </span>
            ) : null}
            <PhaseIcon status={phase.status} />
            <span
              className={cn(
                "truncate text-xs font-medium sm:text-sm",
                phase.status === "active" && "text-foreground",
                phase.status === "done" && "text-muted-foreground",
                phase.status === "pending" && "text-muted-foreground/70",
              )}
            >
              {t(phase.labelKey)}
            </span>
          </div>
        ))}
      </div>
      {label ? (
        <p className={cn("text-muted-foreground", compact ? "mt-1.5 text-xs" : "mt-2.5 text-sm")}>{label}</p>
      ) : null}
    </div>
  );
}

function PhaseIcon({ status }) {
  if (status === "done") {
    return <Check aria-hidden className="size-4 shrink-0 text-primary" />;
  }
  if (status === "active") {
    return <LoaderCircle aria-hidden className="size-4 shrink-0 animate-spin text-primary" />;
  }
  return <Circle aria-hidden className="size-4 shrink-0 text-muted-foreground/40" />;
}
