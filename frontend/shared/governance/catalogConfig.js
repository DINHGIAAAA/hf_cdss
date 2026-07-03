export function buildGovernanceQuery(params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      qs.set(key, String(value));
    }
  });
  const query = qs.toString();
  return query ? `?${query}` : "";
}

export function formatDiffValue(value) {
  if (value === undefined || value === null) return "—";
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

export const SAFETY_TIER_OPTIONS = [
  { value: "", label: "All tiers" },
  { value: "usable_rules", label: "Usable" },
  { value: "needs_refinement", label: "Needs refinement" },
  { value: "rejected_rules", label: "Rejected" },
];

export const CONSTRAINT_CATALOG = {
  id: "constraints",
  label: "Constraint rules",
  bulkLabel: "constraint rules",
  listKey: "listRules",
  bulkKey: "bulkApproveConstraints",
  diffKey: "getConstraintRuleDiff",
  versionsKey: "getVersions",
  logicalIdField: "constraint_id",
  filters: [
    { key: "target_drug_class", label: "Drug class", placeholder: "e.g. MRA" },
    { key: "action", label: "Action", placeholder: "e.g. avoid" },
    { key: "q", label: "Search ID", placeholder: "constraint id" },
  ],
};

export const DOSE_CATALOG = {
  id: "dose-rules",
  label: "Dose rules",
  bulkLabel: "dose rules",
  listKey: "listDoseRules",
  bulkKey: "bulkApproveDoseRules",
  diffKey: "getDoseRuleDiff",
  versionsKey: "getDoseRuleVersions",
  logicalIdField: "dose_rule_id",
  filters: [
    { key: "drug_class", label: "Drug class", placeholder: "e.g. DOAC" },
    { key: "calculation_type", label: "Calculation", placeholder: "e.g. crcl_reduction" },
    { key: "safety_tier", label: "Safety tier", type: "select", options: SAFETY_TIER_OPTIONS },
    { key: "q", label: "Search ID", placeholder: "dose rule id" },
  ],
};
