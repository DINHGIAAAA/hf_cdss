import { apiGet, apiPatch, apiPost, login, logout, API_BASE_URL } from "@shared/api/client.js";
import { buildGovernanceQuery } from "@shared/governance/catalogConfig.js";

export { login, logout, API_BASE_URL };

export const adminApi = {
  listRules: (params = {}) =>
    apiGet(`/admin/constraints${buildGovernanceQuery(params)}`),
  getRule: (ruleId) => apiGet(`/admin/constraints/rules/${ruleId}`),
  getVersions: (constraintId) => apiGet(`/admin/constraints/by-cid/${encodeURIComponent(constraintId)}`),
  getConstraintRuleDiff: (ruleId, against = "approved") =>
    apiGet(`/admin/constraints/rules/${ruleId}/diff?against=${encodeURIComponent(against)}`),
  getHistory: (constraintId) => apiGet(`/admin/constraints/${encodeURIComponent(constraintId)}/history`),
  updateStatus: (ruleId, status) => apiPatch(`/admin/constraints/rules/${ruleId}`, { status }),
  approve: (ruleId) => apiPatch(`/admin/constraints/rules/${ruleId}`, { status: "approved" }),
  retire: (ruleId) => apiPatch(`/admin/constraints/rules/${ruleId}`, { status: "retired" }),
  unretire: (ruleId) => apiPatch(`/admin/constraints/rules/${ruleId}`, { status: "approved" }),
  bulkApproveConstraints: (payload) => apiPost("/admin/constraints/bulk-approve", payload),
  activeRules: () => apiGet("/admin/constraints/active"),
  listDoseRules: (params = {}) =>
    apiGet(`/admin/dose-rules${buildGovernanceQuery(params)}`),
  getDoseRule: (ruleId) => apiGet(`/admin/dose-rules/rules/${ruleId}`),
  getDoseRuleVersions: (doseRuleId) =>
    apiGet(`/admin/dose-rules/by-rid/${encodeURIComponent(doseRuleId)}`),
  getDoseRuleDiff: (ruleId, against = "approved") =>
    apiGet(`/admin/dose-rules/rules/${ruleId}/diff?against=${encodeURIComponent(against)}`),
  getDoseRuleHistory: (doseRuleId) =>
    apiGet(`/admin/dose-rules/${encodeURIComponent(doseRuleId)}/history`),
  updateDoseRuleStatus: (ruleId, status) => apiPatch(`/admin/dose-rules/rules/${ruleId}`, { status }),
  bulkApproveDoseRules: (payload) => apiPost("/admin/dose-rules/bulk-approve", payload),
  activeDoseRules: () => apiGet("/admin/dose-rules/active"),
  listInteractionRules: (params = {}) =>
    apiGet(`/admin/interaction-rules${buildGovernanceQuery(params)}`),
  getInteractionRule: (ruleId) => apiGet(`/admin/interaction-rules/rules/${ruleId}`),
  getInteractionRuleVersions: (interactionRuleId) =>
    apiGet(`/admin/interaction-rules/by-rid/${encodeURIComponent(interactionRuleId)}`),
  getInteractionRuleDiff: (ruleId, against = "approved") =>
    apiGet(`/admin/interaction-rules/rules/${ruleId}/diff?against=${encodeURIComponent(against)}`),
  getInteractionRuleHistory: (interactionRuleId) =>
    apiGet(`/admin/interaction-rules/${encodeURIComponent(interactionRuleId)}/history`),
  updateInteractionRuleStatus: (ruleId, status) =>
    apiPatch(`/admin/interaction-rules/rules/${ruleId}`, { status }),
  bulkApproveInteractionRules: (payload) => apiPost("/admin/interaction-rules/bulk-approve", payload),
  activeInteractionRules: () => apiGet("/admin/interaction-rules/active"),
  listGdmtPolicies: (params = {}) =>
    apiGet(`/admin/gdmt-policies${buildGovernanceQuery(params)}`),
  getGdmtPolicy: (policyId) => apiGet(`/admin/gdmt-policies/rules/${policyId}`),
  getGdmtPolicyVersions: (gdmtPolicyId) =>
    apiGet(`/admin/gdmt-policies/by-rid/${encodeURIComponent(gdmtPolicyId)}`),
  getGdmtPolicyDiff: (policyId, against = "approved") =>
    apiGet(`/admin/gdmt-policies/rules/${policyId}/diff?against=${encodeURIComponent(against)}`),
  getGdmtPolicyHistory: (gdmtPolicyId) =>
    apiGet(`/admin/gdmt-policies/${encodeURIComponent(gdmtPolicyId)}/history`),
  updateGdmtPolicyStatus: (policyId, status) =>
    apiPatch(`/admin/gdmt-policies/rules/${policyId}`, { status }),
  bulkApproveGdmtPolicies: (payload) => apiPost("/admin/gdmt-policies/bulk-approve", payload),
  activeGdmtPolicies: () => apiGet("/admin/gdmt-policies/active"),
  listDoseSafetyWarnings: (params = {}) =>
    apiGet(`/admin/dose-safety-warnings${buildGovernanceQuery(params)}`),
  getDoseSafetyWarning: (ruleId) => apiGet(`/admin/dose-safety-warnings/rules/${ruleId}`),
  getDoseSafetyWarningVersions: (doseSafetyWarningId) =>
    apiGet(`/admin/dose-safety-warnings/by-rid/${encodeURIComponent(doseSafetyWarningId)}`),
  getDoseSafetyWarningDiff: (ruleId, against = "approved") =>
    apiGet(`/admin/dose-safety-warnings/rules/${ruleId}/diff?against=${encodeURIComponent(against)}`),
  getDoseSafetyWarningHistory: (doseSafetyWarningId) =>
    apiGet(`/admin/dose-safety-warnings/${encodeURIComponent(doseSafetyWarningId)}/history`),
  updateDoseSafetyWarningStatus: (ruleId, status) =>
    apiPatch(`/admin/dose-safety-warnings/rules/${ruleId}`, { status }),
  bulkApproveDoseSafetyWarnings: (payload) => apiPost("/admin/dose-safety-warnings/bulk-approve", payload),
  activeDoseSafetyWarnings: () => apiGet("/admin/dose-safety-warnings/active"),
};

export const evidenceApi = {
  search: (q, topK = 8) => apiGet(`/evidence/search?q=${encodeURIComponent(q)}&top_k=${topK}`),
};

export const systemApi = {
  health: () => apiGet("/health"),
  readiness: () => apiGet("/health/ready").catch((err) => ({ status: "degraded", error: err.message })),
  dependencies: () => apiGet("/health/dependencies").catch((err) => ({ status: "degraded", error: err.message })),
  version: () => apiGet("/version"),
  routes: () => fetch(`${API_BASE_URL}/routes`).then((r) => r.json()),
};

export const kgApi = {
  drugClasses: () => apiGet("/kg/drug-classes"),
  recommendations: (hfType) => apiGet(`/kg/recommendations/${encodeURIComponent(hfType)}`),
  constraints: (drugClass) => apiGet(`/kg/constraints/${encodeURIComponent(drugClass)}`),
  interactions: (drug, topK = 5) =>
    apiGet(`/kg/interactions?drug=${encodeURIComponent(drug)}&top_k=${topK}`),
};

export const retrievalApi = {
  search: (q, topK = 6) => apiGet(`/evidence/search?q=${encodeURIComponent(q)}&top_k=${topK}`),
  context: (body) => apiPost("/retrieval/context", body),
};

export const auditApi = {
  byCase: (caseId, limit = 20) => apiGet(`/audit/${encodeURIComponent(caseId)}?limit=${limit}`),
};
