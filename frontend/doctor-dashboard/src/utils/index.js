// ─── Text / number helpers ──────────────────────────────────────────────────

export function toNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number.parseFloat(String(value).replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

export function splitList(value) {
  return String(value || "")
    .split(/,|;|\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function slugify(value) {
  return String(value || "patient")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 32) || "patient";
}

export function titleCase(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function readable(value) {
  if (value === null || value === undefined || value === "") return "missing";
  return String(value);
}

export function sourceLink(chunk) {
  return chunk.source_link || chunk.source_url || chunk.metadata?.source_locator || chunk.metadata?.source_url || "";
}

export function statusClass(status) {
  if (["avoid", "blocked", "fail", "high", "missing"].includes(status)) return "danger";
  if (["warning", "consider_with_caution", "moderate", "weak"].includes(status)) return "warning";
  return "success";
}

// ─── Patient builders ────────────────────────────────────────────────────────

export function clinicalValue(value, unit) {
  const parsed = toNumber(value);
  return parsed === null ? null : { value: parsed, unit };
}

export function makePatientId(fullName) {
  return `${slugify(fullName)}_${Date.now().toString(36).slice(-6)}`;
}

export function buildPatient(patientForm, patientId) {
  const caseId = patientId || makePatientId(patientForm.fullName);
  return {
    patient_identity: {
      case_id: caseId,
      patient_id: caseId,
      full_name: patientForm.fullName || null,
      preferred_name: patientForm.fullName || null,
    },
    demographics: {
      age: toNumber(patientForm.age),
      sex: patientForm.sex || null,
    },
    heart_failure_profile: {
      lvef: clinicalValue(patientForm.lvef, "%"),
      nyha_class: patientForm.nyhaClass || null,
    },
    labs: {
      egfr: clinicalValue(patientForm.egfr, "mL/min/1.73m2"),
      potassium: clinicalValue(patientForm.potassium, "mmol/L"),
    },
    vitals: {
      systolic_bp: clinicalValue(patientForm.systolicBp, "mmHg"),
      heart_rate: clinicalValue(patientForm.heartRate, "bpm"),
      weight_kg: clinicalValue(patientForm.weightKg, "kg"),
    },
    conditions: splitList(patientForm.conditions).map((name) => ({ name, status: "active" })),
    medications: splitList(patientForm.medications).map((name) => ({ name, status: "active" })),
    allergy_statements: splitList(patientForm.allergies).map((substance) => ({ substance, status: "active" })),
    red_flags: splitList(patientForm.redFlags).map((name) => ({
      name,
      status: /stable|no acute|khong|none/i.test(name) ? "absent" : "present",
    })),
    care_context: {
      clinician_question: "",
      decision_context: "chat conversation patient intake",
    },
  };
}

export function patientSummary(patient) {
  if (!patient) return null;
  return {
    name: patient.patient_identity?.full_name || patient.patient_identity?.preferred_name || "Unnamed patient",
    id: patient.patient_identity?.case_id,
    age: patient.demographics?.age,
    sex: patient.demographics?.sex,
    weightKg: patient.vitals?.weight_kg?.value,
    lvef: patient.heart_failure_profile?.lvef?.value,
    egfr: patient.labs?.egfr?.value,
    potassium: patient.labs?.potassium?.value,
    systolicBp: patient.vitals?.systolic_bp?.value,
    heartRate: patient.vitals?.heart_rate?.value,
    conditions: patient.conditions?.map((item) => item.normalized_name || item.name).filter(Boolean) || [],
    medications: patient.medications?.map((item) => item.normalized_name || item.name).filter(Boolean) || [],
    documents: patient.clinical_documents || [],
  };
}

// ─── SSE parser ──────────────────────────────────────────────────────────────

export function parseSseBlock(block) {
  const lines = block.split(/\r?\n/);
  const eventName = lines.find((line) => line.startsWith("event:"))?.slice(6).trim() || "message";
  const data = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .join("\n");
  if (!data) return { eventName, data: null };
  try {
    return { eventName, data: JSON.parse(data) };
  } catch {
    return { eventName, data };
  }
}

// ─── File reader ─────────────────────────────────────────────────────────────

export async function readClinicalFiles(fileList) {
  const files = Array.from(fileList || []);
  const textLike = /text|json|csv|xml|markdown|html/i;
  return Promise.all(
    files.map(
      (file) =>
        new Promise((resolve) => {
          const isText = textLike.test(file.type) || /\.(txt|csv|json|md|xml|html)$/i.test(file.name);
          if (!isText) {
            resolve({
              file_name: file.name,
              mime_type: file.type || "application/octet-stream",
              note: "Metadata only. OCR/vision parsing is not enabled for this file type yet.",
            });
            return;
          }
          const reader = new FileReader();
          reader.onload = () =>
            resolve({
              file_name: file.name,
              mime_type: file.type || "text/plain",
              extracted_text: String(reader.result || "").slice(0, 12000),
            });
          reader.onerror = () =>
            resolve({
              file_name: file.name,
              mime_type: file.type || "text/plain",
              note: "Could not read file content in the browser.",
            });
          reader.readAsText(file);
        }),
    ),
  );
}
