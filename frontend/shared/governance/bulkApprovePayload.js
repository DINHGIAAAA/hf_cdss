/** Build POST body for governance bulk-approve endpoints. */

export function buildBulkApprovePayload(appliedFilters = {}, { ruleIds, matchAll } = {}) {
  const payload = Object.fromEntries(
    Object.entries(appliedFilters).filter(([, value]) => value !== undefined && value !== null && value !== ""),
  );

  if (payload.needs_condition === "true") {
    payload.needs_condition = true;
  } else if (payload.needs_condition === "false") {
    payload.needs_condition = false;
  } else {
    delete payload.needs_condition;
  }

  if (matchAll) {
    payload.match_all = true;
  } else if (ruleIds?.length) {
    payload.rule_ids = [...ruleIds];
  }

  return payload;
}
