import { useState } from "react";
import { ExternalLink, FileText, ShieldAlert } from "lucide-react";
import { patientSummary, sourceLink, statusClass, titleCase } from "../utils";
import {
  evidenceSectionLabel,
  repairEvidenceText,
  shortenChunkId,
} from "@/lib/evidenceDisplay";
import {
  extractVitalChips,
  recommendationDetailLines,
  recommendationLead,
} from "@/lib/recommendationDisplay";
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

function EvidenceMeta({ label, value, mono = false, title }) {
  if (!value) return null;
  return (
    <div className="min-w-0 w-full max-w-full overflow-hidden">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-foreground/60">{label}</div>
      <div
        className={cn(
          "mt-0.5 text-xs leading-relaxed text-muted-foreground [overflow-wrap:anywhere] break-all",
          mono && "font-mono text-[11px]",
        )}
        title={title || (typeof value === "string" ? value : undefined)}
      >
        {value}
      </div>
    </div>
  );
}

function EvidenceCard({ chunk }) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(false);
  const link = sourceLink(chunk);
  const locator = chunk.metadata?.source_locator;
  const showLocator = locator && locator !== link;
  const excerpt = repairEvidenceText(chunk.text);
  const sectionLabel = evidenceSectionLabel(chunk);
  const chunkLabel = shortenChunkId(chunk.chunk_id);

  return (
    <Card className="w-full max-w-full min-w-0 gap-0 overflow-hidden border-border/80 py-0 shadow-sm">
      <CardHeader className="gap-2 space-y-0 border-b border-border/60 px-3 py-3">
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="min-w-0 flex-1 overflow-hidden">
            <CardTitle className="line-clamp-2 text-sm leading-snug">
              {titleCase(chunk.document_id)}
            </CardTitle>
            {sectionLabel && (
              <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">
                {sectionLabel}
              </p>
            )}
          </div>
          <Badge className="shrink-0" variant="secondary">
            {Math.round((chunk.quality_score ?? chunk.score ?? 0) * 100)}%
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="min-w-0 space-y-3 overflow-hidden px-3 py-3">
        {excerpt && (
          <div className="rounded-md border border-border/60 bg-background/80 px-3 py-2.5">
            <p
              className={cn(
                "text-sm leading-relaxed text-foreground/90 [overflow-wrap:anywhere] break-words",
                !expanded && "line-clamp-5",
              )}
            >
              {excerpt}
            </p>
            {excerpt.length > 220 && (
              <Button
                className="mt-2 h-7 px-2 text-xs"
                onClick={() => setExpanded((open) => !open)}
                type="button"
                variant="ghost"
              >
                {expanded ? t("clinicalPanel.showLess") : t("clinicalPanel.showMore")}
              </Button>
            )}
          </div>
        )}

        <dl className="grid min-w-0 gap-2 border-t border-border/60 pt-2">
          {chunk.chunk_id && (
            <EvidenceMeta label={t("clinicalPanel.chunk")} mono title={chunk.chunk_id} value={chunkLabel} />
          )}
          {chunk.page != null && <EvidenceMeta label={t("clinicalPanel.page")} value={String(chunk.page)} />}
          {showLocator && <EvidenceMeta label={t("clinicalPanel.source")} value={locator} />}
          {chunk.metadata?.publisher && (
            <EvidenceMeta label={t("clinicalPanel.publisher")} value={chunk.metadata.publisher} />
          )}
        </dl>

        {link && (
          <a
            className="inline-flex max-w-full items-center gap-1 text-xs text-primary hover:underline"
            href={link}
            rel="noreferrer"
            target="_blank"
            title={link}
          >
            <span>{t("clinicalPanel.openSource")}</span>
            <ExternalLink className="shrink-0" size={14} />
          </a>
        )}
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
        tone === "default" && "border-border/70 bg-muted/20",
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
    <ul className="space-y-2">
      {items.map((line) => (
        <li className="flex gap-2 text-sm leading-relaxed text-foreground/90" key={line}>
          <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
          <span className="min-w-0 break-words [overflow-wrap:anywhere]">{line}</span>
        </li>
      ))}
    </ul>
  );
}

function RecommendationCard({ item, evidenceChunks = [] }) {
  const { t } = useLanguage();
  const linkedChunks = evidenceChunks.filter((chunk) => item.evidence?.includes(chunk.chunk_id));
  const vitals = extractVitalChips(item.rationale, ...(item.clinical_reasoning || []));
  const lead = recommendationLead(item);
  const detailLines = recommendationDetailLines(item, vitals);
  const warnings = (item.warnings || []).filter(Boolean);

  return (
    <Card className="max-w-full min-w-0 gap-3 overflow-hidden border-border/80 py-3 shadow-sm">
      <CardHeader className="gap-1 space-y-0 border-b border-border/60 px-3 pb-3">
        <div className="flex min-w-0 items-start justify-between gap-2">
          <CardTitle className="min-w-0 flex-1 text-sm leading-snug">{item.drug_class}</CardTitle>
          <Badge className={cn("shrink-0", statusTone(item.status))} variant="outline">
            {titleCase(item.status)}
          </Badge>
        </div>
        {lead && (
          <p className="text-sm leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">
            {lead}
          </p>
        )}
      </CardHeader>

      <CardContent className="min-w-0 space-y-3 overflow-hidden px-3 pt-3 text-sm">
        {vitals.length > 0 && (
          <RecommendationBlock title={t("clinicalPanel.patientContext")}>
            <div className="flex flex-wrap gap-1.5">
              {vitals.map((chip) => (
                <span
                  className="rounded-md border border-border/80 bg-background px-2 py-1 text-xs font-medium text-foreground/90"
                  key={chip}
                >
                  {chip}
                </span>
              ))}
            </div>
          </RecommendationBlock>
        )}

        {detailLines.length > 0 && (
          <RecommendationBlock title={t("clinicalPanel.clinicalReasoning")}>
            <RecommendationBullets items={detailLines} />
          </RecommendationBlock>
        )}

        {warnings.length > 0 && (
          <RecommendationBlock title={t("clinicalPanel.safetyFlags")} tone="warning">
            <RecommendationBullets items={warnings.slice(0, 3)} />
          </RecommendationBlock>
        )}

        {item.action_items?.length > 0 && (
          <RecommendationBlock title={t("clinicalPanel.nextStep")}>
            <RecommendationBullets items={item.action_items.slice(0, 3)} />
          </RecommendationBlock>
        )}

        {item.monitoring?.length > 0 && (
          <RecommendationBlock title={t("clinicalPanel.monitor")}>
            <RecommendationBullets items={item.monitoring.slice(0, 3)} />
          </RecommendationBlock>
        )}

        {linkedChunks.length > 0 && (
          <RecommendationBlock title={t("clinicalPanel.linkedEvidence")}>
            <ul className="space-y-1.5 text-xs leading-relaxed text-muted-foreground">
              {linkedChunks.slice(0, 2).map((chunk) => (
                <li className="break-words [overflow-wrap:anywhere]" key={chunk.chunk_id}>
                  {titleCase(chunk.document_id)} — {chunk.section || chunk.source_type}
                </li>
              ))}
            </ul>
          </RecommendationBlock>
        )}
      </CardContent>
    </Card>
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
    <section className="min-w-0 space-y-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {t("clinicalPanel.patient")}
      </h2>
      <div className="grid grid-cols-2 gap-2">
        {vitals.map(([label, val, unit]) => (
          <div className="min-w-0 rounded-lg border border-border/80 bg-muted/30 px-3 py-2" key={label}>
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="truncate text-sm font-semibold">
              {val !== null && val !== undefined ? `${val}${unit}` : t("clinicalPanel.missing")}
            </div>
          </div>
        ))}
      </div>

      {summary.conditions.length > 0 && (
        <p className="break-words text-sm">
          <span className="font-medium">{t("clinicalPanel.conditions")}</span> {summary.conditions.join(", ")}
        </p>
      )}
      {summary.medications.length > 0 && (
        <p className="break-words text-sm">
          <span className="font-medium">{t("clinicalPanel.meds")}</span> {summary.medications.join(", ")}
        </p>
      )}

      {attachments?.length > 0 && (
        <div className="space-y-2">
          {attachments.map((file) => (
            <div
              className="flex min-w-0 items-start gap-2 rounded-lg border border-border/80 bg-background px-3 py-2"
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

export function ClinicalPanel({ active, error, open }) {
  const { t } = useLanguage();
  const summary = patientSummary(active?.draft?.patient || active?.patient);

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-l border-border bg-secondary/30 transition-[width,opacity] duration-200",
        open ? "w-full opacity-100" : "w-0 opacity-0",
      )}
    >
      <header className="shrink-0 border-b border-border px-4 py-3">
        <h2 className="truncate text-sm font-semibold">{t("clinicalPanel.title")}</h2>
        {summary && (
          <p className="truncate text-xs text-muted-foreground">
            {summary.name}
            {summary.age != null ? ` · ${summary.age}` : ""}
            {summary.sex ? ` · ${summary.sex}` : ""}
          </p>
        )}
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
                  <div className="min-w-0 max-w-full space-y-3">
                    {active.recommendation.recommendations.map((item) => (
                      <RecommendationCard
                        evidenceChunks={active.verification?.context?.evidence_chunks || []}
                        item={item}
                        key={item.drug_class}
                      />
                    ))}
                  </div>
                </section>
              )}

              {active?.verification?.context?.evidence_chunks?.length > 0 && (
                <section className="min-w-0 space-y-3">
                  <Separator />
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    {t("clinicalPanel.evidence")}
                  </h2>
                  <div className="min-w-0 max-w-full space-y-3">
                    {active.verification.context.evidence_chunks.slice(0, 4).map((chunk) => (
                      <EvidenceCard chunk={chunk} key={chunk.chunk_id} />
                    ))}
                  </div>
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
