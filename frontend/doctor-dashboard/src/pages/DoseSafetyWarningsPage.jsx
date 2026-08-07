import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronRight, LoaderCircle, RefreshCw } from "lucide-react";

import { adminApi } from "../api/index.js";
import { useAuth } from "../auth/AuthContext";
import { DoseSafetyWarningDetail } from "../components/DoseSafetyWarningDetail.jsx";
import { CatalogApprovalToolbar } from "@shared/governance/CatalogApprovalToolbar.jsx";
import { DOSE_SAFETY_CATALOG } from "@shared/governance/catalogConfig.js";
import { CatalogRecordLabel } from "@shared/governance/CatalogRecordLabel.jsx";
import {
  doseSafetyWarningTitle,
  formatDrugSetLabel,
  shortCatalogId,
} from "@shared/governance/displayNames.js";
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
  target: "",
  default_severity: "",
  safety_tier: "",
  q: "",
};

function statusClass(status) {
  if (status === "approved") return "success";
  if (status === "draft") return "warning";
  return "danger";
}

export function DoseSafetyWarningsPage() {
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

  const loadRules = useCallback(async () => {
    if (!canRead) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await fetchCatalogListWithCounts(adminApi.listDoseSafetyWarnings, {
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
    catalog: DOSE_SAFETY_CATALOG,
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
      const rule = await adminApi.getDoseSafetyWarning(ruleId);
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
      const result = await adminApi.updateDoseSafetyWarningStatus(ruleId, statusByAction[action]);
      setToast(result.message);
      await loadRules();
      if (selectedId === ruleId) {
        const updated = await adminApi.getDoseSafetyWarning(ruleId);
        setSelectedRule(updated);
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
            <AlertTriangle aria-hidden size={22} />
            <h1>Dose safety warnings</h1>
          </div>
          <p>
            Review lab- and renal-based dose safety warnings extracted from labels and guidelines.
            Approved warnings drive the CDSS dose checker at runtime.
          </p>
        </div>
        <button className="secondary-action" onClick={loadRules} type="button">
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      {!canRead && (
        <div className="admin-banner warning" role="status">
          Sign in with a <strong>clinical_lead</strong> or <strong>admin</strong> account to review counts and approve
          dose safety warnings.
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
          approved: "Active in dose checker",
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

      <CatalogApprovalToolbar
        allVisibleSelected={allVisibleSelected}
        bulkLoading={bulkLoading}
        canBulkApprove={canApprove}
        catalog={DOSE_SAFETY_CATALOG}
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
              Loading dose safety warnings...
            </div>
          ) : items.length === 0 ? (
            <div className="admin-empty" role="status">
              <h2>No dose safety warnings in this view</h2>
              <p>Run structured dose safety extraction in the ingestion pipeline, then sync to Postgres.</p>
            </div>
          ) : (
            <>
            <table className="admin-table admin-table--dose">
              <thead>
                <tr>
                  {tab === "draft" && <th>Select</th>}
                  <th>Warning</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Drugs</th>
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
                            aria-label={`Select ${rule.dose_safety_warning_id}`}
                            checked={selectedIds.has(rule.id)}
                            onChange={() => toggleOne(rule.id)}
                            type="checkbox"
                          />
                        ) : null}
                      </td>
                    )}
                    <td>
                      <CatalogRecordLabel
                        id={shortCatalogId(rule.dose_safety_warning_id)}
                        meta={`v${rule.version}`}
                        title={doseSafetyWarningTitle(rule)}
                        titleAttr={rule.dose_safety_warning_id}
                      />
                    </td>
                    <td>
                      <code className="dose-code">{rule.default_severity}</code>
                    </td>
                    <td>
                      <span className={`badge ${statusClass(rule.status)}`}>{rule.status}</span>
                    </td>
                    <td className="cell-clamp" title={(rule.drug_keys || []).join(", ")}>
                      {formatDrugSetLabel(rule.drug_keys)}
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
          <DoseSafetyWarningDetail
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
  );
}
