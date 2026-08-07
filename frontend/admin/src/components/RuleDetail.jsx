import { useEffect, useState } from "react";
import { History, XCircle } from "lucide-react";

import { adminApi } from "../api/index.js";
import { CatalogStatusActions } from "@shared/governance/CatalogStatusActions.jsx";
import { VersionDiffPanel } from "@shared/governance/VersionDiffPanel.jsx";
import { StatusHistoryList } from "@shared/governance/StatusHistoryList.jsx";
import {
  ClinicalSourcesList,
  DetailFieldList,
  DetailMetaRow,
} from "@shared/governance/DetailFieldList.jsx";
import { AdminDetailModal } from "@shared/governance/AdminDetailModal.jsx";
import {
  constraintRuleTitle,
  formatConstraintConditionFields,
} from "@shared/governance/displayNames.js";
import {
  evidenceLinkDetailField,
  pipelineSourceDetailField,
  textMatchesClinicalSources,
} from "@shared/governance/catalogDetailReview.js";
import { ConstraintConditionPanel } from "@shared/governance/ConstraintConditionPanel.jsx";

function statusClass(status) {
  if (status === "approved") return "success";
  if (status === "draft") return "warning";
  return "danger";
}

function ruleNeedsCondition(rule) {
  const meta = rule?.metadata || {};
  if (meta.needs_condition === true || meta.needs_condition === "true") return true;
  if (meta.needs_condition === false || meta.needs_condition === "false") return false;
  return meta.safety_tier === "needs_condition_refinement";
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

  const conditionFields = formatConstraintConditionFields(rule);
  const needsCondition = ruleNeedsCondition(rule);
  const safetyTier = rule.metadata?.safety_tier || null;
  const sources = rule.clinical_sources || [];

  const detailFields = [
    { label: "Action", value: rule.action },
    { label: "Target class", value: rule.target_drug_class || "—" },
    {
      label: "Severity",
      value: (rule.severity_any || []).length ? rule.severity_any : "—",
    },
  ];
  if (rule.reason && !textMatchesClinicalSources(rule.reason, sources)) {
    detailFields.push({ label: "Reason", value: rule.reason, wide: true });
  }
  detailFields.push({
    label: "Risks",
    value: (rule.risk_names || []).length ? rule.risk_names : "—",
  });
  const evidenceField = evidenceLinkDetailField(rule.evidence_ref, sources);
  if (evidenceField) detailFields.push(evidenceField);
  const sourceField = pipelineSourceDetailField(rule.source);
  if (sourceField) detailFields.push(sourceField);

  return (
    <AdminDetailModal ariaLabel="Rule details" onClose={onClose}>
      <header className="admin-detail-header">
        <div>
          <h2>{constraintRuleTitle(rule)}</h2>
          <DetailMetaRow
            badges={
              safetyTier
                ? [{ label: String(safetyTier).replace(/_/g, " "), className: "muted" }]
                : []
            }
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
        <ConstraintConditionPanel
          fields={conditionFields}
          needsCondition={needsCondition}
          rule={rule}
        />

        <DetailFieldList fields={detailFields} />

        <ClinicalSourcesList sources={sources} />

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
        <CatalogStatusActions
          actionLoading={actionLoading}
          approveButtonClassName="primary-action"
          approveLabel="Approve"
          canAdmin={canAdmin}
          canApprove={canApprove}
          onAction={onAction}
          recordId={rule.id}
          status={rule.status}
        />
      </footer>
    </AdminDetailModal>
  );
}
