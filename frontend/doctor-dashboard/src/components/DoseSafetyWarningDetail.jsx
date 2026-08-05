import { useEffect, useState } from "react";
import { History, XCircle } from "lucide-react";

import { CatalogStatusActions } from "@shared/governance/CatalogStatusActions.jsx";
import { adminApi } from "../api/index.js";
import { VersionDiffPanel } from "@shared/governance/VersionDiffPanel.jsx";
import { StatusHistoryList } from "@shared/governance/StatusHistoryList.jsx";
import {
  ClinicalSourcesList,
  CollapsiblePayload,
  DetailFieldList,
  DetailMetaRow,
} from "@shared/governance/DetailFieldList.jsx";
import { AdminDetailModal } from "@shared/governance/AdminDetailModal.jsx";
import { doseSafetyWarningTitle } from "@shared/governance/displayNames.js";
import {
  evidenceLinkDetailField,
  pipelineSourceDetailField,
  textMatchesClinicalSources,
} from "@shared/governance/catalogDetailReview.js";

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
  const sources = rule.clinical_sources || [];

  const summaryFields = [
    {
      label: "Drug keys",
      value: (rule.drug_keys || []).length ? rule.drug_keys : "—",
    },
  ];
  if (rule.target) {
    summaryFields.push({ label: "Target", value: rule.target });
  }
  const message = body.message;
  if (message && !textMatchesClinicalSources(message, sources)) {
    summaryFields.push({ label: "Clinical message", value: message, wide: true });
  }
  const evidenceField = evidenceLinkDetailField(rule.evidence_ref, sources);
  if (evidenceField) summaryFields.push(evidenceField);
  const sourceField = pipelineSourceDetailField(rule.source);
  if (sourceField) summaryFields.push(sourceField);

  return (
    <AdminDetailModal ariaLabel="Dose safety warning details" className="dose-detail-panel" onClose={onClose}>
      <header className="admin-detail-header">
        <div>
          <h2>{doseSafetyWarningTitle(rule)}</h2>
          <DetailMetaRow
            badges={[
              { label: rule.default_severity, className: severityClass(rule.default_severity) },
              ...(rule.safety_tier
                ? [{ label: rule.safety_tier, className: tierClass(rule.safety_tier) }]
                : []),
            ]}
            id={rule.dose_safety_warning_id}
            status={rule.status}
            statusClassName={statusClass(rule.status)}
            version={rule.version}
          />
        </div>
        <button aria-label="Close detail panel" className="icon-btn" onClick={onClose} type="button">
          <XCircle size={18} />
        </button>
      </header>

      <div className="admin-detail-body">
        <DetailFieldList fields={summaryFields} />

        <ClinicalSourcesList sources={sources} />

        <CollapsiblePayload
          clinicalSources={sources}
          data={body}
          defaultOpen={false}
          title="Trigger & monitoring logic"
        />

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
            <StatusHistoryList error={historyError} items={history} />
          </section>
        )}
      </div>

      <footer className="admin-detail-actions">
        <CatalogStatusActions
          actionLoading={actionLoading}
          approveLabel="Approve for dosing"
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
