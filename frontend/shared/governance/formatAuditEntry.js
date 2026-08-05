const LEGACY_AUTO_RETIRE_PREFIX = "system_auto_retire_by_";
const SUPERSEDE_RETIRED_BY_PREFIX = "system:superseded-by-";

/**
 * Turn stored changed_by / retired_by into text clinicians can read.
 */
export function formatGovernanceActor(actor) {
  if (!actor) return "Unknown";
  if (actor.startsWith(LEGACY_AUTO_RETIRE_PREFIX)) {
    const approver = actor.slice(LEGACY_AUTO_RETIRE_PREFIX.length);
    return `Automatic (newer version approved by ${approver})`;
  }
  if (actor.startsWith(SUPERSEDE_RETIRED_BY_PREFIX)) {
    const approver = actor.slice(SUPERSEDE_RETIRED_BY_PREFIX.length);
    return `Automatic (newer version approved by ${approver})`;
  }
  return actor;
}

/**
 * Expand legacy or terse history reasons for the status history panel.
 */
export function formatGovernanceReason(reason, changedBy) {
  if (!reason) return null;
  const legacy = /^Auto-retired due to new version approval \(rule_id: (\d+)\)$/.exec(reason);
  if (legacy) {
    const approver = extractApproverFromActor(changedBy) || "a clinical lead";
    return (
      `This approved copy was retired when ${approver} approved a newer draft ` +
      `(record #${legacy[1]}). Only one approved version is active per rule.`
    );
  }
  return reason;
}

function extractApproverFromActor(actor) {
  if (!actor) return null;
  if (actor.startsWith(LEGACY_AUTO_RETIRE_PREFIX)) {
    return actor.slice(LEGACY_AUTO_RETIRE_PREFIX.length);
  }
  if (actor.startsWith(SUPERSEDE_RETIRED_BY_PREFIX)) {
    return actor.slice(SUPERSEDE_RETIRED_BY_PREFIX.length);
  }
  const automatic = /^Automatic \(newer version approved by (.+)\)$/.exec(actor);
  return automatic ? automatic[1] : null;
}
