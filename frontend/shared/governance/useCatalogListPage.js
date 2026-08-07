import { useEffect, useState } from "react";

import { CATALOG_PAGE_SIZE } from "./catalogPagination.js";

/** Resets to page 1 when tab or applied filters change. */
export function useCatalogListPage(tab, appliedFilters) {
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [tab, appliedFilters]);

  return { page, setPage, pageSize: CATALOG_PAGE_SIZE };
}
