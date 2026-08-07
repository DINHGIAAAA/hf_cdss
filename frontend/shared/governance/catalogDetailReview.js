import { humanizeEvidenceRef, normalizeClinicalSourceItem } from "./clinicalReviewDisplay.js";

export function normalizeReviewText(text) {
  return String(text || "")
    .trim()
    .replace(/\s+/g, " ");
}

/** Distinct evidence quotes already shown under Clinical sources. */
export function clinicalSourceEvidenceTexts(sources = []) {
  const seen = new Set();
  const out = [];
  for (const src of sources) {
    const normalized = normalizeClinicalSourceItem(src);
    const quote = normalizeReviewText(normalized.evidence);
    if (quote && !seen.has(quote)) {
      seen.add(quote);
      out.push(quote);
    }
  }
  return out;
}

export function textMatchesClinicalSources(text, sources = []) {
  const normalized = normalizeReviewText(text);
  if (!normalized) return false;
  return clinicalSourceEvidenceTexts(sources).includes(normalized);
}

/** Drop prose fields that repeat clinical_sources[].evidence in review panels. */
export function omitDuplicateReviewFields(data, sources = [], keys = ["message", "reason", "evidence"]) {
  if (data == null || typeof data !== "object" || Array.isArray(data)) return data;
  if (!sources.length) return data;
  const out = { ...data };
  for (const key of keys) {
    if (out[key] != null && textMatchesClinicalSources(out[key], sources)) {
      delete out[key];
    }
  }
  return out;
}

/** Top-level evidence_ref only when there is no clinical_sources block. */
export function evidenceLinkDetailField(evidenceRef, sources = []) {
  if (!evidenceRef || sources.length > 0) return null;
  const label = humanizeEvidenceRef(evidenceRef);
  return {
    label: "Evidence link",
    value: label,
    wide: label.length > 72,
  };
}

export function pipelineSourceDetailField(source) {
  if (!source || source === "pipeline_generated") return null;
  return { label: "Source", value: source };
}
