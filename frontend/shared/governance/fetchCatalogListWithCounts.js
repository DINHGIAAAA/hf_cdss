import { CATALOG_PAGE_SIZE } from "./catalogPagination.js";

/**
 * Load a governance catalog page.
 * Items follow the status tab; badge counts always come from a parallel
 * request without status filter so top cards stay correct across tabs.
 */
export async function fetchCatalogListWithCounts(
  listFn,
  { tab, filters = {}, page = 1, pageSize = CATALOG_PAGE_SIZE } = {},
) {
  const status = tab && tab !== "all" ? tab : undefined;
  const offset = (page - 1) * pageSize;

  async function run() {
    const [listResult, countResult] = await Promise.all([
      listFn({ status, ...filters, limit: pageSize, offset }),
      listFn({ ...filters, limit: 1, offset: 0 }),
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
