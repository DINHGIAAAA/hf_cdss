/** Intents that trigger structured dose plan display in chat and clinical panel. */
export const DOSE_PLAN_INTENTS = new Set(["dose_adjustment"]);

export function shouldShowDosePlans(clinicalState) {
  const intent = clinicalState?.intent || "recommendation";
  return DOSE_PLAN_INTENTS.has(intent);
}

export function shouldShowStructuredRecommendation(clinicalState, recommendation) {
  if (!recommendation?.recommendations?.length) return false;
  return !shouldShowDosePlans(clinicalState);
}
