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

function formatAmount(amount) {
  if (!amount || amount.value == null) return null;
  const label = amount.label || `${amount.value} ${amount.unit || "mg"}`;
  return `${label} · ${amount.frequency || "—"}`;
}

function summarizeRuleBody(body = {}) {
  const lines = [];
  if (body.standard_dose) lines.push({ label: "Standard", value: formatAmount(body.standard_dose) });
  if (body.reduced_dose) lines.push({ label: "Reduced", value: formatAmount(body.reduced_dose) });
  if (body.recommended_dose) lines.push({ label: "Recommended", value: formatAmount(body.recommended_dose) });
  if (body.starting_dose) lines.push({ label: "Starting", value: formatAmount(body.starting_dose) });
  if (body.target_dose) lines.push({ label: "Target", value: formatAmount(body.target_dose) });
  if (Array.isArray(body.dose_steps) && body.dose_steps.length) {
    lines.push({
      label: "Steps",
      value: body.dose_steps.map((step) => formatAmount(step)).filter(Boolean).join(" → "),
    });
  }
  if (body.crcl_threshold != null) {
    lines.push({ label: "CrCl threshold", value: `${body.crcl_threshold} mL/min` });
  }
  if (Array.isArray(body.reduction_criteria) && body.reduction_criteria.length) {
    lines.push({
      label: "Reduction criteria",
      value: body.reduction_criteria.map((item) => item.label || item.field).join("; "),
    });
  }
  return lines;
}

export function DoseRuleDetail({ rule, onClose, onAction, actionLoading, canApprove, canAdmin }) {
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState("");

  const [versions, setVersions] = useState([]);

  useEffect(() => {
    if (!canAdmin || !rule?.dose_rule_id) return;
    adminApi
      .getDoseRuleHistory(rule.dose_rule_id)
      .then((data) => setHistory(data.items || []))
      .catch((err) => setHistoryError(err.message));
  }, [rule?.dose_rule_id, canAdmin]);

  useEffect(() => {
    if (!rule?.dose_rule_id) return;
    adminApi
      .getDoseRuleVersions(rule.dose_rule_id)
      .then((data) => setVersions(data.items || []))
      .catch(() => setVersions([]));
  }, [rule?.dose_rule_id]);

  if (!rule) return null;

  const body = rule.rule_body || {};
  const summary = summarizeRuleBody(body);

  return (
    <aside aria-label="Dose rule details" className="admin-detail-panel dose-detail-panel">
      <header className="admin-detail-header">
        <div>
          <h2>{rule.dose_rule_id}</h2>
          <p className="dose-detail-meta">
            v{rule.version} · <span className={`badge ${statusClass(rule.status)}`}>{rule.status}</span>
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
          <dt>Calculation</dt>
          <dd>
            <code className="dose-code">{rule.calculation_type}</code>
          </dd>
          <dt>Drug class</dt>
          <dd>{rule.drug_class || "—"}</dd>
          <dt>Drug keys</dt>
          <dd>{(rule.drug_keys || []).join(", ") || "—"}</dd>
          <dt>Evidence</dt>
          <dd>{rule.evidence_ref || "—"}</dd>
          <dt>Source</dt>
          <dd>{rule.source}</dd>
        </dl>

        {summary.length > 0 && (
          <section>
            <h3>Dose summary</h3>
            <dl className="detail-grid dose-summary-grid">
              {summary.map((item) => (
                <div className="dose-summary-row" key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {(body.monitoring || []).length > 0 && (
          <section>
            <h3>Monitoring</h3>
            <ul className="source-list">
              {body.monitoring.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        )}

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
          fetchDiff={adminApi.getDoseRuleDiff}
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
            <CheckCircle2 size={16} /> Approve for dosing
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
