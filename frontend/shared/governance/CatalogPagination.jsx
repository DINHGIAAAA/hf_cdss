import { ChevronLeft, ChevronRight } from "lucide-react";

import "./governance-pagination.css";

function pageRange(page, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const pages = new Set([1, totalPages, page, page - 1, page + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < sorted.length; i += 1) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) out.push("gap");
    out.push(sorted[i]);
  }
  return out;
}

export function CatalogPagination({ page, pageSize, total, onPageChange, loading = false }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  const pages = pageRange(page, totalPages);

  return (
    <nav aria-label="Catalog pagination" className="gov-pagination">
      <div className="gov-pagination-inner">
        <p className="gov-pagination-summary">
          Showing {from}–{to} of {total.toLocaleString()}
        </p>
        <div className="gov-pagination-controls">
        <button
          className="gov-pagination-btn"
          disabled={loading || page <= 1}
          onClick={() => onPageChange(page - 1)}
          type="button"
        >
          <ChevronLeft aria-hidden size={16} />
          Previous
        </button>
        <div className="gov-pagination-pages">
          {pages.map((entry, index) =>
            entry === "gap" ? (
              <span className="gov-pagination-gap" key={`gap-${index}`}>…</span>
            ) : (
              <button
                className={`gov-pagination-page${entry === page ? " is-active" : ""}`}
                disabled={loading || entry === page}
                key={entry}
                onClick={() => onPageChange(entry)}
                type="button"
              >
                {entry}
              </button>
            ),
          )}
        </div>
        <button
          className="gov-pagination-btn"
          disabled={loading || page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          type="button"
        >
          Next
          <ChevronRight aria-hidden size={16} />
        </button>
        </div>
      </div>
    </nav>
  );
}
