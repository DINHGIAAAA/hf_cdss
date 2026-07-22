/** Human-readable titles for governance catalog rows (list + detail).
 *
 * Keep titles to the primary label only — do not repeat values that already
 * have their own table columns (action, calculation, drug sets, …).
 */

const JUNK_DRUG_KEYS = new Set([
  "generic_name",
  "brand_if_stated",
  "brand_name",
  "drug",
  "drug_key",
  "drug_keys",
  "name",
  "unknown",
  "n/a",
  "na",
  "none",
]);

function titleCaseToken(token) {
  const raw = String(token || "").replace(/^class:/i, "").trim();
  if (!raw) return "";
  return raw
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => {
      if (/^[A-Z0-9]+$/.test(part) && part.length <= 5) return part;
      return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
    })
    .join(" ");
}

function clipText(value, max) {
  const text = String(value || "").trim();
  if (!text) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

function usableDrugKeys(keys = []) {
  return (Array.isArray(keys) ? keys : [])
    .map((key) => String(key || "").trim())
    .filter((key) => key && !JUNK_DRUG_KEYS.has(key.toLowerCase()));
}

/** Turn catalog slug into a readable title (drop trailing hash when present). */
export function humanizeCatalogSlug(id, { max = 56 } = {}) {
  const text = String(id || "").trim();
  if (!text) return "";
  const parts = text.split("_").filter(Boolean);
  if (!parts.length) return "";
  const hash = parts[parts.length - 1];
  if (/^[a-f0-9]{6,12}$/i.test(hash) && parts.length >= 2) {
    parts.pop();
  }
  return clipText(parts.map((part) => titleCaseToken(part)).join(" "), max);
}

export function humanizeKey(value) {
  return titleCaseToken(value);
}

export function shortCatalogId(id, { max = 40 } = {}) {
  const text = String(id || "");
  if (!text || text.length <= max) return text;
  const parts = text.split("_").filter(Boolean);
  const hash = parts[parts.length - 1];
  const looksHashed = /^[a-f0-9]{6,12}$/i.test(hash);
  if (looksHashed && parts.length >= 3) {
    const head = parts.slice(0, Math.min(3, parts.length - 1)).join("_");
    return `${head}…_${hash}`;
  }
  return `${text.slice(0, max - 10)}…${text.slice(-8)}`;
}

/** Dose rules: Calculation + Drugs are separate columns. */
export function doseRuleTitle(rule = {}) {
  const drug = humanizeKey(usableDrugKeys(rule.drug_keys)[0] || rule.drug || "");
  if (drug) return drug;
  return humanizeCatalogSlug(rule.dose_rule_id) || shortCatalogId(rule.dose_rule_id);
}

/** Interaction detail header: keep pair with arrow. List uses two columns instead. */
export function interactionRuleTitle(rule = {}) {
  const left = usableDrugKeys(rule.drug_set_a).slice(0, 2).map(humanizeKey).filter(Boolean).join(", ");
  const right = usableDrugKeys(rule.drug_set_b).slice(0, 2).map(humanizeKey).filter(Boolean).join(", ");
  if (left && right) return `${left} ↔ ${right}`;
  if (left) return left;
  if (right) return right;
  return humanizeCatalogSlug(rule.interaction_rule_id) || shortCatalogId(rule.interaction_rule_id);
}

export function formatDrugSetLabel(tokens = [], { maxItems = 3 } = {}) {
  const list = usableDrugKeys(tokens);
  const fallback = Array.isArray(tokens)
    ? tokens.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const source = list.length ? list : fallback;
  const items = source.slice(0, maxItems).map(humanizeKey).filter(Boolean);
  if (!items.length) return "—";
  const extra = source.length - items.length;
  return extra > 0 ? `${items.join(", ")} +${extra}` : items.join(", ");
}

/** Interaction `target` may be pipe-delimited risk tags, not a catalog id. */
export function formatInteractionTarget(target, { maxItems = 3 } = {}) {
  const raw = String(target || "").trim();
  if (!raw || raw === "—" || raw.toLowerCase() === "general") return "—";
  const parts = raw
    .split(/[|,;/]+/)
    .map((part) => humanizeKey(part))
    .filter(Boolean);
  if (!parts.length) return "—";
  const shown = parts.slice(0, maxItems);
  const extra = parts.length - shown.length;
  return extra > 0 ? `${shown.join(", ")} +${extra}` : shown.join(", ");
}

/** Constraint rules: Action is a separate column. */
export function constraintRuleTitle(rule = {}) {
  const drug = humanizeKey(rule.target_drug_class || rule.drug || "");
  if (drug) return drug;
  const reason = String(rule.reason || rule.rule_body?.reason || "").trim();
  if (reason) return clipText(reason, 56);
  return humanizeCatalogSlug(rule.constraint_id) || shortCatalogId(rule.constraint_id);
}

/** GDMT: display_label is the canonical name; class key is its own column. */
export function gdmtPolicyTitle(policy = {}) {
  if (policy.display_label) return String(policy.display_label);
  return humanizeCatalogSlug(policy.gdmt_policy_id) || shortCatalogId(policy.gdmt_policy_id);
}

/** Dose safety: Drug keys column exists; prefer short clinical message. */
export function doseSafetyWarningTitle(rule = {}) {
  const message = String(rule.rule_body?.message || rule.message || "").trim();
  if (message) return clipText(message, 56);
  const target = humanizeKey(rule.target || usableDrugKeys(rule.drug_keys)[0] || "");
  if (target) return target;
  return (
    humanizeCatalogSlug(rule.dose_safety_warning_id) || shortCatalogId(rule.dose_safety_warning_id)
  );
}
