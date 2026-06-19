export function compactPatientForRequest(active) {
  const draftPatient = active.draft?.patient;
  const intakePatient = active.patient;
  if (!draftPatient) return intakePatient;
  if (!intakePatient) return draftPatient;

  return {
    ...draftPatient,
    patient_identity: { ...intakePatient.patient_identity, ...draftPatient.patient_identity },
    demographics: { ...intakePatient.demographics, ...draftPatient.demographics },
    heart_failure_profile: { ...intakePatient.heart_failure_profile, ...draftPatient.heart_failure_profile },
    labs: { ...intakePatient.labs, ...draftPatient.labs },
    vitals: { ...intakePatient.vitals, ...draftPatient.vitals },
    care_context: { ...intakePatient.care_context, ...draftPatient.care_context },
    conditions: draftPatient.conditions?.length ? draftPatient.conditions : intakePatient.conditions,
    medications: draftPatient.medications?.length ? draftPatient.medications : intakePatient.medications,
    allergy_statements: draftPatient.allergy_statements?.length
      ? draftPatient.allergy_statements
      : intakePatient.allergy_statements,
    red_flags: draftPatient.red_flags?.length ? draftPatient.red_flags : intakePatient.red_flags,
  };
}

export function mapBackendMessages(messages) {
  return (messages || []).map((message) => ({
    id: message.message_id,
    role: message.role,
    content: message.content,
  }));
}
