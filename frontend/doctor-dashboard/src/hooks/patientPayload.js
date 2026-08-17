export function compactPatientForRequest(active) {
  const draftPatient = active.draft?.patient;
  const intakePatient = active.patient;
  // If there's a pending confirmation (unconfirmed value changes), use it as the base
  // This ensures confirmation requests include the new values, not the old ones
  const pendingPatient = active.pending_confirmation || active.pendingConfirmation;
  const effectiveDraft = pendingPatient || draftPatient;

  if (!effectiveDraft) return intakePatient;
  if (!intakePatient) return effectiveDraft;

  return {
    ...effectiveDraft,
    patient_identity: { ...intakePatient.patient_identity, ...effectiveDraft.patient_identity },
    demographics: { ...intakePatient.demographics, ...effectiveDraft.demographics },
    heart_failure_profile: { ...intakePatient.heart_failure_profile, ...effectiveDraft.heart_failure_profile },
    labs: { ...intakePatient.labs, ...effectiveDraft.labs },
    vitals: { ...intakePatient.vitals, ...effectiveDraft.vitals },
    care_context: { ...intakePatient.care_context, ...effectiveDraft.care_context },
    conditions: effectiveDraft.conditions?.length ? effectiveDraft.conditions : intakePatient.conditions,
    medications: effectiveDraft.medications?.length ? effectiveDraft.medications : intakePatient.medications,
    allergy_statements: effectiveDraft.allergy_statements?.length
      ? effectiveDraft.allergy_statements
      : intakePatient.allergy_statements,
    red_flags: effectiveDraft.red_flags?.length ? effectiveDraft.red_flags : intakePatient.red_flags,
  };
}

export function mapBackendMessages(messages) {
  return (messages || []).map((message) => ({
    id: message.message_id,
    role: message.role,
    content: message.content,
  }));
}
