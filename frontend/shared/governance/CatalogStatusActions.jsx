import { CheckCircle2, RotateCcw, ShieldOff } from "lucide-react";

/** Approve / retire / restore actions for governance catalog detail panels. */
export function CatalogStatusActions({
  status,
  recordId,
  canApprove,
  canAdmin,
  actionLoading,
  onAction,
  approveLabel,
  approveDisabledHint = false,
  approveButtonClassName = "primary-action dose-primary-action",
}) {
  return (
    <>
      {status === "draft" && canApprove ? (
        <>
          <button
            className={approveButtonClassName}
            disabled={actionLoading}
            onClick={() => onAction("approve", recordId)}
            type="button"
          >
            <CheckCircle2 size={16} /> {approveLabel}
          </button>
          <button
            className="danger-action"
            disabled={actionLoading}
            onClick={() => onAction("retire", recordId)}
            type="button"
          >
            <ShieldOff size={16} /> Retire draft
          </button>
        </>
      ) : null}
      {status === "draft" && approveDisabledHint && !canApprove ? (
        <button
          className="primary-action"
          disabled
          title="Only clinical_lead can approve or retire draft rules"
          type="button"
        >
          <CheckCircle2 size={16} /> Approve (clinical_lead required)
        </button>
      ) : null}
      {status === "approved" && canAdmin ? (
        <button
          className="danger-action"
          disabled={actionLoading}
          onClick={() => onAction("retire", recordId)}
          type="button"
        >
          <ShieldOff size={16} /> Retire
        </button>
      ) : null}
      {status === "retired" && canAdmin ? (
        <button
          className="secondary-action"
          disabled={actionLoading}
          onClick={() => onAction("unretire", recordId)}
          type="button"
        >
          <RotateCcw size={16} /> Restore
        </button>
      ) : null}
    </>
  );
}
