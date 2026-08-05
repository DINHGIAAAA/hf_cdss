import { reviewPayloadToFields, sanitizeValueForReview } from "./reviewFieldFilter.js";
import { normalizeClinicalSourceItem } from "./clinicalReviewDisplay.js";
import { omitDuplicateReviewFields } from "./catalogDetailReview.js";
import { doseSafetyRuleBodyToFields, isDoseSafetyStyleRuleBody } from "./ruleBodyReview.js";
import { gdmtPolicyBodyToFields, isGdmtPolicyBody } from "./gdmtPolicyReview.js";
import { shortCatalogId } from "./displayNames.js";

/**
 * Stacked label/value fields for narrow detail panels.
 * Prefer this over a cramped two-column dl grid.
 * Comma-separated token lists and string arrays render as badges.
 */

function looksLikeTokenList(text) {
  const parts = String(text)
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length < 2) return null;
  // Avoid splitting prose sentences.
  if (parts.some((part) => part.length > 48 || /[.!?]/.test(part))) return null;
  return parts;
}

function valueBadges(value) {
  if (Array.isArray(value)) {
    const chips = value.map((item) => String(item).trim()).filter(Boolean);
    if (chips.length < 2) return null;
    // Keep prose / long phrases as plain text, not badges.
    if (chips.some((part) => part.length > 48 || /[.!?]/.test(part))) return null;
    return chips;
  }
  if (typeof value === "string") return looksLikeTokenList(value);
  return null;
}

function FieldValue({ value }) {
  if (value == null || value === "") return "—";

  // Already a React node (e.g. <code>...</code>)
  if (typeof value === "object" && !Array.isArray(value)) {
    return value;
  }

  const badges = valueBadges(value);
  if (badges) {
    return (
      <div className="detail-field-badges">
        {badges.map((badge) => (
          <span className="detail-field-badge" key={badge}>
            {badge}
          </span>
        ))}
      </div>
    );
  }

  if (Array.isArray(value)) {
    const text = value.map((item) => String(item)).filter(Boolean).join(", ");
    return text || "—";
  }

  return value;
}

export function DetailFieldList({ fields = [], className = "" }) {
  const visible = fields.filter((field) => field && field.hide !== true);
  if (!visible.length) return null;

  return (
    <dl className={`detail-fields ${className}`.trim()}>
      {visible.map((field) => {
        const badges = valueBadges(field.value);
        return (
          <div className={`detail-field${field.wide ? " detail-field--wide" : ""}`} key={field.label}>
            <dt>{field.label}</dt>
            <dd className={field.mono && !badges ? "detail-field-mono" : undefined}>
              <FieldValue value={field.value} />
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function clinicalSourceTitle(src, meta) {
  return (
    src.title ||
    meta.title ||
    src.source_section ||
    meta.section ||
    src.document_id ||
    meta.source_id ||
    src.claim_id ||
    "Source"
  );
}

export function ClinicalSourcesList({ sources = [] }) {
  if (!sources.length) return null;

  return (
    <section className="detail-section">
      <h3>Clinical sources</h3>
      <ul className="source-list">
        {sources.map((src, i) => {
          const normalized = normalizeClinicalSourceItem(src);
          const meta = isPlainObject(src.metadata) ? src.metadata : {};
          const title =
            normalized.title ||
            normalized.label_reference ||
            clinicalSourceTitle(src, meta);
          const fields = [
            { label: "Quote", value: normalized.evidence, wide: true },
            { label: "Section", value: normalized.section || src.source_section || meta.section },
            { label: "Type", value: src.source_type || meta.source_type },
            { label: "Publisher", value: meta.publisher },
          ].filter((field) => field.value != null && field.value !== "");
          const link = normalized.source_link || src.source_url || src.source_locator;

          return (
            <li key={src.claim_id || src.source_url || src.document_id || i}>
              <strong className="source-title">{title}</strong>
              {fields.length ? <DetailFieldList className="source-fields" fields={fields} /> : null}
              {link ? (
                <a className="source-link" href={link} rel="noreferrer" target="_blank">
                  Open source
                </a>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function DetailMetaRow({ id, version, status, statusClassName, badges = [] }) {
  return (
    <div className="detail-meta-row">
      {status ? <span className={`badge ${statusClassName || ""}`.trim()}>{status}</span> : null}
      {badges.map((badge) => (
        <span className={`badge ${badge.className || ""}`.trim()} key={`${badge.label}-${badge.className || ""}`}>
          {badge.label}
        </span>
      ))}
      {version != null ? <span className="detail-meta-chip">v{version}</span> : null}
      {id ? (
        <code className="detail-meta-id" title={id}>
          {shortCatalogId(id)}
        </code>
      ) : null}
    </div>
  );
}

/** Structured payload for review (no raw ids/hashes). Defaults to open in detail modals. */
export function CollapsiblePayload({
  title = "Full payload",
  data,
  defaultOpen = true,
  reviewMode = true,
  clinicalSources = [],
}) {
  if (data == null) return null;

  if (reviewMode) {
    const deduped =
      clinicalSources.length > 0 ? omitDuplicateReviewFields(data, clinicalSources) : data;
    const cleaned = sanitizeValueForReview(deduped);
    const fields = isDoseSafetyStyleRuleBody(cleaned)
      ? doseSafetyRuleBodyToFields(cleaned)
      : isGdmtPolicyBody(cleaned)
        ? gdmtPolicyBodyToFields(cleaned)
        : reviewPayloadToFields(cleaned);
    if (!fields.length) return null;
    return (
      <details className="payload-details" defaultOpen={defaultOpen}>
        <summary className="payload-details-summary">{title}</summary>
        <DetailFieldList className="source-fields payload-review-fields" fields={fields} />
      </details>
    );
  }

  return (
    <details className="payload-details" defaultOpen={defaultOpen}>
      <summary className="payload-details-summary">{title}</summary>
      <pre className="dose-json-block">{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}
