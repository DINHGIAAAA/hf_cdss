import { humanizeToken } from "./triggerDisplay.js";

const GDMT_STATUS_LABELS = {
  consider: "Consider",
  recommend: "Recommend",
  review: "Review",
  avoid: "Avoid",
  consider_with_caution: "Consider with caution",
};

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/** Coerce LLM string or list into string[] (never split prose by character). */
export function ensureStringList(value) {
  if (value == null) return [];
  if (typeof value === "string") {
    const text = value.trim();
    return text ? [text] : [];
  }
  if (Array.isArray(value)) {
    const out = [];
    for (const item of value) {
      if (item == null) continue;
      const text = String(item).trim();
      if (text && !out.includes(text)) out.push(text);
    }
    return out;
  }
  const text = String(value).trim();
  return text ? [text] : [];
}

function formatGdmtStatus(value) {
  if (value == null || value === "") return null;
  let token = String(value).trim().toLowerCase();
  if (token.includes("|")) {
    token = token.split("|").map((part) => part.trim()).find((part) => GDMT_STATUS_LABELS[part]) || token;
  }
  return GDMT_STATUS_LABELS[token] || humanizeToken(token);
}

function mergeGuidanceLists(body = {}) {
  const guidance = isPlainObject(body.guidance) ? body.guidance : {};
  const actions = ensureStringList(guidance.actions?.length ? guidance.actions : body.actions);
  const monitoring = ensureStringList(
    guidance.monitoring?.length ? guidance.monitoring : body.monitoring,
  );
  const reasoning = ensureStringList(guidance.reasoning_base);
  return { actions, monitoring, reasoning };
}

export function isGdmtPolicyBody(body) {
  if (!isPlainObject(body)) return false;
  return (
    body.guidance != null ||
    body.hfref_default_status != null ||
    body.non_hfref_status != null ||
    Array.isArray(body.med_detection_terms)
  );
}

/** Clinician-facing fields for GDMT `policy_body` (detail panel + collapsible review). */
export function gdmtPolicyBodyToFields(body = {}) {
  const fields = [];
  const hfref = formatGdmtStatus(body.hfref_default_status);
  const nonHfref = formatGdmtStatus(body.non_hfref_status);
  if (hfref) fields.push({ label: "HFrEF default", value: hfref });
  if (nonHfref) fields.push({ label: "Non-HFrEF default", value: nonHfref });
  if (body.hfref_ef_range) {
    fields.push({ label: "EF range", value: humanizeToken(String(body.hfref_ef_range)) });
  }

  const terms = ensureStringList(body.med_detection_terms);
  if (terms.length) fields.push({ label: "Med detection terms", value: terms });

  const targets = ensureStringList(body.warning_targets);
  if (targets.length) fields.push({ label: "Warning targets", value: targets });

  const aliases = ensureStringList(body.aliases);
  if (aliases.length) fields.push({ label: "Aliases", value: aliases });

  const { reasoning, actions, monitoring } = mergeGuidanceLists(body);

  if (reasoning.length) {
    reasoning.forEach((line, i) => {
      fields.push({
        label: reasoning.length > 1 ? `Reasoning ${i + 1}` : "Reasoning",
        value: line,
        wide: true,
      });
    });
  }
  if (actions.length) {
    fields.push({ label: "Actions", value: actions, wide: actions.some((line) => line.length > 72) });
  }
  if (monitoring.length) {
    fields.push({
      label: "Monitoring",
      value: monitoring,
      wide: monitoring.some((line) => line.length > 72),
    });
  }

  return fields;
}

/** Header/detail fields for a full GDMT policy row (deduped actions/monitoring). */
export function gdmtPolicyReviewFields(policy = {}) {
  const body = policy.policy_body || {};
  const { actions, monitoring } = mergeGuidanceLists(body);
  const fields = gdmtPolicyBodyToFields(body).filter(
    (field) => field.label !== "Actions" && field.label !== "Monitoring",
  );
  if (actions.length) {
    fields.push({ label: "Actions", value: actions, wide: true });
  }
  if (monitoring.length) {
    fields.push({ label: "Monitoring", value: monitoring, wide: true });
  }
  return fields;
}
