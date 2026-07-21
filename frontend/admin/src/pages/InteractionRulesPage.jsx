import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight, Link2, LoaderCircle, RefreshCw } from "lucide-react";

import { adminApi } from "../api/index.js";
import { useAuth } from "../auth/AuthContext";
import { InteractionRuleDetail } from "../components/InteractionRuleDetail.jsx";
import { ApprovalToolbar } from "@shared/governance/ApprovalToolbar.jsx";
import { INTERACTION_CATALOG } from "@shared/governance/catalogConfig.js";
import { useRuleSelection } from "@shared/governance/useRuleSelection.js";

const STATUS_TABS = [
  { id: "all", label: "All" },
  { id: "draft", label: "Draft" },
  { id: "approved", label: "Approved" },
  { id: "retired", label: "Retired" },
];

const EMPTY_FILTERS = {
  severity: "",
  target: "",
  safety_tier: "",
  extraction_method: "",
  q: "",
};

function statusClass(status) {
  if (status === "approved") return "success";
  if (status === "draft") return "warning";
  return "danger";
}

function formatDrugSet(tokens = []) {
  if (!tokens.length) return "—";
  const preview = tokens.slice(0, 2).join(", ");
  return tokens.length > 2 ? `${preview} +${tokens.length - 2}` : preview;
}

export function InteractionRulesPage() {
  const { isAuthenticated, hasRole } = useAuth();
  const [tab, setTab] = useState("draft");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [selectedRule, setSelectedRule] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [toast, setToast] = useState("");

  const canApprove = isAuthenticated && hasRole("clinical_lead");
  const canAdmin = isAuthenticated && hasRole("admin");

  const loadRules = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await adminApi.listInteractionRules({
        status: tab === "all" ? undefined : tab,
        ...appliedFilters,
      });
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [tab, appliedFilters]);

  useEffect(() => {
    loadRules();
  }, [loadRules]);

  const items = data?.items || [];
  const {
    selectedIds,
    allVisibleSelected,
    toggleOne,
    toggleAllVisible,
    clearSelection,
    selectedCount,
  } = useRuleSelection(items);

  const activeFilterCount = useMemo(
    () => Object.values(appliedFilters).filter(Boolean).length,
    [appliedFilters],
  );

  async function openRule(ruleId) {
    setSelectedId(ruleId);
    try {
      const rule = await adminApi.getInteractionRule(ruleId);
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
      const result = await adminApi.updateInteractionRuleStatus(ruleId, statusByAction[action]);
      setToast(result.message);
      await loadRules();
      if (selectedId === ruleId) {
        const updated = await adminApi.getInteractionRule(ruleId);
        setSelectedRule(updated);
      }
    } catch (err) {
      setToast(err.message);
    } finally {
      setActionLoading(false);
    }
  }

  async function handleBulkApprove() {
    setBulkLoading(true);
    setToast("");
    try {
      const payload = {
        rule_ids: [...selectedIds],
        ...Object.fromEntries(Object.entries(appliedFilters).filter(([, value]) => Boolean(value))),
      };
      const result = await adminApi.bulkApproveInteractionRules(payload);
      setToast(result.message);
      clearSelection();
      await loadRules();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBulkLoading(false);
    }
  }

  return (
    <div className="admin-page dose-rules-page">
      <header className="admin-page-header">
        <div>
          <div className="dose-page-title">
            <Link2 aria-hidden size={22} />
            <h1>Interaction rules</h1>
          </div>
          <p>
            Review drug-drug interaction rules extracted from labels and guidelines. Approved rules drive
            the CDSS interaction checker at runtime.
          </p>
        </div>
        <button className="secondary-action" onClick={loadRules} type="button">
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      {!isAuthenticated && (
        <div className="admin-banner warning" role="status">
          Sign in with a <strong>clinical_lead</strong> or <strong>admin</strong> account to approve
          interaction rules.
        </div>
      )}

      <div className="admin-stats dose-stats">
        <div className="stat-card dose-stat-card">
          <span>Draft</span>
          <strong>{data?.draft_count ?? "—"}</strong>
          <small>Awaiting clinical review</small>
        </div>
        <div className="stat-card dose-stat-card">
          <span>Approved</span>
          <strong>{data?.approved_count ?? "—"}</strong>
          <small>Active in interaction checker</small>
        </div>
        <div className="stat-card dose-stat-card">
          <span>Retired</span>
          <strong>{data?.retired_count ?? "—"}</strong>
          <small>Archived versions</small>
        </div>
      </div>

      <div className="tab-row dose-tab-row" role="tablist">
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

      <ApprovalToolbar
        allVisibleSelected={allVisibleSelected}
        bulkLoading={bulkLoading}
        canBulkApprove={canApprove}
        catalog={INTERACTION_CATALOG}
        filters={filters}
        onApplyFilters={() => setAppliedFilters({ ...filters })}
        onBulkApprove={handleBulkApprove}
        onClearFilters={() => {
          setFilters(EMPTY_FILTERS);
          setAppliedFilters(EMPTY_FILTERS);
        }}
        onFilterChange={(key, value) => setFilters((prev) => ({ ...prev, [key]: value }))}
        onToggleAll={toggleAllVisible}
        selectedCount={selectedCount}
        showBulk={tab === "draft"}
      />

      {activeFilterCount > 0 && (
        <p className="gov-filter-summary" role="status">
          {activeFilterCount} filter(s) active · {items.length} result(s)
        </p>
      )}

      {toast && (
        <p className="admin-toast" role="status">
          {toast}
        </p>
      )}
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}

      <div className={`admin-split${selectedRule ? " admin-split--open" : ""}`}>
        <section className="admin-table-panel">
          {loading ? (
            <div className="admin-empty" aria-busy="true">
              <LoaderCircle className="spin" size={24} />
              Loading interaction rules...
            </div>
          ) : items.length === 0 ? (
            <div className="admin-empty" role="status">
              <h2>No interaction rules in this view</h2>
              <p>Run structured interaction extraction in the ingestion pipeline, then sync to Postgres.</p>
            </div>
          ) : (
            <table className="admin-table admin-table--dose">
              <thead>
                <tr>
                  {tab === "draft" && <th>Select</th>}
                  <th>Rule</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Drug sets</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((rule) => (
                  <tr className={selectedId === rule.id ? "selected" : ""} key={rule.id}>
                    {tab === "draft" && (
                      <td>
                        {rule.status === "draft" ? (
                          <input
                            aria-label={`Select ${rule.interaction_rule_id}`}
                            checked={selectedIds.has(rule.id)}
                            onChange={() => toggleOne(rule.id)}
                            type="checkbox"
                          />
                        ) : null}
                      </td>
                    )}
                    <td>
                      <strong>{rule.interaction_rule_id}</strong>
                      <small>
                        v{rule.version} · {rule.target || "—"}
                      </small>
                    </td>
                    <td>
                      <code className="dose-code">{rule.severity}</code>
                    </td>
                    <td>
                      <span className={`badge ${statusClass(rule.status)}`}>{rule.status}</span>
                    </td>
                    <td>
                      {formatDrugSet(rule.drug_set_a)} ↔ {formatDrugSet(rule.drug_set_b)}
                    </td>
                    <td>
                      <button className="link-btn" onClick={() => openRule(rule.id)} type="button">
                        Review <ChevronRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {selectedRule && (
          <InteractionRuleDetail
            actionLoading={actionLoading}
            canAdmin={canAdmin}
            canApprove={canApprove}
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
