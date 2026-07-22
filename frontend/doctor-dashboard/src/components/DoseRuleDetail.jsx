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
import { doseRuleTitle } from "@shared/governance/displayNames.js";

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
          <h2>{doseRuleTitle(rule)}</h2>
          <DetailMetaRow
            badges={
              rule.safety_tier ? [{ label: rule.safety_tier, className: tierClass(rule.safety_tier) }] : []
            }
            id={rule.dose_rule_id}
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
            {
              label: "Calculation",
              value: <code className="dose-code">{rule.calculation_type}</code>,
            },
            { label: "Drug class", value: rule.drug_class || "—" },
            { label: "Drug keys", value: (rule.drug_keys || []).length ? rule.drug_keys : "—" },
            { label: "Evidence", value: rule.evidence_ref || "—", mono: true },
            { label: "Source", value: rule.source },
          ]}
        />

        {summary.length > 0 && (
          <section>
            <h3>Dose summary</h3>
            <DetailFieldList fields={summary.map((item) => ({ label: item.label, value: item.value }))} />
          </section>
        )}

        {(body.monitoring || []).length > 0 && (
          <section>
            <h3>Monitoring</h3>
            <DetailFieldList fields={[{ label: "Items", value: body.monitoring }]} />
          </section>
        )}

        <ClinicalSourcesList sources={rule.clinical_sources || []} />

        <CollapsiblePayload data={body} title="Full payload" />

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
