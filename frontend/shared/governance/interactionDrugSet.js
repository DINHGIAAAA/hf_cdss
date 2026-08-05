/** Heuristics for interaction drug_set_a / drug_set_b display. */

const PROSE_MARKERS = [
  "may_",
  "might_",
  "increase_",
  "decrease_",
  "risk_of_",
  "leading_to_",
  "associated_with_",
  "should_",
  "patients_",
  "hypokalem",
  "hyperkalem",
  "administration_",
  "concomitant_",
];

export function isSuspiciousDrugSetToken(token) {
  const text = String(token || "").trim().toLowerCase();
  if (!text) return true;
  if (text.startsWith("class:")) return text.length < 8;
  if (text.length > 36 || (text.match(/_/g) || []).length > 4) return true;
  return PROSE_MARKERS.some((marker) => text.includes(marker));
}

export function drugSetNeedsReview(tokens = []) {
  return (Array.isArray(tokens) ? tokens : []).some((token) => isSuspiciousDrugSetToken(token));
}
