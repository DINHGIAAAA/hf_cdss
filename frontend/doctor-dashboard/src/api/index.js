import { apiGet, apiPatch, apiPost, fetchCurrentUser, login, logout, API_BASE_URL, apiUrl } from "@shared/api/client.js";

export { fetchCurrentUser, login, logout, API_BASE_URL };

export const adminApi = {
  listRules: (status) => apiGet(status ? `/admin/constraints?status=${status}` : "/admin/constraints"),
  getRule: (ruleId) => apiGet(`/admin/constraints/rules/${ruleId}`),
  getVersions: (constraintId) => apiGet(`/admin/constraints/by-cid/${encodeURIComponent(constraintId)}`),
  getHistory: (constraintId) => apiGet(`/admin/constraints/${encodeURIComponent(constraintId)}/history`),
  updateStatus: (ruleId, status) => apiPatch(`/admin/constraints/rules/${ruleId}`, { status }),
  approve: (ruleId) => apiPatch(`/admin/constraints/rules/${ruleId}`, { status: "approved" }),
  retire: (ruleId) => apiPatch(`/admin/constraints/rules/${ruleId}`, { status: "retired" }),
  unretire: (ruleId) => apiPatch(`/admin/constraints/rules/${ruleId}`, { status: "approved" }),
  listUsers: () => apiGet("/admin/users"),
  createUser: (payload) => apiPost("/admin/users", payload),
  updateUser: (userId, payload) => apiPatch(`/admin/users/${encodeURIComponent(userId)}`, payload),
  auditByCase: (caseId, limit = 50) => apiGet(`/admin/audit/cases/${encodeURIComponent(caseId)}?limit=${limit}`),
  searchEvidence: (q, topK = 10, { staging = true, signal } = {}) =>
    apiGet(
      `/admin/evidence/search?q=${encodeURIComponent(q)}&top_k=${topK}&staging=${staging ? "true" : "false"}`,
      { signal },
    ),
  activeRules: () => apiGet("/admin/constraints/active"),
};

export const evidenceApi = {
  search: (q, topK = 8, options = {}) =>
    apiGet(`/evidence/search?q=${encodeURIComponent(q)}&top_k=${topK}`, options),
};

export const systemApi = {
  health: () => apiGet("/health"),
  readiness: () => apiGet("/health/ready").catch((err) => ({ status: "degraded", error: err.message })),
  dependencies: () => apiGet("/health/dependencies").catch((err) => ({ status: "degraded", error: err.message })),
  version: () => apiGet("/version"),
  routes: () =>
    fetch(apiUrl("/routes"), { credentials: "include" }).then((r) => {
      if (!r.ok) throw new Error(`Request failed (${r.status})`);
      return r.json();
    }),
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
