function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function humanizeToken(key) {
  const acronyms = { egfr: "eGFR", bp: "BP", hr: "HR", ntprobnp: "NT-proBNP" };
  return String(key || "")
    .split("_")
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLowerCase();
      if (acronyms[lower]) return acronyms[lower];
      return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
    })
    .join(" ");
}

export { humanizeToken };

export function isTriggerCondition(value) {
  return isPlainObject(value) && ("operator" in value || "field" in value);
}

export function isSeverityRule(value) {
  return isPlainObject(value) && "severity" in value && ("field" in value || "operator" in value);
}

/** Human-readable dose-safety trigger row (rule_body.trigger). */
export function formatTriggerCondition(condition) {
  if (!isPlainObject(condition)) return String(condition ?? "—");
  if (condition.operator === "always") return "Always applies (monitoring reminder)";

  const OP_LABELS = {
    lt: "below",
    lte: "at or below",
    gt: "above",
    gte: "at or above",
    eq: "equals",
    ne: "not equal to",
    missing_or_lt: "missing or below",
    missing_or_lte: "missing or at/below",
  };

  const field = condition.field ? humanizeToken(String(condition.field)) : "Observation";
  const opKey = String(condition.operator || "eq").toLowerCase();
  const op = OP_LABELS[opKey] || opKey.replace(/_/g, " ");
  const val = condition.value;

  if (val === undefined || val === null || val === "") {
    return `${field} is ${op}`;
  }
  if (opKey === "missing_or_lt" || opKey === "missing_or_lte") {
    return `${field} is ${op} ${val}`;
  }
  if (["lt", "lte", "gt", "gte"].includes(opKey)) {
    const sym = { lt: "<", lte: "≤", gt: ">", gte: "≥" }[opKey];
    return `${field} ${sym} ${val}`;
  }
  return `${field} ${op} ${val}`;
}

export function formatSeverityRule(rule) {
  if (!isSeverityRule(rule)) return null;
  const base = formatTriggerCondition(rule);
  const sev = rule.severity ? humanizeToken(String(rule.severity)) : "";
  return sev ? `${base} → ${sev} severity` : base;
}
