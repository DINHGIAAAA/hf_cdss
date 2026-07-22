import { ArrowRight } from "lucide-react";

function formatChangedAt(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function StatusPill({ status }) {
  const label = status || "—";
  const tone = status === "approved" ? "success" : status === "draft" ? "warning" : status === "retired" ? "danger" : "neutral";
  return <span className={`history-status-pill history-status-pill--${tone}`}>{label}</span>;
}

/**
 * Readable status-change history for governance catalogs.
 */
export function StatusHistoryList({ items = [], error = "", emptyLabel = "No history recorded." }) {
  if (error) {
    return <p className="inline-error">{error}</p>;
  }

  if (!items.length) {
    return <p className="history-empty">{emptyLabel}</p>;
  }

  return (
    <ul className="history-list">
      {items.map((item) => (
        <li className="history-item" key={item.history_id}>
          <div className="history-item-transition">
            <StatusPill status={item.status_from} />
            <ArrowRight aria-hidden className="history-item-arrow" size={14} />
            <StatusPill status={item.status_to} />
          </div>
          <div className="history-item-meta">
            <span className="history-item-actor">{item.changed_by || "Unknown"}</span>
            <span className="history-item-sep" aria-hidden>
              ·
            </span>
            <time className="history-item-time" dateTime={item.changed_at || undefined}>
              {formatChangedAt(item.changed_at)}
            </time>
          </div>
          {item.reason ? <p className="history-item-reason">{item.reason}</p> : null}
        </li>
      ))}
    </ul>
  );
}
