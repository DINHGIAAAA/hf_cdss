/** Human labels for governance diff field paths. */
const FIELD_LABELS = {
  action: "Action",
  reason: "Reason",
  target_drug_class: "Target class",
  risk_names: "Risks",
  severity_any: "Severity any",
  evidence_ref: "Evidence",
  clinical_sources: "Clinical sources",
  metadata: "Metadata",
  calculation_type: "Calculation",
  drug_class: "Drug class",
  drug_keys: "Drug keys",
  rule_body: "Rule body",
  safety_tier: "Safety tier",
  drug_set_a: "Drug set A",
  drug_set_b: "Drug set B",
  severity: "Severity",
  target: "Target",
  drug_class_key: "Class key",
  display_label: "Display label",
  sort_order: "Sort order",
  policy_body: "Policy body",
  default_severity: "Default severity",
  message: "Message",
  monitoring: "Monitoring",
  escalation: "Escalation",
  guidance: "Guidance",
  actions: "Actions",
  extraction_method: "Extraction method",
  source_type: "Source type",
  source_section: "Source section",
  document_id: "Document",
  claim_id: "Claim ID",
  evidence: "Evidence quote",
  title: "Title",
  source_url: "Source URL",
  confidence: "Confidence",
  publisher: "Publisher",
  chunk_id: "Chunk ID",
  source_id: "Source ID",
  document: "Document",
};

function humanizeKey(key) {
  if (FIELD_LABELS[key]) return FIELD_LABELS[key];
  if (/^\d+$/.test(String(key))) return `Item #${Number(key) + 1}`;
  return String(key)
    .replace(/_/g, " ")
    .replace(/\./g, " › ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

/** Humanized path segments for separate field sub-columns. */
export function fieldPathParts(path) {
  if (!path) return ["Field"];
  return String(path)
    .split(".")
    .filter(Boolean)
    .map((part) => humanizeKey(part));
}

export function formatFieldPath(path) {
  return fieldPathParts(path).join(" · ");
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function serializeComparable(value) {
  return JSON.stringify(value ?? null);
}

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

function entryForScalar(prefix, text) {
  const chips = looksLikeTokenList(text);
  if (chips) return { label: prefix || null, text: chips.join(", "), chips };
  return { label: prefix || null, text: String(text) };
}

/**
 * Turn any diff value into labeled text rows (no raw JSON dump).
 * Multi-value lists become chips for readable badges in the UI.
 */
export function valueToEntries(value, { prefix = "" } = {}) {
  if (value === undefined || value === null || value === "") {
    return [{ label: prefix || null, text: "—" }];
  }

  if (typeof value === "boolean" || typeof value === "number") {
    return [{ label: prefix || null, text: String(value) }];
  }

  if (typeof value === "string") {
    return [entryForScalar(prefix, value)];
  }

  if (Array.isArray(value)) {
    if (!value.length) return [{ label: prefix || null, text: "—" }];
    if (value.every((item) => item == null || ["string", "number", "boolean"].includes(typeof item))) {
      const chips = value.map((item) => String(item)).filter(Boolean);
      return [{ label: prefix || null, text: chips.join(", "), chips }];
    }
    return value.flatMap((item, index) => {
      const label = prefix ? `${prefix} #${index + 1}` : `Item #${index + 1}`;
      if (isPlainObject(item)) {
        return valueToEntries(item, { prefix: label });
      }
      return [entryForScalar(label, String(item))];
    });
  }

  if (isPlainObject(value)) {
    const keys = Object.keys(value);
    if (!keys.length) return [{ label: prefix || null, text: "—" }];
    return keys.flatMap((key) => {
      const label = prefix ? `${prefix} · ${humanizeKey(key)}` : humanizeKey(key);
      const child = value[key];
      if (isPlainObject(child) || Array.isArray(child)) {
        return valueToEntries(child, { prefix: label });
      }
      if (child === undefined || child === null || child === "") {
        return [{ label, text: "—" }];
      }
      return [entryForScalar(label, String(child))];
    });
  }

  return [{ label: prefix || null, text: String(value) }];
}

function changeTypeFor(before, after) {
  if (before == null && after != null) return "added";
  if (before != null && after == null) return "removed";
  if (serializeComparable(before) === serializeComparable(after)) return "unchanged";
  return "modified";
}

/**
 * Recursively expand object/array diffs into leaf rows so nested values
 * (e.g. clinical_sources[0].metadata.title) each get their own table row.
 */
function expandValueDiff(path, before, after) {
  const type = changeTypeFor(before, after);
  if (type === "unchanged") return [];

  const beforeObj = isPlainObject(before);
  const afterObj = isPlainObject(after);
  if ((beforeObj || afterObj) && !Array.isArray(before) && !Array.isArray(after)) {
    const keys = new Set([
      ...Object.keys(beforeObj ? before : {}),
      ...Object.keys(afterObj ? after : {}),
    ]);
    const nested = [];
    for (const key of keys) {
      nested.push(
        ...expandValueDiff(
          `${path}.${key}`,
          beforeObj ? before[key] : undefined,
          afterObj ? after[key] : undefined,
        ),
      );
    }
    if (nested.length) return nested;
  }

  const beforeArr = Array.isArray(before);
  const afterArr = Array.isArray(after);
  if (beforeArr || afterArr) {
    const left = beforeArr ? before : [];
    const right = afterArr ? after : [];
    const hasObjectItems =
      left.some((item) => isPlainObject(item)) || right.some((item) => isPlainObject(item));

    if (hasObjectItems) {
      const nested = [];
      const len = Math.max(left.length, right.length);
      for (let index = 0; index < len; index += 1) {
        nested.push(...expandValueDiff(`${path}.${index}`, left[index], right[index]));
      }
      if (nested.length) return nested;
    }

    // Scalar / chip lists stay as a single row.
    return [{ path, change_type: type, before, after }];
  }

  return [{ path, change_type: type, before, after }];
}

/**
 * Expand top-level object/array diffs into per-key rows so reviewers see
 * readable fields instead of one giant JSON blob.
 */
export function expandDiffChanges(changes = []) {
  const expanded = [];
  for (const change of changes) {
    expanded.push(...expandValueDiff(change.path, change.before, change.after));
  }
  return expanded;
}
