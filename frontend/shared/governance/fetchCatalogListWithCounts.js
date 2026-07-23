/**
 * Load a governance catalog page.
 * Items follow the status tab; badge counts always come from a parallel
 * request without status filter so top cards stay correct across tabs.
 */
export async function fetchCatalogListWithCounts(listFn, { tab, filters = {} } = {}) {
  const status = tab && tab !== "all" ? tab : undefined;

  async function run() {
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

  try {
    return await run();
  } catch (err) {
    // One retry: concurrent chat/stream work on a single API worker can briefly fail lists.
    await new Promise((resolve) => setTimeout(resolve, 500));
    return await run();
  }
}
