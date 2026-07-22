const CARDS = [
  { id: "draft", label: "Draft" },
  { id: "approved", label: "Approved" },
  { id: "retired", label: "Retired" },
];

/**
 * Global status counts (independent of the active status tab filter).
 * Cards switch the list tab when clicked.
 */
export function StatusCountCards({
  className = "admin-stats",
  cardClassName = "stat-card",
  draftCount,
  approvedCount,
  retiredCount,
  activeTab,
  onSelect,
  hints = {},
}) {
  const counts = {
    draft: draftCount,
    approved: approvedCount,
    retired: retiredCount,
  };

  return (
    <div className={className}>
      {CARDS.map((card) => {
        const active = activeTab === card.id;
        const hint = hints[card.id];
        return (
          <button
            aria-pressed={active}
            className={`${cardClassName}${active ? " active" : ""}`}
            key={card.id}
            onClick={() => onSelect?.(card.id)}
            type="button"
          >
            <span>{card.label}</span>
            <strong>{counts[card.id] ?? "—"}</strong>
            {hint ? <small>{hint}</small> : null}
          </button>
        );
      })}
    </div>
  );
}

/** Append "(n)" to Draft / Approved / Retired tab labels. */
export function statusTabLabel(tabId, label, counts) {
  if (!counts || tabId === "all") return label;
  const value = counts[`${tabId}_count`];
  if (value == null) return label;
  return `${label} (${value})`;
}
