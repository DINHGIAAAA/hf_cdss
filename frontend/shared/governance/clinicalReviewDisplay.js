/**
 * Make governance diff values readable for clinicians (not pipeline ids).
 */

import { humanizeCatalogSlug } from "./displayNames.js";

const GENERIC_TITLES = /^drug_label evidence$/i;

function drugTokenFromChunkRef(ref) {
  const text = String(ref || "").trim();
  if (!text) return "";
  const head = text.split("__")[0];
  return head ? humanizeCatalogSlug(head, { max: 48 }) : "";
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function formatSectionSlug(sectionSlug) {
  const raw = String(sectionSlug || "").trim();
  if (!raw) return "Section";
  // Guideline headings often slug as 5_2_topic → §5.2 Topic
  const numbered = raw.match(/^(\d+)_(\d+)_(.+)$/);
  if (numbered) {
    const topic = humanizeCatalogSlug(numbered[3], { max: 72 });
    return `§${numbered[1]}.${numbered[2]} ${topic}`.trim();
  }
  return humanizeCatalogSlug(raw, { max: 72 });
}

/** chunk_id: `{document}__{section}__{index:04d}__{sha1}` (see scraper/transform/chunk_sections.py). */
function parseChunkEvidenceRef(text) {
  const parts = String(text || "")
    .split("__")
    .filter(Boolean);
  if (parts.length < 2) return null;

  const doc = parts[0];
  const last = parts[parts.length - 1];
  const penultimate = parts[parts.length - 2];

  if (
    parts.length >= 4 &&
    /^\d{4}$/.test(penultimate) &&
    /^[a-f0-9]{6,12}$/i.test(last)
  ) {
    return {
      doc,
      sectionSlug: parts[1],
      chunkIndex: Number.parseInt(penultimate, 10),
    };
  }

  if (parts.length === 3 && /^[a-f0-9]{6,12}$/i.test(last)) {
    return { doc, sectionSlug: parts[1], chunkIndex: null };
  }

  return {
    doc,
    sectionSlug: parts.slice(1, -1).join("_") || parts[1] || "",
    chunkIndex: null,
  };
}

/** Turn chunk/evidence_ref into a short label (drug + section), not a hash id. */
export function humanizeEvidenceRef(ref) {
  const text = String(ref || "").trim();
  if (!text) return "—";

  if (/^rule:/i.test(text)) {
    const slug = text.replace(/^rule:/i, "").replace(/_[a-f0-9]{6,}$/i, "");
    const label = humanizeCatalogSlug(slug, { max: 48 });
    return `Pipeline anchor for “${label}” — the clinical quote is under Clinical sources, not this id.`;
  }

  if (/^(week\d+_rule|constraint|risk|policy|warning|interaction_rule|dose_safety_warning):/i.test(text)) {
    return "Internal catalog reference — see Clinical sources for the quoted evidence.";
  }

  if (/^claim:/i.test(text) || /^fda_label:/i.test(text)) {
    const tail = text.split(":").slice(1).join(" · ");
    return humanizeCatalogSlug(tail.replace(/_/g, " "), { max: 72 }) || text;
  }

  if (!text.includes("__")) {
    // Long prose was sometimes stored in evidence_ref in older rows; show as-is.
    if (text.length > 120 || /\s{1,}/.test(text)) return text;
    return text;
  }

  const parsed = parseChunkEvidenceRef(text);
  if (!parsed) return humanizeCatalogSlug(text, { max: 80 });

  const docLabel = humanizeCatalogSlug(parsed.doc, { max: 40 });
  const sectionLabel = formatSectionSlug(parsed.sectionSlug);
  const chunkNote =
    parsed.chunkIndex != null && !Number.isNaN(parsed.chunkIndex)
      ? ` (chunk ${parsed.chunkIndex + 1} in section)`
      : "";

  return `${docLabel} — ${sectionLabel}${chunkNote}`;
}

export function normalizeClinicalSourceItem(src) {
  if (!isPlainObject(src)) return src;
  const meta = isPlainObject(src.metadata) ? src.metadata : {};
  const evidence =
    src.evidence ||
    meta.evidence ||
    src.evidence_quote ||
    meta.evidence_quote ||
    null;
  const locator = src.source_locator || src.source_url || meta.source_locator || meta.source_url;
  const section = src.source_section || meta.section || meta.source_section;
  const title = src.title || meta.title;
  const out = {};
  if (evidence) out.evidence = String(evidence).trim();
  if (section) out.section = section;
  if (locator) out.source_link = locator;
  if (title && !GENERIC_TITLES.test(String(title))) out.title = title;
  if (!out.evidence && src.chunk_id) {
    out.label_reference = humanizeEvidenceRef(src.chunk_id);
  }
  if (!Object.keys(out).length && src.chunk_id) {
    return { label_reference: humanizeEvidenceRef(src.chunk_id) };
  }
  return out;
}

export function normalizeReviewDiffValue(path, value) {
  if (value == null) return value;
  const p = String(path || "");

  if (p === "evidence_ref" || p.endsWith(".evidence_ref")) {
    return humanizeEvidenceRef(value);
  }

  if (p === "reason" && typeof value === "string") {
    const trimmed = value.trim();
    if (/^rule generated from structured source claim$/i.test(trimmed)) {
      return "— (generic pipeline text; see clinical sources)";
    }
  }

  if (p === "clinical_sources" || p.includes("clinical_sources")) {
    if (Array.isArray(value)) {
      return value.map((item) => normalizeClinicalSourceItem(item)).filter((item) => {
        if (!isPlainObject(item)) return Boolean(item);
        return Object.keys(item).length > 0;
      });
    }
    if (isPlainObject(value)) {
      return normalizeClinicalSourceItem(value);
    }
  }

  if (Array.isArray(value)) {
    return value.map((item, index) => normalizeReviewDiffValue(`${p}.${index}`, item));
  }

  if (isPlainObject(value)) {
    const out = {};
    for (const [key, child] of Object.entries(value)) {
      const childPath = p ? `${p}.${key}` : key;
      const normalized = normalizeReviewDiffValue(childPath, child);
      if (normalized != null && !(isPlainObject(normalized) && !Object.keys(normalized).length)) {
        out[key] = normalized;
      }
    }
    return out;
  }

  return value;
}

function drugFromEvidenceRef(ref) {
  return String(ref || "").split("__")[0]?.toLowerCase() || "";
}

/**
 * Warn when version diff compares unrelated clinical subjects (same constraint_id, different drug).
 */
export function diffClinicalIdentityWarning(changes = []) {
  let beforeRef = null;
  let afterRef = null;
  let beforeClass = null;
  let afterClass = null;

  for (const change of changes) {
    const path = change.path || "";
    if (path === "evidence_ref") {
      beforeRef = change.before;
      afterRef = change.after;
    }
    if (path === "target_drug_class") {
      beforeClass = change.before;
      afterClass = change.after;
    }
    if (path.startsWith("clinical_sources") && path.includes("chunk_id")) {
      if (change.before) beforeRef = change.before;
      if (change.after) afterRef = change.after;
    }
  }

  const beforeDrug = drugFromEvidenceRef(beforeRef);
  const afterDrug = drugFromEvidenceRef(afterRef);
  if (beforeDrug && afterDrug && beforeDrug !== afterDrug) {
    return {
      tone: "warning",
      message: `These versions cite different drugs (${humanizeCatalogSlug(beforeDrug)} vs ${humanizeCatalogSlug(afterDrug)}). The version number is an administrative record for the same rule id — not a clinical update to one patient scenario. Compare each version on its own merits.`,
    };
  }

  if (
    beforeClass &&
    afterClass &&
    String(beforeClass).toLowerCase() !== String(afterClass).toLowerCase()
  ) {
    return {
      tone: "warning",
      message: `Target drug class changed (${beforeClass} → ${afterClass}). Treat this as a catalog replacement, not a dose tweak.`,
    };
  }

  return null;
}
