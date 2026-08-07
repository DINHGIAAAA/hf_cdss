import { ruleVisibilityMeta } from "../utils/ruleVisibility.js";

export function RuleVisibilityBadge({ status, title, compact = false }) {
  const visibility = ruleVisibilityMeta(status);

  return (
    <span
      className={`visibility-badge visibility-badge--${visibility.tone}`}
      title={title || visibility.hint}
    >
      {compact ? (
        visibility.shortLabel
      ) : (
        <>
          <span className="visibility-badge__primary">{visibility.label}</span>
          <small className="visibility-badge__secondary">{visibility.shortLabel}</small>
        </>
      )}
    </span>
  );
}
