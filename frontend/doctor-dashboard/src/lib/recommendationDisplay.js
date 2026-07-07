const VITAL_PATTERN =
  /(?:LVEF\s*[\d.]+\s*%|eGFR\s*[\d.]+|K\+\s*[\d.]+\s*mmol\/L|SBP\s*[\d.]+\s*mmHg|HR\s*[\d.]+\s*bpm)/gi;

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
  const [first] = recommendationReasoning(item);
  const source = first || item.rationale || "";
  return source
    .replace(/,?\s*but this patient context is.*$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function recommendationDetailLines(item, vitals = []) {
  const lines = recommendationReasoning(item);
  const lead = recommendationLead(item);
  const vitalBlob = vitals.join(" ").toLowerCase();

  return lines.filter((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return false;

    const withoutContext = trimmed
      .replace(/,?\s*but this patient context is.*$/i, "")
      .replace(/\.$/, "")
      .trim();

    if (index === 0 && withoutContext === lead) return false;
    if (/^this patient context is/i.test(trimmed)) return false;

    const lineVitals = extractVitalChips(trimmed);
    if (lineVitals.length >= 3 && vitalBlob && lineVitals.join(" ").length >= vitalBlob.length * 0.8) {
      return false;
    }

    return true;
  });
}
