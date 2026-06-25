import { useEffect, useState } from "react";
import { CheckCircle2, History, RotateCcw, ShieldOff, XCircle } from "lucide-react";

import { adminApi } from "../api/index.js";

function statusClass(status) {
  if (status === "approved") return "success";
  if (status === "draft") return "warning";
  return "danger";
}

export function RuleDetail({ rule, onClose, onAction, actionLoading, canApprove, canAdmin, canRead }) {
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState("");

  useEffect(() => {
    if (!canRead || !rule?.constraint_id) return;
    adminApi
      .getHistory(rule.constraint_id)
      .then((data) => setHistory(data.items || []))
      .catch((err) => setHistoryError(err.message));
  }, [rule?.constraint_id, canRead]);

  if (!rule) return null;

  const showApprove = rule.status === "draft";
  const approveDisabled = showApprove && !canApprove;

  return (
    <aside aria-label="Rule details" className="admin-detail-panel">
      <header className="admin-detail-header">
        <div className="admin-clip">
          <h2 title={rule.constraint_id}>{rule.constraint_id}</h2>
          <p>
            v{rule.version} · <span className={`badge ${statusClass(rule.status)}`}>{rule.status}</span>
          </p>
        </div>
        <button className="icon-btn" onClick={onClose} type="button">
          <XCircle size={18} />
        </button>
      </header>

      <div className="admin-detail-body">
        <dl className="detail-grid">
          <dt>Action</dt>
          <dd>{rule.action}</dd>
          <dt>Target class</dt>
          <dd>{rule.target_drug_class || "—"}</dd>
          <dt>Reason</dt>
          <dd>{rule.reason}</dd>
          <dt>Risks</dt>
          <dd>{(rule.risk_names || []).join(", ") || "—"}</dd>
          <dt>Evidence</dt>
          <dd>{rule.evidence_ref || "—"}</dd>
          <dt>Source</dt>
          <dd>{rule.source}</dd>
        </dl>

        {(rule.clinical_sources || []).length > 0 && (
          <section>
            <h3>Clinical sources</h3>
            <ul className="source-list">
              {rule.clinical_sources.map((src, i) => (
                <li key={`${src.source_url || i}`}>
                  {src.title || src.source_url || JSON.stringify(src)}
                </li>
              ))}
            </ul>
          </section>
        )}

        {canRead && (
          <section>
            <h3>
              <History size={16} /> History
            </h3>
            {historyError && <p className="inline-error">{historyError}</p>}
            <ul className="history-list">
              {history.map((item) => (
                <li key={item.history_id}>
                  <strong>
                    {item.status_from || "—"} → {item.status_to}
                  </strong>
                  <span>
                    {item.changed_by} · {new Date(item.changed_at).toLocaleString()}
                  </span>
                  {item.reason && <small>{item.reason}</small>}
                </li>
              ))}
              {history.length === 0 && !historyError && <li>No history recorded.</li>}
            </ul>
          </section>
        )}
      </div>

      <footer className="admin-detail-actions">
        {showApprove && canApprove && (
          <button
            className="primary-action"
            disabled={actionLoading}
            onClick={() => onAction("approve", rule.id)}
            type="button"
          >
            <CheckCircle2 size={16} /> Approve
          </button>
        )}
        {approveDisabled && (
          <button
            className="primary-action"
            disabled
            title="Only clinical_lead can approve draft rules"
            type="button"
          >
            <CheckCircle2 size={16} /> Approve (clinical_lead required)
          </button>
        )}
        {rule.status === "approved" && canAdmin && (
          <button
            className="danger-action"
            disabled={actionLoading}
            onClick={() => onAction("retire", rule.id)}
            type="button"
          >
            <ShieldOff size={16} /> Retire
          </button>
        )}
        {rule.status === "retired" && canAdmin && (
          <button
            className="secondary-action"
            disabled={actionLoading}
            onClick={() => onAction("unretire", rule.id)}
            type="button"
          >
            <RotateCcw size={16} /> Restore
          </button>
        )}
      </footer>
    </aside>
  );
}
