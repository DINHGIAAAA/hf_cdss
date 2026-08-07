import { CheckCircle2, Circle, PauseCircle, XCircle } from "lucide-react";

import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { cn } from "@/lib/utils";
import { titleCase } from "@/utils";

const PHASE_STYLES = {
  active: {
    icon: CheckCircle2,
    ring: "border-emerald-500/50 bg-emerald-50/80",
    badge: "bg-emerald-100 text-emerald-800",
  },
  next: {
    icon: Circle,
    ring: "border-primary/40 bg-primary/5",
    badge: "bg-primary/10 text-primary",
  },
  hold: {
    icon: PauseCircle,
    ring: "border-amber-500/40 bg-amber-50/80",
    badge: "bg-amber-100 text-amber-800",
  },
  blocked: {
    icon: XCircle,
    ring: "border-destructive/30 bg-destructive/5",
    badge: "bg-destructive/10 text-destructive",
  },
};

function LabGateRow({ gate }) {
  const tone =
    gate.passed === true
      ? "text-emerald-700"
      : gate.passed === false
        ? "text-destructive"
        : "text-muted-foreground";
  return (
    <li className={cn("text-xs", tone)}>
      <span className="font-medium">{gate.label}</span>
      {gate.value != null ? `: ${gate.value}` : ""}
      <span className="text-muted-foreground"> — {gate.requirement}</span>
    </li>
  );
}

export function MedicationPathway({ pathway }) {
  const { t } = useLanguage();
  const steps = pathway || [];
  if (!steps.length) return null;

  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t("clinicalAnswer.pathwayHeading")}
      </h3>
      <ol className="relative space-y-3 border-l border-border/80 pl-4">
        {steps.map((step) => {
          const style = PHASE_STYLES[step.pathway_phase] || PHASE_STYLES.next;
          const Icon = style.icon;
          return (
            <li className="relative min-w-0" key={`${step.class_id}-${step.step_order}`}>
              <span
                className={cn(
                  "absolute -left-[1.35rem] top-1 flex h-5 w-5 items-center justify-center rounded-full border bg-background",
                  style.ring,
                )}
              >
                <Icon className="h-3 w-3" />
              </span>
              <div className={cn("rounded-lg border px-3 py-2.5", style.ring)}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium text-muted-foreground">
                    {t("clinicalAnswer.pathwayStep", { n: step.step_order })}
                  </span>
                  <span className="font-semibold text-foreground">{step.drug_class}</span>
                  <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium uppercase", style.badge)}>
                    {t(`clinicalAnswer.pathwayPhase.${step.pathway_phase}`)}
                  </span>
                </div>
                {step.patient_drug ? (
                  <p className="mt-1 text-sm text-foreground/90">
                    <span className="text-muted-foreground">{t("clinicalAnswer.pathwayDrug")}: </span>
                    {step.patient_drug}
                    {step.dose_summary ? ` · ${step.dose_summary}` : ""}
                  </p>
                ) : null}
                {step.action ? (
                  <p className="mt-1 text-sm leading-relaxed text-foreground/85">{step.action}</p>
                ) : null}
                {step.lab_gates?.length > 0 ? (
                  <ul className="mt-2 space-y-0.5">
                    {step.lab_gates.map((gate) => (
                      <LabGateRow gate={gate} key={`${step.class_id}-${gate.lab}`} />
                    ))}
                  </ul>
                ) : null}
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {t("clinicalAnswer.pathwayRecStatus")}:{" "}
                  {titleCase(step.recommendation_status?.replace(/_/g, " ") || "—")}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
