import { useEffect, useState } from "react";
import { CheckCircle2, History, RotateCcw, ShieldOff, XCircle } from "lucide-react";

import { adminApi } from "../api/index.js";
import { VersionDiffPanel } from "@shared/governance/VersionDiffPanel.jsx";
import { StatusHistoryList } from "@shared/governance/StatusHistoryList.jsx";
import {
  ClinicalSourcesList,
  DetailFieldList,
  DetailMetaRow,
} from "@shared/governance/DetailFieldList.jsx";
import { constraintRuleTitle } from "@shared/governance/displayNames.js";

function statusClass(status) {
  if (status === "approved") return "success";
  if (status === "draft") return "warning";
  return "danger";
}

export function RuleDetail({ rule, onClose, onAction, actionLoading, canApprove, canAdmin }) {
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState("");
  const [versions, setVersions] = useState([]);

  useEffect(() => {
    if (!canAdmin || !rule?.constraint_id) return;
    adminApi
      .getHistory(rule.constraint_id)
      .then((data) => setHistory(data.items || []))
      .catch((err) => setHistoryError(err.message));
  }, [rule?.constraint_id, canAdmin]);

  useEffect(() => {
    if (!rule?.constraint_id) return;
    adminApi
      .getVersions(rule.constraint_id)
      .then((data) => setVersions(data.items || []))
      .catch(() => setVersions([]));
  }, [rule?.constraint_id]);

  if (!rule) return null;

  return (
    <aside aria-label="Rule details" className="admin-detail-panel">
      <header className="admin-detail-header">
        <div>
          <h2>{constraintRuleTitle(rule)}</h2>
          <DetailMetaRow
            id={rule.constraint_id}
            status={rule.status}
            statusClassName={statusClass(rule.status)}
            version={rule.version}
          />
        </div>
        <button className="icon-btn" onClick={onClose} type="button">
          <XCircle size={18} />
        </button>
      </header>

      <div className="admin-detail-body">
        <DetailFieldList
          fields={[
            { label: "Action", value: rule.action },
            { label: "Target class", value: rule.target_drug_class || "—" },
            { label: "Reason", value: rule.reason, wide: true },
            { label: "Risks", value: (rule.risk_names || []).length ? rule.risk_names : "—" },
            { label: "Evidence", value: rule.evidence_ref || "—", mono: true },
            { label: "Source", value: rule.source },
          ]}
        />

        <ClinicalSourcesList sources={rule.clinical_sources || []} />

        <VersionDiffPanel
          fetchDiff={adminApi.getConstraintRuleDiff}
          ruleId={rule.id}
          versions={versions}
        />

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
        {rule.status === "draft" && canApprove && (
          <button
            className="primary-action"
            disabled={actionLoading}
            onClick={() => onAction("approve", rule.id)}
            type="button"
          >
            <CheckCircle2 size={16} /> Approve
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
