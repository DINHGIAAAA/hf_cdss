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
import { InteractionDrugSetFields } from "@shared/governance/InteractionDrugSetFields.jsx";
import { AdminDetailModal } from "@shared/governance/AdminDetailModal.jsx";
import { interactionRuleTitle } from "@shared/governance/displayNames.js";
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

export function InteractionRuleDetail({ rule, onClose, onAction, actionLoading, canApprove, canAdmin }) {
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState("");
  const [versions, setVersions] = useState([]);

  useEffect(() => {
    if (!canAdmin || !rule?.interaction_rule_id) return;
    adminApi
      .getInteractionRuleHistory(rule.interaction_rule_id)
      .then((data) => setHistory(data.items || []))
      .catch((err) => setHistoryError(err.message));
  }, [rule?.interaction_rule_id, canAdmin]);

  useEffect(() => {
    if (!rule?.interaction_rule_id) return;
    adminApi
      .getInteractionRuleVersions(rule.interaction_rule_id)
      .then((data) => setVersions(data.items || []))
      .catch(() => setVersions([]));
  }, [rule?.interaction_rule_id]);

  if (!rule) return null;

  const body = rule.rule_body || {};
  const sources = rule.clinical_sources || [];

  const headerFields = [
    { label: "Action", value: body.action || "—" },
  ];
  const message = body.message;
  if (message && !textMatchesClinicalSources(message, sources)) {
    headerFields.push({ label: "Clinical message", value: message, wide: true });
  }
  const evidenceField = evidenceLinkDetailField(rule.evidence_ref, sources);
  if (evidenceField) headerFields.push(evidenceField);
  const sourceField = pipelineSourceDetailField(rule.source);
  if (sourceField) headerFields.push(sourceField);

  return (
    <AdminDetailModal ariaLabel="Interaction rule details" className="dose-detail-panel" onClose={onClose}>
      <header className="admin-detail-header">
        <div>
          <h2>{interactionRuleTitle(rule)}</h2>
          <DetailMetaRow
            badges={[
              { label: rule.severity, className: severityClass(rule.severity) },
              ...(rule.safety_tier
                ? [{ label: rule.safety_tier, className: tierClass(rule.safety_tier) }]
                : []),
            ]}
            id={rule.interaction_rule_id}
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
        <InteractionDrugSetFields drugSetA={rule.drug_set_a} drugSetB={rule.drug_set_b} />
        {rule.target || body.target ? (
          <DetailFieldList fields={[{ label: "Target", value: rule.target || body.target }]} />
        ) : null}
        <DetailFieldList fields={headerFields} />

        {(body.monitoring || []).length > 0 && (
          <section>
            <h3>Monitoring</h3>
            <DetailFieldList fields={[{ label: "Items", value: body.monitoring }]} />
          </section>
        )}

        {(body.escalation || []).length > 0 && (
          <CollapsiblePayload data={body.escalation} title="Escalation" />
        )}

        <ClinicalSourcesList sources={sources} />

        <CollapsiblePayload
          clinicalSources={sources}
          data={body}
          defaultOpen={false}
          title="Interaction logic"
        />

        <VersionDiffPanel
          fetchDiff={adminApi.getInteractionRuleDiff}
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
          approveLabel="Approve for checking"
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
