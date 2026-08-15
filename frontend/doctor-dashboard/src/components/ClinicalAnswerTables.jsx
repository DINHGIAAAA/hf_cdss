import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { MedicationPathway } from "@/components/MedicationPathway";
import { cn } from "@/lib/utils";
import { titleCase } from "@/utils";

function clip(text, max = 200) {
  const value = String(text || "").trim();
  if (!value) return "";
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1).trim()}…`;
}

function statusTone(status) {
  if (status === "avoid" || status === "blocked") {
    return "bg-destructive/10 text-destructive";
  }
  if (status === "consider_with_caution") {
    return "bg-amber-50 text-amber-800";
  }
  if (status === "continue") {
    return "bg-emerald-50 text-emerald-800";
  }
  return "bg-muted text-foreground";
}

function DataTable({ caption, headers, rows }) {
  if (!rows?.length) return null;
  return (
    <figure className="min-w-0 overflow-hidden rounded-lg border border-border/80">
      {caption ? (
        <figcaption className="border-b border-border/70 bg-muted/40 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {caption}
        </figcaption>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[260px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border/60 bg-background/80">
              {headers.map((header) => (
                <th
                  className="px-3 py-2 text-xs font-semibold text-muted-foreground"
                  key={header}
                  scope="col"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr className="border-b border-border/40 last:border-0" key={row.key}>
                {row.cells.map((cell, cellIndex) => (
                  <td
                    className="max-w-[18rem] px-3 py-2 align-top text-foreground/90 [overflow-wrap:anywhere]"
                    key={`${row.key}-${cellIndex}`}
                    title={cell.title || undefined}
                  >
                    {cell.content}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

function groupByStatus(items) {
  const groups = { avoid: [], consider_with_caution: [], consider: [], continue: [] };
  for (const item of items) {
    const key = item.status in groups ? item.status : "consider";
    groups[key].push(item);
  }
  return groups;
}

function collectBullets(items, limit = 4) {
  const lines = [];
  for (const item of items || []) {
    for (const raw of [
      ...(item.simplified_monitoring || []),
      ...(item.monitoring || []),
    ]) {
      const text = String(raw || "").trim();
      if (!text || text.length < 12) continue;
      if (lines.includes(text)) continue;
      lines.push(text);
      if (lines.length >= limit) return lines;
    }
  }
  return lines;
}

/** Prose + tables only for GDMT matrix and dose plans. */
export function ClinicalStructuredAnswer({ recommendation, verification, focusClassIds }) {
  const { t } = useLanguage();
  if (!recommendation) return null;

  const allItems = recommendation.recommendations || [];
  const hasFocus = Boolean(focusClassIds?.length);
  // Clinician asked about a specific class (e.g. "MRA dose") — only show
  // that class's row, not the full unrelated GDMT checklist.
  const items = hasFocus
    ? allItems.filter((item) => focusClassIds.includes((item.class_id || "").toLowerCase()))
    : allItems;
  const allPathway = recommendation.medication_pathway || [];
  const pathway = hasFocus
    ? allPathway.filter((step) => focusClassIds.includes((step.class_id || "").toLowerCase()))
    : allPathway;

  if (hasFocus && items.length === 0 && pathway.length === 0) return null;

  const summary = recommendation.patient_summary || {};
  const groups = groupByStatus(items);
  const evidenceCount = verification?.context?.evidence_chunks?.length || 0;

  const conclusionParts = [];
  if (groups.avoid.length) {
    conclusionParts.push(
      t("clinicalAnswer.conclusionAvoid", {
        drugs: groups.avoid.map((i) => i.drug_class).join(", "),
      }),
    );
  }
  if (groups.consider_with_caution.length) {
    conclusionParts.push(
      t("clinicalAnswer.conclusionCaution", {
        drugs: groups.consider_with_caution.map((i) => i.drug_class).join(", "),
      }),
    );
  }
  if (groups.consider.length) {
    conclusionParts.push(
      t("clinicalAnswer.conclusionConsider", {
        drugs: groups.consider.map((i) => i.drug_class).join(", "),
      }),
    );
  }
  if (groups.continue.length) {
    conclusionParts.push(
      t("clinicalAnswer.conclusionContinue", {
        drugs: groups.continue.map((i) => i.drug_class).join(", "),
      }),
    );
  }

  const vitals = [
    summary.lvef != null ? `LVEF ${summary.lvef}%` : null,
    summary.egfr != null ? `eGFR ${summary.egfr}` : null,
    summary.potassium != null ? `K+ ${summary.potassium}` : null,
    summary.sbp != null ? `SBP ${summary.sbp} mmHg` : null,
    summary.heart_rate != null ? `HR ${summary.heart_rate} bpm` : null,
  ].filter(Boolean);

  const gdmtRows = items.map((item) => {
    const summaryText =
      item.plain_language_summary ||
      item.simplified_rationale ||
      item.rationale ||
      "";
    return {
      key: item.class_id || item.drug_class,
      cells: [
        { content: <span className="font-medium">{item.drug_class}</span> },
        {
          content: (
            <span
              className={cn(
                "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                statusTone(item.status),
              )}
            >
              {titleCase(item.status?.replace(/_/g, " ") || "—")}
            </span>
          ),
        },
        {
          content: clip(summaryText) || "—",
          title: summaryText,
        },
      ],
    };
  });

  const constraints = (recommendation.constraints || [])
    .filter((c) => {
      const target = (c.target_drug_class || "").toLowerCase();
      return items.some(
        (item) =>
          target.includes((item.class_id || "").replace(/_/g, " ")) ||
          target === item.class_id ||
          target.includes(item.drug_class?.toLowerCase() || ""),
      );
    })
    .slice(0, 4);
  const monitoring = collectBullets(items);

  return (
    <div className="aui-clinical-structured-answer space-y-4 text-sm leading-relaxed">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium",
            statusTone(recommendation.overall_status),
          )}
        >
          {titleCase(recommendation.overall_status?.replace(/_/g, " ") || "—")}
        </span>
        {evidenceCount > 0 ? (
          <span className="text-xs text-muted-foreground">
            {t("clinicalAnswer.evidenceCount", { count: evidenceCount })}
          </span>
        ) : null}
      </div>

      {conclusionParts.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t("clinicalAnswer.conclusionHeading")}
          </h3>
          {conclusionParts.map((line) => (
            <p className="text-foreground/90" key={line}>
              {line}
            </p>
          ))}
        </section>
      ) : null}

      {vitals.length > 0 ? (
        <p className="text-foreground/85">
          <span className="font-medium text-muted-foreground">{t("clinicalAnswer.vitalsInline")}: </span>
          {vitals.join(" · ")}
        </p>
      ) : null}

      {gdmtRows.length > 0 ? (
        <DataTable
          caption={t("clinicalAnswer.gdmtTable")}
          headers={[
            t("clinicalAnswer.colClass"),
            t("clinicalAnswer.colStatus"),
            t("clinicalAnswer.colSummary"),
          ]}
          rows={gdmtRows}
        />
      ) : null}

      {pathway.length > 0 ? <MedicationPathway pathway={pathway} /> : null}

      {constraints.length > 0 ? (
        <section className="space-y-1.5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t("clinicalAnswer.constraintsHeading")}
          </h3>
          <ul className="list-disc space-y-1 pl-5 text-foreground/90">
            {constraints.map((c) => (
              <li key={c.constraint_id || c.reason}>
                <span className="font-medium">{c.target_drug_class}</span>
                {c.reason ? ` — ${clip(c.reason, 280)}` : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {monitoring.length > 0 ? (
        <section className="space-y-1.5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t("clinicalAnswer.monitoringHeading")}
          </h3>
          <ul className="list-disc space-y-1 pl-5 text-foreground/90">
            {monitoring.map((line) => (
              <li key={line}>{clip(line, 320)}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="text-xs text-muted-foreground">{t("clinicalAnswer.disclaimer")}</p>
    </div>
  );
}

/** Pathway below LLM prose (replaces flat dose table). */
export function ClinicalDoseTable({ recommendation }) {
  const pathway = recommendation?.medication_pathway;
  if (!pathway?.length) return null;
  return <MedicationPathway pathway={pathway} />;
}
