import { useCallback } from "react";

import { buildBulkApprovePayload } from "./bulkApprovePayload.js";

export function useCatalogBulkApprove({
  catalog,
  adminApi,
  appliedFilters,
  selectedIds,
  clearSelection,
  loadRules,
  setToast,
  setBulkLoading,
}) {
  const bulkFn = adminApi[catalog.bulkKey];

  const handleBulkApprove = useCallback(async () => {
    setBulkLoading(true);
    setToast("");
    try {
      const payload = buildBulkApprovePayload(appliedFilters, {
        ruleIds: [...selectedIds],
      });
      const result = await bulkFn(payload);
      setToast(result.message);
      clearSelection();
      await loadRules();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBulkLoading(false);
    }
  }, [appliedFilters, bulkFn, clearSelection, loadRules, selectedIds, setBulkLoading, setToast]);

  const handleBulkApproveAll = useCallback(async () => {
    setBulkLoading(true);
    setToast("");
    try {
      const payload = buildBulkApprovePayload(appliedFilters, { matchAll: true });
      const result = await bulkFn(payload);
      setToast(result.message);
      clearSelection();
      await loadRules();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBulkLoading(false);
    }
  }, [appliedFilters, bulkFn, clearSelection, loadRules, setBulkLoading, setToast]);

  return { handleBulkApprove, handleBulkApproveAll };
}
