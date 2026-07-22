import { useEffect, useState } from "react";
import { CheckCircle2, History, RotateCcw, ShieldOff, XCircle } from "lucide-react";

import { adminApi } from "../api/index.js";
import { VersionDiffPanel } from "@shared/governance/VersionDiffPanel.jsx";
import { StatusHistoryList } from "@shared/governance/StatusHistoryList.jsx";
import { DetailFieldList, DetailMetaRow, CollapsiblePayload } from "@shared/governance/DetailFieldList.jsx";

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
          <DetailMetaRow
            badges={
              policy.safety_tier
                ? [{ label: policy.safety_tier, className: tierClass(policy.safety_tier) }]
                : []
            }
            id={policy.gdmt_policy_id}
            status={policy.status}
            statusClassName={statusClass(policy.status)}
            version={policy.version}
          />
        </div>
        <button aria-label="Close detail panel" className="icon-btn" onClick={onClose} type="button">
          <XCircle size={18} />
        </button>
      </header>

      <div className="admin-detail-body">
        <DetailFieldList
          fields={[
            { label: "Class key", value: policy.drug_class_key },
            { label: "Sort order", value: policy.sort_order },
            { label: "Evidence", value: policy.evidence_ref || "—", mono: true },
            { label: "Source", value: policy.source },
          ]}
        />

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

        <CollapsiblePayload data={body} title="Full payload" />

        <VersionDiffPanel fetchDiff={adminApi.getGdmtPolicyDiff} ruleId={policy.id} versions={versions} />

        {canAdmin && (
          <section>
            <h3>
              <History size={16} /> History
            </h3>
            <StatusHistoryList error={historyError} items={history} />
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
