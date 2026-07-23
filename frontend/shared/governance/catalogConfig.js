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

export const CONSTRAINT_SAFETY_TIER_OPTIONS = [
  { value: "", label: "All tiers" },
  { value: "usable_rules", label: "Usable" },
  { value: "needs_condition_refinement", label: "Needs condition" },
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
    {
      key: "safety_tier",
      label: "Safety tier",
      type: "select",
      options: CONSTRAINT_SAFETY_TIER_OPTIONS,
    },
    {
      key: "needs_condition",
      label: "Needs condition",
      type: "select",
      options: [
        { value: "", label: "Any" },
        { value: "true", label: "Needs condition only" },
        { value: "false", label: "Has structured condition" },
      ],
    },
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

export const GDMT_CATALOG = {
  id: "gdmt-policies",
  label: "GDMT policies",
  bulkLabel: "GDMT policies",
  listKey: "listGdmtPolicies",
  bulkKey: "bulkApproveGdmtPolicies",
  diffKey: "getGdmtPolicyDiff",
  versionsKey: "getGdmtPolicyVersions",
  logicalIdField: "gdmt_policy_id",
  filters: [
    { key: "drug_class_key", label: "Drug class key", placeholder: "e.g. MRA" },
    { key: "safety_tier", label: "Safety tier", type: "select", options: SAFETY_TIER_OPTIONS },
    { key: "q", label: "Search ID", placeholder: "gdmt policy id" },
  ],
};

export const INTERACTION_CATALOG = {
  id: "interaction-rules",
  label: "Interaction rules",
  bulkLabel: "interaction rules",
  listKey: "listInteractionRules",
  bulkKey: "bulkApproveInteractionRules",
  diffKey: "getInteractionRuleDiff",
  versionsKey: "getInteractionRuleVersions",
  logicalIdField: "interaction_rule_id",
  filters: [
    { key: "severity", label: "Severity", placeholder: "e.g. high" },
    { key: "target", label: "Target", placeholder: "e.g. RAASi_MRA" },
    { key: "safety_tier", label: "Safety tier", type: "select", options: SAFETY_TIER_OPTIONS },
    {
      key: "extraction_method",
      label: "Source",
      type: "select",
      options: [
        { value: "", label: "Any source" },
        { value: "fda_xml", label: "FDA XML label" },
        { value: "llm_structured", label: "LLM guideline chunks" },
        { value: "regex_drug_interaction", label: "Regex claim" },
      ],
    },
    { key: "q", label: "Search ID", placeholder: "interaction rule id" },
  ],
};

export const DOSE_SAFETY_CATALOG = {
  id: "dose-safety-warnings",
  label: "Dose safety warnings",
  bulkLabel: "dose safety warnings",
  listKey: "listDoseSafetyWarnings",
  bulkKey: "bulkApproveDoseSafetyWarnings",
  diffKey: "getDoseSafetyWarningDiff",
  versionsKey: "getDoseSafetyWarningVersions",
  logicalIdField: "dose_safety_warning_id",
  filters: [
    { key: "target", label: "Target", placeholder: "e.g. MRA" },
    { key: "default_severity", label: "Severity", placeholder: "e.g. high" },
    { key: "safety_tier", label: "Safety tier", type: "select", options: SAFETY_TIER_OPTIONS },
    { key: "q", label: "Search ID", placeholder: "dose safety warning id" },
  ],
};
