import { useState } from "react";
import { CheckCircle2, Filter, Search, X } from "lucide-react";

export function ApprovalToolbar({
  catalog,
  filters,
  onFilterChange,
  onApplyFilters,
  onClearFilters,
  selectedCount,
  allVisibleSelected,
  onToggleAll,
  onBulkApprove,
  bulkLoading,
  canBulkApprove,
  showBulk,
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <section aria-label="Approval filters and bulk actions" className="gov-toolbar">
      <div className="gov-toolbar-filters">
        <div className="gov-toolbar-heading">
          <Filter aria-hidden size={16} />
          <strong>Filters</strong>
        </div>
        <div className="gov-filter-grid">
          {catalog.filters.map((field) => (
            <label className="gov-filter-field" key={field.key}>
              <span>{field.label}</span>
              {field.type === "select" ? (
                <select
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
        <div className="gov-toolbar-actions">
          <button className="secondary-action" onClick={onApplyFilters} type="button">
            <Search size={14} /> Apply filters
          </button>
          <button className="link-btn" onClick={onClearFilters} type="button">
            <X size={14} /> Clear
          </button>
        </div>
      </div>

      {showBulk && (
        <div className="gov-bulk-bar">
          <label className="gov-select-all">
            <input
              checked={allVisibleSelected}
              onChange={onToggleAll}
              type="checkbox"
            />
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
                <CheckCircle2 size={16} /> Bulk approve
              </button>
              {confirmOpen && (
                <div className="gov-confirm-dialog" role="dialog">
                  <p>
                    Approve <strong>{selectedCount}</strong> draft {catalog.bulkLabel}? This publishes them
                    to the CDSS runtime.
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
              )}
            </>
          ) : (
            <span className="gov-permission-hint">clinical_lead required for bulk approve</span>
          )}
        </div>
      )}
    </section>
  );
}
