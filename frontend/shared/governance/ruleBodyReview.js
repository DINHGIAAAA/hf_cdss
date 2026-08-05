import {
  formatSeverityRule,
  formatTriggerCondition,
  humanizeToken,
  isTriggerCondition,
} from "./triggerDisplay.js";

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function isDoseSafetyStyleRuleBody(body) {
  if (!isPlainObject(body)) return false;
  return (
    Array.isArray(body.trigger?.condition_groups) ||
    Array.isArray(body.severity_rules) ||
    Array.isArray(body.related_observation_fields) ||
    Array.isArray(body.monitoring)
  );
}

/** Flat, clinician-friendly fields for dose-safety `rule_body` (trigger panel). */
export function doseSafetyRuleBodyToFields(body = {}) {
  const fields = [];
  const groups = body.trigger?.condition_groups;

  if (Array.isArray(groups) && groups.length) {
    let index = 0;
    groups.forEach((group, groupIndex) => {
      const conditions = Array.isArray(group) ? group : [group];
      conditions.forEach((cond) => {
        if (!isTriggerCondition(cond)) return;
        index += 1;
        const pathLabel = groups.length > 1 ? ` · path ${groupIndex + 1}` : "";
        const label = index === 1 && groups.length === 1 && conditions.length === 1
          ? "When to warn"
          : `Condition ${index}${pathLabel}`;
        fields.push({
          label,
          value: formatSeverityRule(cond) || formatTriggerCondition(cond),
          wide: true,
        });
      });
    });
  }

  const severityRules = body.severity_rules;
  if (Array.isArray(severityRules) && severityRules.length) {
    severityRules.forEach((rule, i) => {
      const text = formatSeverityRule(rule);
      if (!text) return;
      fields.push({
        label: severityRules.length > 1 ? `Higher severity ${i + 1}` : "Higher severity if",
        value: text,
        wide: true,
      });
    });
  }

  const labs = body.related_observation_fields;
  if (Array.isArray(labs) && labs.length) {
    fields.push({
      label: "Related labs",
      value: labs.map((token) => humanizeToken(String(token))),
    });
  }

  const monitoring = body.monitoring;
  if (Array.isArray(monitoring) && monitoring.length) {
    fields.push({
      label: "Monitoring",
      value: monitoring.map((item) => humanizeToken(String(item))),
    });
  }

  const notes = body.notes || body.guidance;
  if (notes && typeof notes === "string") {
    fields.push({ label: "Notes", value: notes, wide: true });
  }

  return fields;
}
