import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight, HeartPulse, LoaderCircle, RefreshCw } from "lucide-react";

import { adminApi } from "../api/index.js";
import { useAuth } from "../auth/AuthContext";
import { GdmtPolicyDetail } from "../components/GdmtPolicyDetail.jsx";
import { CatalogApprovalToolbar } from "@shared/governance/CatalogApprovalToolbar.jsx";
import { GDMT_CATALOG } from "@shared/governance/catalogConfig.js";
import { CatalogRecordLabel } from "@shared/governance/CatalogRecordLabel.jsx";
import { gdmtPolicyTitle, shortCatalogId } from "@shared/governance/displayNames.js";
import { CatalogPagination } from "@shared/governance/CatalogPagination.jsx";
import { CATALOG_PAGE_SIZE } from "@shared/governance/catalogPagination.js";
import { useCatalogBulkApprove } from "@shared/governance/useCatalogBulkApprove.js";
import { useCatalogListPage } from "@shared/governance/useCatalogListPage.js";
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
  const { page, setPage, pageSize } = useCatalogListPage(tab, appliedFilters);

  const canApprove = isAuthenticated && hasRole("clinical_lead");
  const canAdmin = isAuthenticated && hasRole("admin");

  const loadPolicies = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await adminApi.listGdmtPolicies({
        status: tab === "all" ? undefined : tab,
        ...appliedFilters,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [tab, appliedFilters, page, pageSize]);

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

  const { handleBulkApprove, handleBulkApproveAll } = useCatalogBulkApprove({
    catalog: GDMT_CATALOG,
    adminApi,
    appliedFilters,
    selectedIds,
    clearSelection,
    loadRules: loadPolicies,
    setToast,
    setBulkLoading,
  });

  const draftMatchCount = tab === "draft" ? (data?.total ?? 0) : 0;

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

      {!isAuthenticated && (
        <div className="admin-banner warning" role="status">
          Sign in with a <strong>clinical_lead</strong> or <strong>admin</strong> account to approve GDMT policies.
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
          <small>Active in recommendation engine</small>
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

      <CatalogApprovalToolbar
        allVisibleSelected={allVisibleSelected}
        bulkLoading={bulkLoading}
        canBulkApprove={canApprove}
        catalog={GDMT_CATALOG}
        fetchFilterOptions={adminApi.getCatalogFilterOptions}
        filters={filters}
        onApplyFilters={() => setAppliedFilters({ ...filters })}
        onBulkApprove={handleBulkApprove}
        onBulkApproveAll={handleBulkApproveAll}
        draftMatchCount={draftMatchCount}
        onClearFilters={() => {
          setFilters(EMPTY_FILTERS);
          setAppliedFilters(EMPTY_FILTERS);
        }}
        onToggleAll={toggleAllVisible}
        activeFilterCount={activeFilterCount}
        resultsCount={data?.total ?? items.length}
        selectedCount={selectedCount}
        setFilters={setFilters}
        tab={tab}
        showBulk={tab === "draft"}
      />

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
            <>
            <table className="admin-table admin-table--dose">
              <thead>
                <tr>
                  {tab === "draft" && <th>Select</th>}
                  <th>Policy</th>
                  <th>Class key</th>
                  <th>Status</th>
                  <th>Order</th>
                  <th className="admin-col-actions">Review</th>
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
                      <CatalogRecordLabel
                        id={shortCatalogId(policy.gdmt_policy_id)}
                        meta={`v${policy.version}`}
                        title={gdmtPolicyTitle(policy)}
                        titleAttr={policy.gdmt_policy_id}
                      />
                    </td>
                    <td className="cell-clamp" title={policy.drug_class_key}>
                      <code className="dose-code">{policy.drug_class_key}</code>
                    </td>
                    <td>
                      <span className={`badge ${statusClass(policy.status)}`}>{policy.status}</span>
                    </td>
                    <td>{policy.sort_order}</td>
                    <td className="admin-col-actions">
                      <button className="link-btn" onClick={() => openPolicy(policy.id)} type="button">
                        Review <ChevronRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <CatalogPagination
              loading={loading}
              onPageChange={setPage}
              page={page}
              pageSize={CATALOG_PAGE_SIZE}
              total={data?.total ?? 0}
            />
            </>

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
  );
}
