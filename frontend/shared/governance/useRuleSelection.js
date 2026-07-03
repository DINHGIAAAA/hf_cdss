import { useMemo, useState } from "react";

export function useRuleSelection(items, { selectable = (rule) => rule.status === "draft" } = {}) {
  const [selectedIds, setSelectedIds] = useState(() => new Set());

  const selectableItems = useMemo(
    () => items.filter((item) => selectable(item)),
    [items, selectable],
  );

  const selectableIds = useMemo(() => selectableItems.map((item) => item.id), [selectableItems]);

  function toggleOne(ruleId) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(ruleId)) next.delete(ruleId);
      else next.add(ruleId);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelectedIds((prev) => {
      const allSelected = selectableIds.length > 0 && selectableIds.every((id) => prev.has(id));
      if (allSelected) return new Set();
      return new Set(selectableIds);
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  const allVisibleSelected =
    selectableIds.length > 0 && selectableIds.every((id) => selectedIds.has(id));

  return {
    selectedIds,
    selectableIds,
    allVisibleSelected,
    toggleOne,
    toggleAllVisible,
    clearSelection,
    selectedCount: selectedIds.size,
  };
}
