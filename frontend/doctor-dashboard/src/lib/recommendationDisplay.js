const VITAL_PATTERN =
  /(?:LVEF\s*[\d.]+\s*%|eGFR\s*[\d.]+|K\+\s*[\d.]+\s*mmol\/L|SBP\s*[\d.]+\s*mmHg|HR\s*[\d.]+\s*bpm)/gi;

const PATIENT_CONTEXT_TAIL = /,?\s*(?:but\s+)?this patient context is\b[\s\S]*$/i;

function normalizeVital(token) {
  return token.replace(/\s+/g, " ").trim();
}

export function extractVitalChips(...texts) {
  const chips = new Set();
  for (const text of texts) {
    if (!text) continue;
    const matches = String(text).match(VITAL_PATTERN) || [];
    for (const match of matches) {
      chips.add(normalizeVital(match));
    }
  }
  return [...chips];
}

/** Shared vitals across all recommendation items in one response (dedupe once per conversation turn). */
export function collectSharedVitalChips(recommendations = []) {
  return extractVitalChips(
    ...recommendations.flatMap((item) => [item.rationale, ...(item.clinical_reasoning || [])]),
  );
}

export function stripPatientContext(text) {
  return String(text || "")
    .replace(PATIENT_CONTEXT_TAIL, "")
    .replace(/\s+/g, " ")
    .replace(/[,\s]+$/g, "")
    .trim();
}

export function isPatientContextLine(line) {
  const trimmed = String(line || "").trim();
  if (!trimmed) return true;
  if (/^this patient context is\b/i.test(trimmed)) return true;
  if (/\bpatient context is\b/i.test(trimmed) && extractVitalChips(trimmed).length >= 2) {
    return true;
  }
  const vitals = extractVitalChips(trimmed);
  if (vitals.length < 3) return false;
  const remainder = trimmed
    .replace(VITAL_PATTERN, "")
    .replace(/patient context is/gi, "")
    .replace(/[,:;.\-–—/\s]+/g, "");
  return remainder.length < 24;
}

export function recommendationReasoning(item) {
  if (item.clinical_reasoning?.length) {
    return item.clinical_reasoning.map((line) => line.trim()).filter(Boolean);
  }
  return (item.rationale || "")
    .split(/\.\s+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 8);
}

export function recommendationLead(item) {
  for (const line of recommendationReasoning(item)) {
    const cleaned = stripPatientContext(line);
    if (cleaned && !isPatientContextLine(cleaned) && !isPatientContextLine(line)) {
      return cleaned;
    }
  }
  return "";
}

export function recommendationDetailLines(item, sharedVitals = []) {
  const lines = recommendationReasoning(item);
  const lead = recommendationLead(item);
  const vitalBlob = sharedVitals.join(" ").toLowerCase();

  return lines
    .map((line) => stripPatientContext(line))
    .filter((trimmed, index) => {
      if (!trimmed) return false;
      if (isPatientContextLine(trimmed)) return false;
      if (index === 0 && trimmed === lead) return false;
      if (lead && trimmed === lead) return false;

      const lineVitals = extractVitalChips(trimmed);
      if (
        lineVitals.length >= 3 &&
        vitalBlob &&
        lineVitals.join(" ").toLowerCase().length >= vitalBlob.length * 0.8
      ) {
        return false;
      }

      return true;
    });
}
