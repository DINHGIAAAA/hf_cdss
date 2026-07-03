import { useEffect, useState } from "react";
import { CheckCircle2, History, RotateCcw, ShieldOff, XCircle } from "lucide-react";

import { adminApi } from "../api/index.js";
import { VersionDiffPanel } from "@shared/governance/VersionDiffPanel.jsx";

function statusClass(status) {
  if (status === "approved") return "success";
  if (status === "draft") return "warning";
  return "danger";
}

function tierClass(tier) {
  if (tier === "usable_rules") return "success";
  if (tier === "needs_refinement") return "warning";
  return "muted";
}

export function GdmtPolicyDetail({ policy, onClose, onAction, actionLoading, canApprove, canAdmin }) {
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState("");
  const [versions, setVersions] = useState([]);

  useEffect(() => {
    if (!canAdmin || !policy?.gdmt_policy_id) return;
    adminApi
      .getGdmtPolicyHistory(policy.gdmt_policy_id)
      .then((data) => setHistory(data.items || []))
      .catch((err) => setHistoryError(err.message));
  }, [policy?.gdmt_policy_id, canAdmin]);

  useEffect(() => {
    if (!policy?.gdmt_policy_id) return;
    adminApi
      .getGdmtPolicyVersions(policy.gdmt_policy_id)
      .then((data) => setVersions(data.items || []))
      .catch(() => setVersions([]));
  }, [policy?.gdmt_policy_id]);

  if (!policy) return null;

  const body = policy.policy_body || {};
  const guidance = body.guidance || {};

  return (
    <aside aria-label="GDMT policy details" className="admin-detail-panel dose-detail-panel">
      <header className="admin-detail-header">
        <div>
          <h2>{policy.display_label}</h2>
          <p className="dose-detail-meta">
            {policy.gdmt_policy_id} · v{policy.version} ·{" "}
            <span className={`badge ${statusClass(policy.status)}`}>{policy.status}</span>
            {policy.safety_tier && (
              <>
                {" "}
                · <span className={`badge ${tierClass(policy.safety_tier)}`}>{policy.safety_tier}</span>
              </>
            )}
          </p>
        </div>
        <button aria-label="Close detail panel" className="icon-btn" onClick={onClose} type="button">
          <XCircle size={18} />
        </button>
      </header>

      <div className="admin-detail-body">
        <dl className="detail-grid">
          <dt>Class key</dt>
          <dd>{policy.drug_class_key}</dd>
          <dt>Sort order</dt>
          <dd>{policy.sort_order}</dd>
          <dt>Evidence</dt>
          <dd>{policy.evidence_ref || "—"}</dd>
          <dt>Source</dt>
          <dd>{policy.source}</dd>
        </dl>

        {(guidance.actions || []).length > 0 && (
          <section>
            <h3>Actions</h3>
            <ul className="source-list">
              {guidance.actions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        )}

        {(guidance.monitoring || body.monitoring || []).length > 0 && (
          <section>
            <h3>Monitoring</h3>
            <ul className="source-list">
              {(guidance.monitoring || body.monitoring || []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h3>Policy payload</h3>
          <pre className="dose-json-block">{JSON.stringify(body, null, 2)}</pre>
        </section>

        <VersionDiffPanel fetchDiff={adminApi.getGdmtPolicyDiff} ruleId={policy.id} versions={versions} />

        {canAdmin && (
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
        {policy.status === "draft" && canApprove && (
          <button
            className="primary-action dose-primary-action"
            disabled={actionLoading}
            onClick={() => onAction("approve", policy.id)}
            type="button"
          >
            <CheckCircle2 size={16} /> Approve for recommendations
          </button>
        )}
        {policy.status === "approved" && canAdmin && (
          <button
            className="danger-action"
            disabled={actionLoading}
            onClick={() => onAction("retire", policy.id)}
            type="button"
          >
            <ShieldOff size={16} /> Retire
          </button>
        )}
        {policy.status === "retired" && canAdmin && (
          <button
            className="secondary-action"
            disabled={actionLoading}
            onClick={() => onAction("unretire", policy.id)}
            type="button"
          >
            <RotateCcw size={16} /> Restore
          </button>
        )}
      </footer>
    </aside>
  );
}
