import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight, LoaderCircle, RefreshCw } from "lucide-react";

import { adminApi } from "../api/index.js";
import { useAuth } from "../auth/AuthContext";
import { RuleDetail } from "../components/RuleDetail.jsx";
import { tabVisibilityBanner } from "../utils/ruleVisibility.js";
import { CatalogApprovalToolbar } from "@shared/governance/CatalogApprovalToolbar.jsx";
import { CONSTRAINT_CATALOG } from "@shared/governance/catalogConfig.js";
import { CatalogRecordLabel } from "@shared/governance/CatalogRecordLabel.jsx";
import { constraintRuleTitle, shortCatalogId } from "@shared/governance/displayNames.js";
import { CatalogPagination } from "@shared/governance/CatalogPagination.jsx";
import { CATALOG_PAGE_SIZE } from "@shared/governance/catalogPagination.js";
import { fetchCatalogListWithCounts } from "@shared/governance/fetchCatalogListWithCounts.js";
import { useCatalogBulkApprove } from "@shared/governance/useCatalogBulkApprove.js";
import { useCatalogListPage } from "@shared/governance/useCatalogListPage.js";
import { StatusCountCards, statusTabLabel } from "@shared/governance/StatusCountCards.jsx";
import { useRuleSelection } from "@shared/governance/useRuleSelection.js";

const STATUS_TABS = [
  { id: "all", label: "All" },
  { id: "draft", label: "Draft" },
  { id: "approved", label: "Approved" },
  { id: "retired", label: "Retired" },
];

const EMPTY_FILTERS = {
  target_drug_class: "",
  action: "",
  safety_tier: "",
  needs_condition: "",
  q: "",
};

function statusClass(status) {
  if (status === "approved") return "success";
  if (status === "draft") return "warning";
  return "danger";
}

function needsConditionBadge(rule) {
  const meta = rule?.metadata || {};
  if (meta.needs_condition === true || meta.safety_tier === "needs_condition_refinement") {
    return <span className="badge warning">Needs condition</span>;
  }
  if (meta.safety_tier === "usable_rules") {
    return <span className="badge success">Usable</span>;
  }
  return null;
}

export function RulesPage() {
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
  const { page, setPage, pageSize } = useCatalogListPage(tab, appliedFilters);

  const canApprove = isAuthenticated && hasRole("clinical_lead");
  const canAdmin = isAuthenticated && hasRole("admin");
  const canRead = isAuthenticated && (canApprove || canAdmin);
  const tabBanner = tabVisibilityBanner(tab);

  const loadRules = useCallback(async () => {
    if (!canRead) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await fetchCatalogListWithCounts(adminApi.listRules, {
        tab,
        filters: appliedFilters,
        page,
        pageSize,
      });
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [tab, appliedFilters, page, pageSize, canRead]);

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

  const { handleBulkApprove, handleBulkApproveAll } = useCatalogBulkApprove({
    catalog: CONSTRAINT_CATALOG,
    adminApi,
    appliedFilters,
    selectedIds,
    clearSelection,
    loadRules,
    setToast,
    setBulkLoading,
  });

  const draftMatchCount = tab === "draft" ? (data?.total ?? 0) : 0;

  const activeFilterCount = useMemo(
    () => Object.values(appliedFilters).filter(Boolean).length,
    [appliedFilters],
  );

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

      {!canRead && (
        <div className="admin-banner warning" role="status">
          Sign in with a <strong>clinical_lead</strong> or <strong>admin</strong> account to review counts and approve or retire rules.
        </div>
      )}

      <StatusCountCards
        activeTab={tab}
        approvedCount={loading && !data ? undefined : (data?.approved_count ?? 0)}
        draftCount={loading && !data ? undefined : (data?.draft_count ?? 0)}
        hints={{
          draft: "Admin only",
          approved: "Live in chat",
          retired: "Not in chat",
        }}
        onSelect={setTab}
        retiredCount={loading && !data ? undefined : (data?.retired_count ?? 0)}
      />

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
            {statusTabLabel(item.id, item.label, data)}
          </button>
        ))}
      </div>

      <CatalogApprovalToolbar
        allVisibleSelected={allVisibleSelected}
        bulkLoading={bulkLoading}
        canBulkApprove={canApprove}
        catalog={CONSTRAINT_CATALOG}
        draftMatchCount={draftMatchCount}
        fetchFilterOptions={adminApi.getCatalogFilterOptions}
        filters={filters}
        onApplyFilters={() => setAppliedFilters({ ...filters })}
        onBulkApprove={handleBulkApprove}
        onBulkApproveAll={handleBulkApproveAll}
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

      <div className={`admin-banner rule-visibility-banner ${tabBanner.tone}`} role="status">
        <strong>{tabBanner.title}</strong>
        <span>{tabBanner.message}</span>
      </div>

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
              Loading rules...
            </div>
          ) : items.length === 0 ? (
            <div className="admin-empty" role="status">
              <h2>No rules in this view</h2>
              <p>Run the ingestion pipeline to generate draft constraint rules.</p>
            </div>
          ) : (
            <>
            <table className="admin-table admin-table--rules">
              <thead>
                <tr>
                  {tab === "draft" && <th>Select</th>}
                  <th>Constraint</th>
                  <th>Action</th>
                  <th>Status</th>
                  <th>Tier</th>
                  <th>Drug class</th>
                  <th className="admin-col-actions">Review</th>
                </tr>
              </thead>
              <tbody>
                {items.map((rule) => (
                    <tr className={selectedId === rule.id ? "selected" : ""} key={rule.id}>
                      {tab === "draft" && (
                        <td>
                          {rule.status === "draft" ? (
                            <input
                              aria-label={`Select ${rule.constraint_id}`}
                              checked={selectedIds.has(rule.id)}
                              onChange={() => toggleOne(rule.id)}
                              type="checkbox"
                            />
                          ) : null}
                        </td>
                      )}
                      <td>
                        <CatalogRecordLabel
                          id={shortCatalogId(rule.constraint_id)}
                          meta={`v${rule.version}`}
                          title={constraintRuleTitle(rule)}
                          titleAttr={rule.constraint_id}
                        />
                      </td>
                      <td className="cell-clamp" title={rule.action}>
                        {rule.action}
                      </td>
                      <td>
                        <span className={`badge ${statusClass(rule.status)}`}>{rule.status}</span>
                      </td>
                      <td>{needsConditionBadge(rule) || "—"}</td>
                      <td className="cell-clamp" title={rule.target_drug_class || undefined}>
                        {rule.target_drug_class || "—"}
                      </td>
                      <td className="admin-col-actions">
                        <button className="link-btn" onClick={() => openRule(rule.id)} type="button">
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
  );
}
