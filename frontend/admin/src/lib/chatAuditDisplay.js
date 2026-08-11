const EVENT_LABELS = {
  chat_recommendation_completed: { label: "Answered", tone: "success" },
  chat_missing_fields: { label: "Missing data", tone: "warning" },
  chat_value_conflict: { label: "Conflict", tone: "danger" },
};

export function eventMeta(eventType) {
  return EVENT_LABELS[eventType] || { label: eventType, tone: "neutral" };
}

export function extractQuestion(payload = {}) {
  const question = payload.user_question || payload.message;
  if (!question || question === "[REDACTED]") return "—";
  return question;
}

export function extractAnswer(payload = {}) {
  const answer = payload.assistant?.answer;
  if (!answer) return "";
  return answer;
}

export function extractPatientSnapshot(patient = {}) {
  if (!patient || typeof patient !== "object") return [];

  const vitals = patient.vitals || {};
  const labs = patient.labs || {};
  const hf = patient.heart_failure_profile || {};
  const echo = patient.echocardiography || {};

  const lvef = echo.lvef ?? hf.lvef ?? patient.lvef;
  const egfr = labs.egfr ?? patient.egfr;
  const potassium = labs.potassium ?? patient.potassium;
  const systolicBp = vitals.systolic_bp ?? patient.systolic_bp;
  const heartRate = vitals.heart_rate ?? patient.heart_rate;

  const chips = [];
  if (lvef != null) chips.push({ key: "LVEF", value: `${lvef}%` });
  if (egfr != null) chips.push({ key: "eGFR", value: `${egfr}` });
  if (potassium != null) chips.push({ key: "K+", value: `${potassium}` });
  if (systolicBp != null) chips.push({ key: "SBP", value: `${systolicBp} mmHg` });
  if (heartRate != null) chips.push({ key: "HR", value: `${heartRate} bpm` });

  const meds = (patient.medications || patient.current_medications || [])
    .map((item) => (typeof item === "string" ? item : item?.name || item?.drug_name))
    .filter(Boolean);
  if (meds.length) {
    chips.push({ key: "Meds", value: meds.slice(0, 4).join(", ") + (meds.length > 4 ? "…" : "") });
  }

  const hfType = hf.hf_type || hf.type || patient.hf_type;
  if (hfType) chips.push({ key: "HF", value: hfType });

  return chips;
}

export function formatTimestamp(iso) {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function truncate(text, max = 160) {
  if (!text) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, max).trim()}…`;
}
