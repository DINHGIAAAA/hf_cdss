import { ruleVisibilityMeta } from "../utils/ruleVisibility.js";

export function RuleVisibilityBadge({ status, title, compact = false }) {
  const visibility = ruleVisibilityMeta(status);

  return (
    <span
      className={`visibility-badge visibility-badge--${visibility.tone}`}
      title={title || visibility.hint}
    >
      {compact ? visibility.shortLabel : visibility.label}
      {!compact && <small>{visibility.shortLabel}</small>}
    </span>
  );
}
