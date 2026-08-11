/** Maps SSE step ids to grouped pipeline phases for the chat loading UI. */

export const CLINICAL_STREAM_PHASES = [
  {
    id: "intake",
    labelKey: "chat.streamPhases.intake",
    steps: ["preparing", "received", "planning_question", "using_supplied_profile", "extracting_patient", "draft_ready", "missing_check"],
  },
  {
    id: "recommendation",
    labelKey: "chat.streamPhases.recommendation",
    steps: ["building_recommendation", "recommendation_ready"],
  },
  {
    id: "evidence",
    labelKey: "chat.streamPhases.evidence",
    steps: ["verifying_evidence", "verification_ready"],
  },
  {
    id: "reasoning",
    labelKey: "chat.streamPhases.reasoning",
    steps: ["loading_model", "generating_answer"],
  },
];

const STEP_ORDER = CLINICAL_STREAM_PHASES.flatMap((phase) => phase.steps);

export { STEP_ORDER };

export function resolveStreamPhaseState(activeStep) {
  if (!activeStep) {
    return CLINICAL_STREAM_PHASES.map((phase) => ({ ...phase, status: "pending" }));
  }

  const activeIndex = STEP_ORDER.indexOf(activeStep);
  if (activeIndex === -1) {
    return CLINICAL_STREAM_PHASES.map((phase) => ({ ...phase, status: "pending" }));
  }

  return CLINICAL_STREAM_PHASES.map((phase) => {
    const indices = phase.steps.map((step) => STEP_ORDER.indexOf(step)).filter((i) => i >= 0);
    const phaseStart = Math.min(...indices);
    const phaseEnd = Math.max(...indices);

    let status = "pending";
    if (activeIndex >= phaseEnd) status = "done";
    else if (activeIndex >= phaseStart) status = "active";

    return { ...phase, status };
  });
}
