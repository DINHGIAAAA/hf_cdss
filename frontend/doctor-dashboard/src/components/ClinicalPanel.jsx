import { useEffect, useState } from "react";
import { ExternalLink, FileText, ShieldAlert } from "lucide-react";
import { patientSummary, sourceLink, statusClass, titleCase } from "../utils";
import {
  evidenceDocumentTitle,
  evidenceMatchPercent,
  evidenceReadableFacts,
  evidenceSectionLabel,
  repairEvidenceText,
} from "@/lib/evidenceDisplay";
import {
  collectSharedVitalChips,
  recommendationCardKey,
  recommendationDetailLines,
  recommendationLead,
} from "@/lib/recommendationDisplay";
import { DosePlanDisplay } from "@/components/DosePlanDisplay";
import { MedicationPathway } from "@/components/MedicationPathway";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

function statusTone(status) {
  const tone = statusClass(status);
  if (tone === "danger") return "border-destructive/30 bg-destructive/10 text-destructive";
  if (tone === "warning") return "border-amber-500/30 bg-amber-50 text-amber-700";
  return "border-emerald-500/30 bg-emerald-50 text-emerald-700";
}

function EvidenceCard({ chunk }) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(false);
  const link = sourceLink(chunk);
  const excerpt = repairEvidenceText(chunk.text);
  const title = evidenceDocumentTitle(chunk);
  const sectionLabel = evidenceSectionLabel(chunk);
  const matchPct = evidenceMatchPercent(chunk);
  const facts = evidenceReadableFacts(chunk);

  return (
    <Card className="w-full max-w-full min-w-0 gap-0 overflow-hidden border-border/80 py-0 shadow-sm">
      <CardHeader className="gap-2 space-y-0 border-b border-border/60 px-3 py-3">
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="min-w-0 flex-1 overflow-hidden">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {t("clinicalPanel.evidence")}
            </p>
            <CardTitle className="mt-1 line-clamp-2 text-sm leading-snug">{title}</CardTitle>
            {sectionLabel ? (
              <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">
                {sectionLabel}
              </p>
            ) : null}
          </div>
          {matchPct != null ? (
            <Badge className="shrink-0" title={t("clinicalPanel.matchScore")} variant="secondary">
              {matchPct}%
            </Badge>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="min-w-0 space-y-3 overflow-hidden px-3 py-3">
        {excerpt ? (
          <div className="rounded-md border border-border/60 bg-background/80 px-3 py-2.5">
            <p
              className={cn(
                "text-sm leading-relaxed text-foreground/90 [overflow-wrap:anywhere] break-words",
                !expanded && "line-clamp-5",
              )}
            >
              {excerpt}
            </p>
            {excerpt.length > 220 ? (
              <Button
                className="mt-2 h-7 cursor-pointer px-2 text-xs"
                onClick={() => setExpanded((open) => !open)}
                type="button"
                variant="ghost"
              >
                {expanded ? t("clinicalPanel.showLess") : t("clinicalPanel.showMore")}
              </Button>
            ) : null}
          </div>
        ) : null}

        {facts.length ? (
          <ul className="flex flex-wrap gap-2" aria-label={t("clinicalPanel.sourceDetails")}>
            {facts.map((fact) => (
              <li
                className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border/70 bg-muted/30 px-2.5 py-1 text-xs text-foreground/80"
                key={fact.key}
              >
                <span className="font-semibold text-muted-foreground">
                  {t(`clinicalPanel.fact.${fact.key}`)}
                </span>
                <span className="min-w-0 truncate">{fact.value}</span>
              </li>
            ))}
          </ul>
        ) : null}

        {link ? (
          <a
            className="inline-flex max-w-full cursor-pointer items-center gap-1 text-xs font-medium text-primary transition-colors duration-200 hover:underline"
            href={link}
            rel="noreferrer"
            target="_blank"
            title={link}
          >
            <span>{t("clinicalPanel.openSource")}</span>
            <ExternalLink className="shrink-0" size={14} />
          </a>
        ) : null}
      </CardContent>
    </Card>
  );
}

function RecommendationBlock({ title, children, tone = "default" }) {
  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2.5",
        tone === "warning" && "border-amber-500/30 bg-amber-50/80",
        tone === "default" && "border-border/70 bg-muted/15",
      )}
    >
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  );
}

function RecommendationBullets({ items }) {
  return (
    <ul className="space-y-1.5">
      {items.map((line, index) => (
        <li
          className="flex gap-2 text-sm leading-relaxed text-foreground/90"
          key={`${String(line).slice(0, 80)}-${index}`}
        >
          <span aria-hidden className="mt-[0.55rem] h-1 w-1 shrink-0 rounded-full bg-primary" />
          <span className="min-w-0 break-words [overflow-wrap:anywhere]">{line}</span>
        </li>
      ))}
    </ul>
  );
}

function RecommendationCard({ item, evidenceChunks = [], sharedVitals = [] }) {
  const { t, language } = useLanguage();
  const linkedChunks = evidenceChunks.filter((chunk) => item.evidence?.includes(chunk.chunk_id));
  const lead = recommendationLead(item);
  const detailLines = recommendationDetailLines(item, sharedVitals);
  const plainDetails = item.plain_language_details || {};
  const simplified = item.simplified || {};

  // Helper to get simplified field with fallback
  const getSimplified = (field, fallback = []) => {
    const simplifiedList = simplified[field];
    if (Array.isArray(simplifiedList) && simplifiedList.length > 0) {
      return simplifiedList.map((item) => item?.[language] || item?.vi || "").filter(Boolean);
    }
    return fallback;
  };

  // Simplified fields: use simplified_* if available, fallback to existing
  const displayDrugClass =
    simplified.drug_class_plain?.[language] ||
    simplified.drug_class_plain?.vi ||
    item.drug_class;

  const displayStatus =
    simplified.status_plain?.[language] ||
    simplified.status_plain?.vi ||
    item.status;

  const reasoningItems = getSimplified(
    "reasoning_plain",
    (plainDetails.reasoning || []).map((line) => String(line || "").trim()).filter(Boolean),
  );
  const actionItems = getSimplified(
    "action_items_plain",
    (plainDetails.next_steps || item.action_items || [])
      .map((line) => String(line || "").trim())
      .filter(Boolean),
  );
  const monitoring = getSimplified(
    "monitoring_plain",
    (plainDetails.monitoring || item.monitoring || [])
      .map((line) => String(line || "").trim())
      .filter(Boolean),
  );
  const warnings = getSimplified(
    "warnings_plain",
    (plainDetails.warnings || item.warnings || []).map((line) => String(line || "").trim()).filter(Boolean),
  );

  const displayReasoning = reasoningItems.length > 0 ? reasoningItems : detailLines;
  const plainSummary = String(item.plain_language_summary || "").trim();
  const displaySummary =
    plainSummary ||
    (language === "vi"
      ? t("clinicalPanel.summaryFallback", {
          status: titleCase(displayStatus),
          drugClass: displayDrugClass,
        })
      : lead);
  const hasStructuredDetails =
    displayReasoning.length > 0 ||
    warnings.length > 0 ||
    actionItems.length > 0 ||
    monitoring.length > 0 ||
    linkedChunks.length > 0;

  return (
    <article className="max-w-full min-w-0 space-y-3 rounded-xl border border-border/70 bg-background px-3.5 py-3.5">
      <header className="flex min-w-0 items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="text-sm font-semibold leading-snug text-foreground">{displayDrugClass}</h3>
          {displaySummary ? (
            <p className="text-sm leading-relaxed text-foreground/90 [overflow-wrap:anywhere]">
              {displaySummary}
            </p>
          ) : null}
        </div>
        <Badge className={cn("shrink-0", statusTone(displayStatus))} variant="outline">
          {titleCase(displayStatus)}
        </Badge>
      </header>

      {hasStructuredDetails ? (
        <details className="group rounded-lg border border-border/60 bg-muted/20 px-3 py-2" open={false}>
          <summary className="cursor-pointer list-none text-xs font-semibold uppercase tracking-wide text-muted-foreground marker:content-none [&::-webkit-details-marker]:hidden">
            <span className="inline-flex items-center gap-1.5">
              {t("clinicalPanel.clinicalDetails")}
              <span className="font-normal normal-case text-muted-foreground/80 group-open:hidden">
                ({t("clinicalPanel.showMore")})
              </span>
              <span className="hidden font-normal normal-case text-muted-foreground/80 group-open:inline">
                ({t("clinicalPanel.showLess")})
              </span>
            </span>
          </summary>
          <div className="mt-3 space-y-3">
            {displayReasoning.length > 0 ? (
              <RecommendationBlock title={t("clinicalPanel.clinicalReasoning")}>
                <RecommendationBullets items={displayReasoning.slice(0, 3)} />
              </RecommendationBlock>
            ) : null}

            {warnings.length > 0 ? (
              <RecommendationBlock title={t("clinicalPanel.safetyFlags")} tone="warning">
                <RecommendationBullets items={warnings.slice(0, 3)} />
              </RecommendationBlock>
            ) : null}

            {actionItems.length > 0 ? (
              <RecommendationBlock title={t("clinicalPanel.nextStep")}>
                <RecommendationBullets items={actionItems.slice(0, 3)} />
              </RecommendationBlock>
            ) : null}

            {monitoring.length > 0 ? (
              <RecommendationBlock title={t("clinicalPanel.monitor")}>
                <RecommendationBullets items={monitoring.slice(0, 3)} />
              </RecommendationBlock>
            ) : null}

            {linkedChunks.length > 0 ? (
              <RecommendationBlock title={t("clinicalPanel.linkedEvidence")}>
                <ul className="space-y-1 text-xs leading-relaxed text-muted-foreground">
                  {linkedChunks.slice(0, 2).map((chunk) => (
                    <li className="break-words [overflow-wrap:anywhere]" key={chunk.chunk_id}>
                      {evidenceDocumentTitle(chunk)}
                      {evidenceSectionLabel(chunk) ? ` — ${evidenceSectionLabel(chunk)}` : ""}
                    </li>
                  ))}
                </ul>
              </RecommendationBlock>
            ) : null}
          </div>
        </details>
      ) : null}
    </article>
  );
}

function PatientSection({ summary, attachments }) {
  const { t } = useLanguage();
  const vitals = [
    [t("clinicalPanel.vitals.lvef"), summary.lvef, "%"],
    [t("clinicalPanel.vitals.egfr"), summary.egfr, ""],
    [t("clinicalPanel.vitals.potassium"), summary.potassium, " mmol/L"],
    [t("clinicalPanel.vitals.sbp"), summary.systolicBp, " mmHg"],
    [t("clinicalPanel.vitals.hr"), summary.heartRate, " bpm"],
    [t("clinicalPanel.vitals.weight"), summary.weightKg, " kg"],
    [t("clinicalPanel.vitals.age"), summary.age, " yr"],
  ];

  return (
    <section className="min-w-0 space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {t("clinicalPanel.patient")}
      </h2>
      <div className="flex flex-wrap gap-1.5">
        {vitals.map(([label, val, unit]) => (
          <div
            className="rounded-full bg-muted/80 px-2.5 py-1 text-xs text-foreground/90"
            key={label}
          >
            <span className="text-muted-foreground">{label}</span>{" "}
            <span className="font-semibold">
              {val !== null && val !== undefined ? `${val}${unit}` : t("clinicalPanel.missing")}
            </span>
          </div>
        ))}
      </div>

      {summary.conditions.length > 0 && (
        <p className="break-words text-sm leading-relaxed">
          <span className="font-medium">{t("clinicalPanel.conditions")}</span> {summary.conditions.join(", ")}
        </p>
      )}
      {summary.medications.length > 0 && (
        <p className="break-words text-sm leading-relaxed">
          <span className="font-medium">{t("clinicalPanel.meds")}</span> {summary.medications.join(", ")}
        </p>
      )}

      {attachments?.length > 0 && (
        <div className="space-y-2">
          {attachments.map((file) => (
            <div
              className="flex min-w-0 items-start gap-2 border-t border-border/50 pt-2"
              key={`${file.file_name}-${file.mime_type}`}
            >
              <FileText className="mt-0.5 shrink-0 text-primary" size={15} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{file.file_name}</div>
                <div className="break-words text-xs text-muted-foreground">
                  {file.extracted_text
                    ? t("clinicalPanel.chars", { count: file.extracted_text.length })
                    : file.note}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function ClinicalPanel({ active, error, open, panelTab: panelTabProp, onPanelTabChange }) {
  const { t } = useLanguage();
  const summary = patientSummary(active?.draft?.patient || active?.patient);
  const evidenceChunks = active?.verification?.context?.evidence_chunks || [];
  const [internalTab, setInternalTab] = useState("clinical");
  const panelTab = panelTabProp ?? internalTab;
  const setPanelTab = onPanelTabChange ?? setInternalTab;

  useEffect(() => {
    setPanelTab("clinical");
  }, [active?.id, setPanelTab]);

  const showEvidenceTab = evidenceChunks.length > 0 || Boolean(active?.recommendation);

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-l border-border bg-secondary/30 transition-[width,opacity] duration-200",
        open ? "w-full opacity-100" : "w-0 opacity-0",
      )}
    >
      <header className="shrink-0 space-y-2 border-b border-border px-4 py-3">
        <h2 className="truncate text-sm font-semibold">{t("clinicalPanel.title")}</h2>
        {summary && (
          <p className="truncate text-xs text-muted-foreground">
            {summary.name}
            {summary.age != null ? ` · ${summary.age}` : ""}
            {summary.sex ? ` · ${summary.sex}` : ""}
          </p>
        )}
        {showEvidenceTab && summary ? (
          <div
            className="flex gap-1 rounded-lg border border-[var(--color-rule)] bg-[var(--color-paper)] p-0.5"
            role="tablist"
            aria-label={t("clinicalPanel.title")}
          >
            <button
              className={cn(
                "flex-1 cursor-pointer rounded-md px-2 py-1.5 text-xs font-medium transition-colors duration-[var(--dur-fast)]",
                panelTab === "clinical"
                  ? "bg-[var(--color-accent)] text-[var(--color-accent-ink)]"
                  : "text-muted-foreground hover:text-foreground",
              )}
              onClick={() => setPanelTab("clinical")}
              role="tab"
              aria-selected={panelTab === "clinical"}
              type="button"
            >
              {t("clinicalPanel.tabClinical")}
            </button>
            <button
              className={cn(
                "flex flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors duration-[var(--dur-fast)]",
                panelTab === "evidence"
                  ? "bg-[var(--color-accent)] text-[var(--color-accent-ink)]"
                  : "text-muted-foreground hover:text-foreground",
              )}
              onClick={() => setPanelTab("evidence")}
              role="tab"
              aria-selected={panelTab === "evidence"}
              type="button"
            >
              {t("clinicalPanel.tabEvidence")}
              {evidenceChunks.length > 0 ? (
                <Badge className="h-5 min-w-5 justify-center px-1 text-[10px]" variant="secondary">
                  {evidenceChunks.length}
                </Badge>
              ) : null}
            </button>
          </div>
        ) : null}
      </header>

      <div className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain">
        <div className="min-w-0 max-w-full space-y-6 p-4">
          {error && (
            <p className="break-words rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          {summary ? (
            <>
              {panelTab === "clinical" ? (
                <>
                  <PatientSection summary={summary} attachments={active?.attachments} />

                  {active?.recommendation && (
                    <section className="min-w-0 space-y-3">
                      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                        {t("clinicalPanel.recommendation")}
                      </h2>
                      <div
                        className={cn(
                          "flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium",
                          statusTone(active.recommendation.overall_status),
                        )}
                      >
                        <ShieldAlert className="shrink-0" size={17} />
                        <strong className="truncate">{titleCase(active.recommendation.overall_status)}</strong>
                      </div>
                      {(() => {
                        const sharedVitals = collectSharedVitalChips(
                          active.recommendation.recommendations || [],
                        );
                        return (
                          <div className="min-w-0 max-w-full space-y-3">
                            {active.recommendation.recommendations.map((item, index) => (
                              <RecommendationCard
                                evidenceChunks={evidenceChunks}
                                item={item}
                                key={recommendationCardKey(item, index)}
                                sharedVitals={sharedVitals}
                              />
                            ))}
                          </div>
                        );
                      })()}

                      {active.recommendation.medication_pathway?.length > 0 ? (
                        <>
                          <Separator />
                          <MedicationPathway pathway={active.recommendation.medication_pathway} />
                        </>
                      ) : active.recommendation.dose_plans?.length > 0 ? (
                        <>
                          <Separator />
                          <DosePlanDisplay
                            dosePlans={active.recommendation.dose_plans}
                            version={active.recommendation.dose_rules_version}
                          />
                        </>
                      ) : null}
                    </section>
                  )}
                </>
              ) : (
                <section className="min-w-0 space-y-3">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    {t("clinicalPanel.evidence")}
                  </h2>
                  {evidenceChunks.length > 0 ? (
                    <div className="min-w-0 max-w-full space-y-3">
                      {evidenceChunks.slice(0, 12).map((chunk) => (
                        <EvidenceCard chunk={chunk} key={chunk.chunk_id} />
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">{t("clinicalPanel.evidenceEmpty")}</p>
                  )}
                </section>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">{t("clinicalPanel.empty")}</p>
          )}
        </div>
      </div>
    </aside>
  );
}
