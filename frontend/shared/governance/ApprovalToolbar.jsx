import { useState } from "react";
import { CheckCircle2, Filter, Layers, Search, X } from "lucide-react";

import "./governance-toolbar.css";

export function ApprovalToolbar({
  catalog,
  filters,
  onFilterChange,
  onApplyFilters,
  onClearFilters,
  selectedCount,
  draftMatchCount = 0,
  allVisibleSelected,
  onToggleAll,
  onBulkApprove,
  onBulkApproveAll = () => {},
  bulkLoading,
  canBulkApprove,
  showBulk,
  activeFilterCount = 0,
  resultsCount,
  filterOptionsLoading = false,
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAllOpen, setConfirmAllOpen] = useState(false);

  const resultsHint =
    activeFilterCount > 0 && resultsCount != null
      ? `${activeFilterCount} filter(s) active · ${resultsCount} result(s)`
      : resultsCount != null
        ? `${resultsCount} result(s)`
        : null;

  return (
    <section aria-label="Approval filters and bulk actions" className="gov-toolbar">
      <div className="gov-toolbar-top">
        <div className="gov-toolbar-heading">
          <Filter aria-hidden size={18} strokeWidth={2} />
          <span>Filters</span>
          {activeFilterCount > 0 ? (
            <span className="gov-filter-badge">{activeFilterCount} active</span>
          ) : null}
        </div>
        {resultsHint ? <span className="gov-toolbar-meta">{resultsHint}</span> : null}
      </div>

      <div className="gov-filter-grid">
        {catalog.filters.map((field) => (
          <label className="gov-filter-field" key={field.key}>
            <span>{field.label}</span>
            {field.type === "select" ? (
              <select
                disabled={filterOptionsLoading && field.dynamic}
                onChange={(event) => onFilterChange(field.key, event.target.value)}
                value={filters[field.key] || ""}
              >
                {(field.options || []).map((option) => (
                  <option key={option.value || "all"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                onChange={(event) => onFilterChange(field.key, event.target.value)}
                placeholder={field.placeholder}
                type="search"
                value={filters[field.key] || ""}
              />
            )}
          </label>
        ))}
      </div>

      <div className="gov-toolbar-footer">
        <div className="gov-toolbar-actions">
          <button className="gov-btn-apply" onClick={onApplyFilters} type="button">
            <Search aria-hidden size={16} strokeWidth={2} />
            Apply filters
          </button>
          <button className="gov-btn-clear" onClick={onClearFilters} type="button">
            <X aria-hidden size={16} strokeWidth={2} />
            Clear
          </button>
        </div>
      </div>

      {showBulk ? (
        <div className="gov-bulk-bar">
          <label className="gov-select-all">
            <input checked={allVisibleSelected} onChange={onToggleAll} type="checkbox" />
            Select visible drafts
          </label>
          <span className="gov-selected-count">{selectedCount} selected</span>
          {canBulkApprove ? (
            <>
              <button
                className="primary-action dose-primary-action"
                disabled={selectedCount === 0 || bulkLoading}
                onClick={() => setConfirmOpen(true)}
                type="button"
              >
                <CheckCircle2 size={16} /> Approve selected
              </button>
              <button
                className="secondary-action gov-btn-approve-all"
                disabled={draftMatchCount === 0 || bulkLoading}
                onClick={() => setConfirmAllOpen(true)}
                type="button"
              >
                <Layers size={16} /> Approve all matching ({draftMatchCount})
              </button>
              {confirmOpen ? (
                <div className="gov-confirm-dialog" role="dialog">
                  <p>
                    Approve <strong>{selectedCount}</strong> selected draft {catalog.bulkLabel} on this
                    page? This publishes them to the CDSS runtime.
                  </p>
                  <div className="gov-confirm-actions">
                    <button className="secondary-action" onClick={() => setConfirmOpen(false)} type="button">
                      Cancel
                    </button>
                    <button
                      className="primary-action dose-primary-action"
                      disabled={bulkLoading}
                      onClick={() => {
                        setConfirmOpen(false);
                        onBulkApprove();
                      }}
                      type="button"
                    >
                      Confirm approve
                    </button>
                  </div>
                </div>
              ) : null}
              {confirmAllOpen ? (
                <div className="gov-confirm-dialog gov-confirm-dialog--wide" role="dialog">
                  <p>
                    Approve <strong>all {draftMatchCount}</strong> draft {catalog.bulkLabel} matching your
                    current filters (every page in this tab)? This publishes them to the CDSS runtime.
                  </p>
                  <div className="gov-confirm-actions">
                    <button className="secondary-action" onClick={() => setConfirmAllOpen(false)} type="button">
                      Cancel
                    </button>
                    <button
                      className="primary-action dose-primary-action"
                      disabled={bulkLoading}
                      onClick={() => {
                        setConfirmAllOpen(false);
                        onBulkApproveAll();
                      }}
                      type="button"
                    >
                      Confirm approve all
                    </button>
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <span className="gov-permission-hint">clinical_lead required for bulk approve</span>
          )}
        </div>
      ) : null}
    </section>
  );
}
