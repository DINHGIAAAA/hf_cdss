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
import {
  evidenceLinkDetailField,
  pipelineSourceDetailField,
} from "@shared/governance/catalogDetailReview.js";
import { gdmtPolicyReviewFields } from "@shared/governance/gdmtPolicyReview.js";

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
  const sources = policy.clinical_sources || [];

  const headerFields = [
    { label: "Class key", value: policy.drug_class_key },
    { label: "Sort order", value: policy.sort_order },
  ];
  const evidenceField = evidenceLinkDetailField(policy.evidence_ref, sources);
  if (evidenceField) headerFields.push(evidenceField);
  const sourceField = pipelineSourceDetailField(policy.source);
  if (sourceField) headerFields.push(sourceField);

  return (
    <AdminDetailModal ariaLabel="GDMT policy details" className="dose-detail-panel" onClose={onClose}>
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
        <DetailFieldList fields={headerFields} />

        <ClinicalSourcesList sources={sources} />

        <DetailFieldList fields={gdmtPolicyReviewFields(policy)} />

        <CollapsiblePayload
          clinicalSources={sources}
          data={body}
          defaultOpen={false}
          title="Policy logic"
        />

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
        <CatalogStatusActions
          actionLoading={actionLoading}
          approveLabel="Approve for recommendations"
          canAdmin={canAdmin}
          canApprove={canApprove}
          onAction={onAction}
          recordId={policy.id}
          status={policy.status}
        />
      </footer>
    </AdminDetailModal>
  );
}
