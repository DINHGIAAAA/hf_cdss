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

function severityClass(severity) {
  if (severity === "high" || severity === "critical") return "danger";
  if (severity === "moderate") return "warning";
  return "muted";
}

function formatDrugSet(tokens = []) {
  if (!tokens.length) return "—";
  return tokens.join(", ");
}

export function DoseSafetyWarningDetail({ rule, onClose, onAction, actionLoading, canApprove, canAdmin }) {
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState("");
  const [versions, setVersions] = useState([]);

  useEffect(() => {
    if (!canAdmin || !rule?.dose_safety_warning_id) return;
    adminApi
      .getDoseSafetyWarningHistory(rule.dose_safety_warning_id)
      .then((data) => setHistory(data.items || []))
      .catch((err) => setHistoryError(err.message));
  }, [rule?.dose_safety_warning_id, canAdmin]);

  useEffect(() => {
    if (!rule?.dose_safety_warning_id) return;
    adminApi
      .getDoseSafetyWarningVersions(rule.dose_safety_warning_id)
      .then((data) => setVersions(data.items || []))
      .catch(() => setVersions([]));
  }, [rule?.dose_safety_warning_id]);

  if (!rule) return null;

  const body = rule.rule_body || {};

  return (
    <aside aria-label="Dose safety warning details" className="admin-detail-panel dose-detail-panel">
      <header className="admin-detail-header">
        <div>
          <h2>{rule.dose_safety_warning_id}</h2>
          <p className="dose-detail-meta">
            v{rule.version} · <span className={`badge ${statusClass(rule.status)}`}>{rule.status}</span>
            {" · "}
            <span className={`badge ${severityClass(rule.default_severity)}`}>{rule.default_severity}</span>
            {rule.safety_tier && (
              <>
                {" "}
                · <span className={`badge ${tierClass(rule.safety_tier)}`}>{rule.safety_tier}</span>
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
          <dt>Drug keys</dt>
          <dd>{formatDrugSet(rule.drug_keys)}</dd>
          <dt>Target</dt>
          <dd>{rule.target || "—"}</dd>
          <dt>Message</dt>
          <dd>{body.message || "—"}</dd>
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
                <li key={src.claim_id || src.document_id || i}>
                  {src.evidence || src.source_section || src.document_id || "Source claim"}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h3>Rule payload</h3>
          <pre className="dose-json-block">{JSON.stringify(body, null, 2)}</pre>
        </section>

        <VersionDiffPanel
          fetchDiff={adminApi.getDoseSafetyWarningDiff}
          ruleId={rule.id}
          versions={versions}
        />

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
        {rule.status === "draft" && canApprove && (
          <button
            className="primary-action dose-primary-action"
            disabled={actionLoading}
            onClick={() => onAction("approve", rule.id)}
            type="button"
          >
            <CheckCircle2 size={16} /> Approve for checking
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
