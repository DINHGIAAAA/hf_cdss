/** Human-readable titles for governance catalog rows (list + detail).
 *
 * Keep titles short and primary-label only. Technical ids render as small
 * text under the title via CatalogRecordLabel — do not repeat them here.
 */

import { isSuspiciousDrugSetToken } from "./interactionDrugSet.js";

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
  const lower = raw.toLowerCase();
  const acronyms = {
    egfr: "eGFR",
    lvef: "LVEF",
    ckd: "CKD",
    mra: "MRA",
    acei: "ACEi",
    arni: "ARNI",
    sglt2: "SGLT2",
    bp: "BP",
  };
  if (acronyms[lower]) return acronyms[lower];
  return raw
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => {
      const partLower = part.toLowerCase();
      if (acronyms[partLower]) return acronyms[partLower];
      if (/^[A-Z0-9]+$/.test(part) && part.length <= 5) return part;
      return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
    })
    .join(" ");
}

function clipText(value, max) {
  const text = String(value || "").trim().replace(/\s+/g, " ");
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
export function humanizeCatalogSlug(id, { max = 42 } = {}) {
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

/** Compact technical id for the line under the title. */
export function shortCatalogId(id, { max = 28 } = {}) {
  const text = String(id || "");
  if (!text || text.length <= max) return text;
  const parts = text.split("_").filter(Boolean);
  const hash = parts[parts.length - 1];
  const looksHashed = /^[a-f0-9]{6,12}$/i.test(hash);
  if (looksHashed && parts.length >= 2) {
    const head = parts[0];
    return `${clipText(head, Math.max(8, max - hash.length - 2))}…${hash}`;
  }
  return `${text.slice(0, Math.max(8, max - 9))}…${text.slice(-6)}`;
}

/** Dose rules: prefer drug name; calculation stays in its own column. */
export function doseRuleTitle(rule = {}) {
  const drug = humanizeKey(usableDrugKeys(rule.drug_keys)[0] || rule.drug || "");
  if (drug) return clipText(drug, 36);
  const cls = humanizeKey(rule.drug_class || "");
  if (cls) return clipText(cls, 36);
  return humanizeCatalogSlug(rule.dose_rule_id) || "Dose rule";
}

/** Interaction list/detail: short pair label. */
export function interactionRuleTitle(rule = {}) {
  const pick = (tokens) =>
    (Array.isArray(tokens) ? tokens : [])
      .map((t) => String(t || "").trim())
      .filter((t) => t && !isSuspiciousDrugSetToken(t))[0];
  const leftKey = pick(rule.drug_set_a) || usableDrugKeys(rule.drug_set_a)[0];
  const rightKey = pick(rule.drug_set_b) || usableDrugKeys(rule.drug_set_b)[0];
  const left = leftKey ? humanizeKey(leftKey) : "";
  const right = rightKey ? humanizeKey(rightKey) : "";
  if (left && right) return clipText(`${left} ↔ ${right}`, 40);
  if (left) return clipText(left, 36);
  if (right) return clipText(right, 36);
  return humanizeCatalogSlug(rule.interaction_rule_id) || "Interaction";
}

export function formatDrugSetLabel(tokens = [], { maxItems = 2 } = {}) {
  const raw = Array.isArray(tokens) ? tokens.map((item) => String(item || "").trim()).filter(Boolean) : [];
  const plausible = raw.filter((token) => !isSuspiciousDrugSetToken(token));
  const list = usableDrugKeys(plausible.length ? plausible : raw);
  const source = list.length ? list : plausible.length ? plausible : raw;
  const items = source.slice(0, maxItems).map((token) => {
    if (isSuspiciousDrugSetToken(token)) {
      return "Partner unresolved";
    }
    return humanizeKey(token);
  }).filter(Boolean);
  if (!items.length) return "—";
  const extra = source.length - items.length;
  return clipText(extra > 0 ? `${items.join(", ")} +${extra}` : items.join(", "), 42);
}

/** Interaction `target` may be pipe-delimited risk tags, not a catalog id. */
export function formatInteractionTarget(target, { maxItems = 2 } = {}) {
  const raw = String(target || "").trim();
  if (!raw || raw === "—" || raw.toLowerCase() === "general") return "—";
  const parts = raw
    .split(/[|,;/]+/)
    .map((part) => humanizeKey(part))
    .filter(Boolean);
  if (!parts.length) return "—";
  const shown = parts.slice(0, maxItems);
  const extra = parts.length - shown.length;
  return clipText(extra > 0 ? `${shown.join(", ")} +${extra}` : shown.join(", "), 36);
}

/**
 * Constraint list/detail title: drug + action only.
 * Condition stays in detail/filters — keep the list label short and scannable.
 */
const BOILERPLATE_REASON_PREFIXES = [
  "rule generated from",
  "source advises against",
  "source states this use",
  "renal function constraint from source",
  "dose adjustment required based on source",
];

function isBoilerplateReason(reason) {
  const text = String(reason || "")
    .trim()
    .toLowerCase();
  if (!text) return true;
  return BOILERPLATE_REASON_PREFIXES.some((prefix) => text.startsWith(prefix));
}

function formatActionLabel(action) {
  return humanizeKey(String(action || "").replace(/_/g, " "));
}

function drugFromConstraintId(id) {
  const parts = String(id || "")
    .split("_")
    .filter(Boolean);
  if (!parts.length) return "";
  const head = parts[0];
  if (/^[a-f0-9]{6,}$/i.test(head)) return "";
  if (JUNK_DRUG_KEYS.has(head.toLowerCase())) return "";
  return humanizeKey(head);
}

export function constraintRuleTitle(rule = {}) {
  const drug =
    humanizeKey(rule.target_drug_class || rule.drug || usableDrugKeys(rule.drug_keys)[0] || "") ||
    drugFromConstraintId(rule.constraint_id);
  const action = formatActionLabel(rule.action);
  const reason = String(rule.reason || rule.rule_body?.reason || "").trim();

  if (drug && action) return clipText(`${drug}: ${action}`, 40);
  if (drug) return clipText(drug, 36);
  if (reason && !isBoilerplateReason(reason)) return clipText(reason, 44);
  return humanizeCatalogSlug(rule.constraint_id) || "Constraint";
}

/** Structured condition object from constraint metadata / rule body. */
export function getConstraintCondition(rule = {}) {
  let meta = rule.metadata;
  if (typeof meta === "string") {
    try {
      meta = JSON.parse(meta);
    } catch {
      meta = {};
    }
  }
  if (!meta || typeof meta !== "object") meta = {};

  const body = rule.rule_body && typeof rule.rule_body === "object" ? rule.rule_body : {};
  const candidates = [rule.condition, meta.condition, body.condition];
  for (const candidate of candidates) {
    if (typeof candidate === "string") {
      try {
        const parsed = JSON.parse(candidate);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
      } catch {
        continue;
      }
    }
    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
      return candidate;
    }
  }
  return {};
}

/** DetailFieldList rows for a constraint condition. */
export function formatConstraintConditionFields(rule = {}) {
  const condition = getConstraintCondition(rule);
  return Object.entries(condition)
    .filter(([, value]) => value != null && value !== "")
    .map(([key, value]) => {
      let display = value;
      if (value === true) display = "Yes";
      else if (value === false) display = "No";
      else if (typeof value === "object") display = JSON.stringify(value);
      else display = String(value);
      return { label: humanizeKey(key), value: display };
    });
}

/** GDMT: short display label. */
export function gdmtPolicyTitle(policy = {}) {
  if (policy.display_label) return clipText(policy.display_label, 44);
  return humanizeCatalogSlug(policy.gdmt_policy_id) || "GDMT policy";
}

/**
 * Dose safety: prefer target/drug + short cue over a long free-text message.
 */
export function doseSafetyWarningTitle(rule = {}) {
  const target = humanizeKey(rule.target || usableDrugKeys(rule.drug_keys)[0] || "");
  const message = String(rule.rule_body?.message || rule.message || "").trim();
  if (target && message) {
    const cue = clipText(message, 28);
    return clipText(`${target}: ${cue}`, 44);
  }
  if (message) return clipText(message, 44);
  if (target) return clipText(target, 36);
  return humanizeCatalogSlug(rule.dose_safety_warning_id) || "Safety warning";
}
