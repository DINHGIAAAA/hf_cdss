import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight, HeartPulse, LoaderCircle, RefreshCw } from "lucide-react";

import { adminApi } from "../api/index.js";
import { useAuth } from "../auth/AuthContext";
import { GdmtPolicyDetail } from "../components/GdmtPolicyDetail.jsx";
import { ApprovalToolbar } from "@shared/governance/ApprovalToolbar.jsx";
import { GDMT_CATALOG } from "@shared/governance/catalogConfig.js";
import { fetchCatalogListWithCounts } from "@shared/governance/fetchCatalogListWithCounts.js";
import { StatusCountCards, statusTabLabel } from "@shared/governance/StatusCountCards.jsx";
import { useRuleSelection } from "@shared/governance/useRuleSelection.js";

const STATUS_TABS = [
  { id: "all", label: "All" },
  { id: "draft", label: "Draft" },
  { id: "approved", label: "Approved" },
  { id: "retired", label: "Retired" },
];

const EMPTY_FILTERS = {
  drug_class_key: "",
  safety_tier: "",
  q: "",
};

function statusClass(status) {
  if (status === "approved") return "success";
  if (status === "draft") return "warning";
  return "danger";
}

export function GdmtPoliciesPage() {
  const { isAuthenticated, hasRole } = useAuth();
  const [tab, setTab] = useState("draft");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [toast, setToast] = useState("");

  const canApprove = isAuthenticated && hasRole("clinical_lead");
  const canAdmin = isAuthenticated && hasRole("admin");
  const canRead = isAuthenticated && (canApprove || canAdmin);

  const loadPolicies = useCallback(async () => {
    if (!canRead) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await fetchCatalogListWithCounts(adminApi.listGdmtPolicies, {
        tab,
        filters: appliedFilters,
      });
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [tab, appliedFilters, canRead]);

  useEffect(() => {
    loadPolicies();
  }, [loadPolicies]);

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

  async function openPolicy(policyId) {
    setSelectedId(policyId);
    try {
      const policy = await adminApi.getGdmtPolicy(policyId);
      setSelectedPolicy(policy);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleAction(action, policyId) {
    setActionLoading(true);
    setToast("");
    try {
      const statusByAction = {
        approve: "approved",
        unretire: "approved",
        retire: "retired",
      };
      const result = await adminApi.updateGdmtPolicyStatus(policyId, statusByAction[action]);
      setToast(result.message);
      await loadPolicies();
      if (selectedId === policyId) {
        const updated = await adminApi.getGdmtPolicy(policyId);
        setSelectedPolicy(updated);
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
      const result = await adminApi.bulkApproveGdmtPolicies(payload);
      setToast(result.message);
      clearSelection();
      await loadPolicies();
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
            <HeartPulse aria-hidden size={22} />
            <h1>GDMT policies</h1>
          </div>
          <p>
            Review GDMT recommendation policies extracted from guidelines. Approved policies drive
            medication-class statuses in /recommend and the chatbot.
          </p>
        </div>
        <button className="secondary-action" onClick={loadPolicies} type="button">
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      {!canRead && (
        <div className="admin-banner warning" role="status">
          Sign in with a <strong>clinical_lead</strong> or <strong>admin</strong> account to review counts and approve GDMT policies.
        </div>
      )}

      <StatusCountCards
        activeTab={tab}
        approvedCount={loading && !data ? undefined : (data?.approved_count ?? 0)}
        cardClassName="stat-card dose-stat-card"
        className="admin-stats dose-stats"
        draftCount={loading && !data ? undefined : (data?.draft_count ?? 0)}
        hints={{
          draft: "Awaiting clinical review",
          approved: "Active in recommendation engine",
          retired: "Archived versions",
        }}
        onSelect={setTab}
        retiredCount={loading && !data ? undefined : (data?.retired_count ?? 0)}
      />

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
            {statusTabLabel(item.id, item.label, data)}
          </button>
        ))}
      </div>

      <ApprovalToolbar
        allVisibleSelected={allVisibleSelected}
        bulkLoading={bulkLoading}
        canBulkApprove={canApprove}
        catalog={GDMT_CATALOG}
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

      <div className={`admin-split${selectedPolicy ? " admin-split--open" : ""}`}>
        <section className="admin-table-panel">
          {loading ? (
            <div className="admin-empty" aria-busy="true">
              <LoaderCircle className="spin" size={24} />
              Loading GDMT policies...
            </div>
          ) : items.length === 0 ? (
            <div className="admin-empty" role="status">
              <h2>No GDMT policies in this view</h2>
              <p>Run structured GDMT extraction in the ingestion pipeline, then sync to Postgres.</p>
            </div>
          ) : (
            <table className="admin-table admin-table--dose">
              <thead>
                <tr>
                  {tab === "draft" && <th>Select</th>}
                  <th>Policy</th>
                  <th>Class key</th>
                  <th>Status</th>
                  <th>Order</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((policy) => (
                  <tr className={selectedId === policy.id ? "selected" : ""} key={policy.id}>
                    {tab === "draft" && (
                      <td>
                        {policy.status === "draft" ? (
                          <input
                            aria-label={`Select ${policy.gdmt_policy_id}`}
                            checked={selectedIds.has(policy.id)}
                            onChange={() => toggleOne(policy.id)}
                            type="checkbox"
                          />
                        ) : null}
                      </td>
                    )}
                    <td>
                      <strong>{policy.display_label}</strong>
                      <small>
                        {policy.gdmt_policy_id} · v{policy.version}
                      </small>
                    </td>
                    <td>
                      <code className="dose-code">{policy.drug_class_key}</code>
                    </td>
                    <td>
                      <span className={`badge ${statusClass(policy.status)}`}>{policy.status}</span>
                    </td>
                    <td>{policy.sort_order}</td>
                    <td>
                      <button className="link-btn" onClick={() => openPolicy(policy.id)} type="button">
                        Review <ChevronRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {selectedPolicy && (
          <GdmtPolicyDetail
            actionLoading={actionLoading}
            canAdmin={canAdmin}
            canApprove={canApprove}
            onAction={handleAction}
            onClose={() => {
              setSelectedPolicy(null);
              setSelectedId(null);
            }}
            policy={selectedPolicy}
          />
        )}
      </div>
    </div>
  );
}
