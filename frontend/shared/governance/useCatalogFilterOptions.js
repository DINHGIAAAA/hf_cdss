import { useEffect, useMemo, useState } from "react";

import { buildGovernanceQuery } from "./catalogConfig.js";

const DEBOUNCE_MS = 250;

/**
 * Load distinct filter values from Postgres for a governance catalog.
 * Cross-field: other selected filters narrow each dropdown (faceted).
 */
export function useCatalogFilterOptions(fetchOptions, catalogId, tab, filters) {
  const [options, setOptions] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const queryParams = useMemo(() => {
    const status = tab && tab !== "all" ? tab : undefined;
    const params = { catalog: catalogId, status, ...filters };
    Object.keys(params).forEach((key) => {
      if (params[key] === "" || params[key] == null) delete params[key];
    });
    return params;
  }, [catalogId, tab, filters]);

  const queryKey = useMemo(() => JSON.stringify(queryParams), [queryParams]);

  useEffect(() => {
    if (!fetchOptions || !catalogId) return undefined;
    let cancelled = false;
    const timer = setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const result = await fetchOptions(queryParams);
        if (!cancelled) {
          setOptions(result?.fields || {});
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "Failed to load filter options");
          setOptions({});
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [fetchOptions, catalogId, queryKey]);

  return { options, loading, error };
}

export function buildCatalogFilterOptionsUrl(params) {
  return `/admin/governance/filter-options${buildGovernanceQuery(params)}`;
}
