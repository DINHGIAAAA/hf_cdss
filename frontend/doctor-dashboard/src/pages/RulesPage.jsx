import { useCallback, useEffect, useState } from "react";
import { ChevronRight, LoaderCircle, RefreshCw } from "lucide-react";

import { adminApi } from "../api/index.js";
import { useAuth } from "../auth/AuthContext";
import { RuleDetail } from "../components/RuleDetail.jsx";
import { RuleVisibilityBadge } from "../components/RuleVisibilityBadge.jsx";
import { ruleVisibilityMeta, tabVisibilityBanner } from "../utils/ruleVisibility.js";

const STATUS_TABS = [
  { id: "all", label: "All" },
  { id: "draft", label: "Draft" },
  { id: "approved", label: "Approved" },
  { id: "retired", label: "Retired" },
];

function statusClass(status) {
  if (status === "approved") return "success";
  if (status === "draft") return "warning";
  return "danger";
}

export function RulesPage() {
  const { isAuthenticated, hasRole } = useAuth();
  const [tab, setTab] = useState("draft");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [selectedRule, setSelectedRule] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [toast, setToast] = useState("");

  const canApprove = isAuthenticated && hasRole("clinical_lead");
  const canAdmin = isAuthenticated && hasRole("admin");
  const canRead = isAuthenticated && (canApprove || canAdmin);
  const tabBanner = tabVisibilityBanner(tab);

  const loadRules = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await adminApi.listRules(tab === "all" ? undefined : tab);
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    loadRules();
  }, [loadRules]);

  async function openRule(ruleId) {
    setSelectedId(ruleId);
    try {
      const rule = await adminApi.getRule(ruleId);
      setSelectedRule(rule);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleAction(action, ruleId) {
    setActionLoading(true);
    setToast("");
    try {
      const statusByAction = {
        approve: "approved",
        unretire: "approved",
        retire: "retired",
      };
      const result = await adminApi.updateStatus(ruleId, statusByAction[action]);
      setToast(result.message);
      await loadRules();
      if (selectedId === ruleId) {
        const updated = await adminApi.getRule(ruleId);
        setSelectedRule(updated);
      }
    } catch (err) {
      setToast(err.message);
    } finally {
      setActionLoading(false);
    }
  }

  const items = data?.items || [];

  return (
    <div className="admin-page">
      <header className="admin-page-header">
        <div>
          <h1>Constraint rules</h1>
          <p>Review draft rules generated from the knowledge pipeline and approve for clinical use.</p>
        </div>
        <button className="secondary-action" onClick={loadRules} type="button">
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      {!isAuthenticated && (
        <div className="admin-banner warning" role="status">
          Sign in with a <strong>clinical_lead</strong> or <strong>admin</strong> account to approve or retire rules.
        </div>
      )}

      <div className="admin-stats">
        <div className="stat-card">
          <span>Draft</span>
          <strong>{data?.draft_count ?? "—"}</strong>
          <small className="stat-hint">Admin only</small>
        </div>
        <div className="stat-card">
          <span>Approved</span>
          <strong>{data?.approved_count ?? "—"}</strong>
          <small className="stat-hint">Live in chat</small>
        </div>
        <div className="stat-card">
          <span>Retired</span>
          <strong>{data?.retired_count ?? "—"}</strong>
          <small className="stat-hint">Not in chat</small>
        </div>
      </div>

      <div className="tab-row" role="tablist">
        {STATUS_TABS.map((item) => (
          <button
            aria-selected={tab === item.id}
            className={tab === item.id ? "active" : ""}
            key={item.id}
            onClick={() => setTab(item.id)}
            role="tab"
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className={`admin-banner rule-visibility-banner ${tabBanner.tone}`} role="status">
        <strong>{tabBanner.title}</strong>
        <span>{tabBanner.message}</span>
      </div>

      {toast && <p className="admin-toast" role="status">{toast}</p>}
      {error && <p className="inline-error" role="alert">{error}</p>}

      <div className={`admin-split${selectedRule ? " admin-split--open" : ""}`}>
        <section className="admin-table-panel">
          {loading ? (
            <div className="admin-empty" aria-busy="true">
              <LoaderCircle className="spin" size={24} />
              Loading rules...
            </div>
          ) : items.length === 0 ? (
            <div className="admin-empty" role="status">
              <h2>No rules in this view</h2>
              <p>Run the ingestion pipeline to generate draft constraint rules.</p>
            </div>
          ) : (
            <table className="admin-table admin-table--rules">
              <colgroup>
                <col className="col-constraint" />
                <col className="col-action" />
                <col className="col-status" />
                <col className="col-visibility" />
                <col className="col-target" />
                <col className="col-actions" />
              </colgroup>
              <thead>
                <tr>
                  <th>Constraint</th>
                  <th>Action</th>
                  <th>Status</th>
                  <th>Visibility</th>
                  <th>Drug class</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((rule) => {
                  const visibility = ruleVisibilityMeta(rule.status);
                  return (
                    <tr className={selectedId === rule.id ? "selected" : ""} key={rule.id}>
                      <td className="cell-ellipsis" title={rule.constraint_id}>
                        <strong>{rule.constraint_id}</strong>
                        <small>v{rule.version}</small>
                      </td>
                      <td className="cell-ellipsis" title={rule.action}>{rule.action}</td>
                      <td>
                        <span className={`badge ${statusClass(rule.status)}`}>{rule.status}</span>
                      </td>
                      <td>
                        <RuleVisibilityBadge status={rule.status} title={visibility.hint} />
                      </td>
                      <td className="cell-ellipsis" title={rule.target_drug_class || undefined}>
                        {rule.target_drug_class || "—"}
                      </td>
                      <td>
                        <button className="link-btn" onClick={() => openRule(rule.id)} type="button">
                          Review <ChevronRight size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        {selectedRule && (
          <RuleDetail
            actionLoading={actionLoading}
            canAdmin={canAdmin}
            canApprove={canApprove}
            canRead={canRead}
            onAction={handleAction}
            onClose={() => {
              setSelectedRule(null);
              setSelectedId(null);
            }}
            rule={selectedRule}
          />
        )}
      </div>
    </div>
  );
}
