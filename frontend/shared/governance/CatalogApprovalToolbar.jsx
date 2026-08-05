import { useEffect } from "react";

import { ApprovalToolbar } from "./ApprovalToolbar.jsx";
import { useCatalogFilterOptions } from "./useCatalogFilterOptions.js";

function labelForValue(field, value) {
  if (field.optionLabels?.[value]) return field.optionLabels[value];
  if (field.formatOption) return field.formatOption(value);
  return value;
}

export function buildSelectOptions(field, filterOptions) {
  if (field.type !== "select") return null;
  if (field.options?.length) return field.options;
  if (!field.dynamic) return [{ value: "", label: field.emptyLabel || "All" }];
  const values = filterOptions?.[field.key] || [];
  const empty = { value: "", label: field.emptyLabel || "All" };
  return [
    empty,
    ...values.map((value) => ({
      value,
      label: labelForValue(field, value),
    })),
  ];
}

export function CatalogApprovalToolbar({
  catalog,
  tab,
  filters,
  setFilters,
  fetchFilterOptions,
  ...rest
}) {
  const { options, loading } = useCatalogFilterOptions(fetchFilterOptions, catalog.id, tab, filters);

  useEffect(() => {
    const dynamicKeys = catalog.filters.filter((field) => field.dynamic).map((field) => field.key);
    if (!dynamicKeys.length) return;
    setFilters((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const key of dynamicKeys) {
        const values = options[key];
        if (!prev[key] || !values?.length) continue;
        if (!values.includes(prev[key])) {
          next[key] = "";
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [options, catalog.filters, setFilters]);

  const catalogWithOptions = {
    ...catalog,
    filters: catalog.filters.map((field) => {
      if (field.type !== "select") return field;
      const built = buildSelectOptions(field, options);
      if (!built) return field;
      return { ...field, options: built };
    }),
  };

  return (
    <ApprovalToolbar
      catalog={catalogWithOptions}
      filterOptionsLoading={loading}
      filters={filters}
      onFilterChange={(key, value) => setFilters((prev) => ({ ...prev, [key]: value }))}
      {...rest}
    />
  );
}
