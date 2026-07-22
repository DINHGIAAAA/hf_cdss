import { useEffect, useState } from "react";
import { CheckCircle2, History, RotateCcw, ShieldOff, XCircle } from "lucide-react";

import { adminApi } from "../api/index.js";
import { VersionDiffPanel } from "@shared/governance/VersionDiffPanel.jsx";
import { StatusHistoryList } from "@shared/governance/StatusHistoryList.jsx";
import {
  ClinicalSourcesList,
  CollapsiblePayload,
  DetailFieldList,
  DetailMetaRow,
} from "@shared/governance/DetailFieldList.jsx";
import { doseSafetyWarningTitle } from "@shared/governance/displayNames.js";

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

  return (
    <aside aria-label="Dose safety warning details" className="admin-detail-panel dose-detail-panel">
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
        <DetailFieldList
          fields={[
            { label: "Drug keys", value: (rule.drug_keys || []).length ? rule.drug_keys : "—" },
            { label: "Target", value: rule.target || "—" },
            { label: "Message", value: body.message || "—", wide: true },
            { label: "Evidence", value: rule.evidence_ref || "—", mono: true },
            { label: "Source", value: rule.source },
          ]}
        />

        <ClinicalSourcesList sources={rule.clinical_sources || []} />

        <CollapsiblePayload data={body} title="Full payload" />

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
