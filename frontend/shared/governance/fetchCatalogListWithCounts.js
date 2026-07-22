/**
 * Load a governance catalog page.
 * Items follow the status tab; badge counts always come from a parallel
 * request without status filter so top cards stay correct across tabs.
 */
export async function fetchCatalogListWithCounts(listFn, { tab, filters = {} } = {}) {
  const status = tab && tab !== "all" ? tab : undefined;
  const [listResult, countResult] = await Promise.all([
    listFn({ status, ...filters }),
    // No status filter — must NOT use a tiny limit; counts are SQL aggregates
    // but older backends derived counts from returned rows.
    listFn({ ...filters }),
  ]);
  return {
    ...listResult,
    draft_count: Number(countResult.draft_count ?? 0),
    approved_count: Number(countResult.approved_count ?? 0),
    retired_count: Number(countResult.retired_count ?? 0),
  };
}
