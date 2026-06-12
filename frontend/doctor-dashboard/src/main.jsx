import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ExternalLink,
  FileText,
  LoaderCircle,
  MessageSquareText,
  Send,
  ShieldAlert,
  Stethoscope,
  Upload,
  UserRound,
} from "lucide-react";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";
const API_KEY_HEADER = import.meta.env.VITE_API_KEY_HEADER ?? "x-api-key";

const EMPTY_INTAKE = {
  caseId: `CASE_${Date.now()}`,
  age: "",
  sex: "",
  weightKg: "",
  lvef: "",
  egfr: "",
  potassium: "",
  systolicBp: "",
  heartRate: "",
  nyhaClass: "",
  conditions: "",
  medications: "",
  allergies: "no known drug allergies",
  redFlags: "stable",
};

const EXAMPLES = [
  {
    label: "HFrEF + CKD",
    intake: {
      age: "68",
      sex: "male",
      weightKg: "72",
      lvef: "28",
      egfr: "48",
      potassium: "4.9",
      systolicBp: "88",
      heartRate: "54",
      conditions: "CKD, atrial fibrillation",
      medications: "metoprolol, furosemide, apixaban",
    },
    chat: "Benh nhan kho tho khi gang suc, dang uong cac thuoc tren. Co the toi uu GDMT nhu the nao?",
  },
  {
    label: "MRA safety",
    intake: {
      age: "71",
      sex: "female",
      weightKg: "61",
      lvef: "30",
      egfr: "24",
      potassium: "5.7",
      systolicBp: "104",
      heartRate: "70",
      conditions: "CKD, diabetes",
      medications: "furosemide, spironolactone, warfarin",
    },
    chat: "Dang dung spironolactone, co nen tiep tuc hay tang lieu khong?",
  },
];

function apiHeaders(extra = {}) {
  return API_KEY ? { ...extra, [API_KEY_HEADER]: API_KEY } : extra;
}

function toNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number.parseFloat(String(value).replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function splitList(value) {
  return String(value || "")
    .split(/,|;|\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function clinicalValue(value, unit) {
  const parsed = toNumber(value);
  return parsed === null ? null : { value: parsed, unit };
}

function buildPatient(intake) {
  const caseId = intake.caseId || `CASE_${Date.now()}`;
  return {
    patient_identity: { case_id: caseId },
    demographics: {
      age: toNumber(intake.age),
      sex: intake.sex || null,
    },
    heart_failure_profile: {
      lvef: clinicalValue(intake.lvef, "%"),
      nyha_class: intake.nyhaClass || null,
    },
    labs: {
      egfr: clinicalValue(intake.egfr, "mL/min/1.73m2"),
      potassium: clinicalValue(intake.potassium, "mmol/L"),
    },
    vitals: {
      systolic_bp: clinicalValue(intake.systolicBp, "mmHg"),
      heart_rate: clinicalValue(intake.heartRate, "bpm"),
      weight_kg: clinicalValue(intake.weightKg, "kg"),
    },
    conditions: splitList(intake.conditions).map((name) => ({ name, status: "active" })),
    medications: splitList(intake.medications).map((name) => ({ name, status: "active" })),
    allergy_statements: splitList(intake.allergies).map((substance) => ({ substance, status: "active" })),
    red_flags: splitList(intake.redFlags).map((name) => ({
      name,
      status: /stable|no acute|khong|none/i.test(name) ? "absent" : "present",
    })),
    care_context: {
      clinician_question: "",
      decision_context: "structured intake form",
    },
  };
}

function summarizePatient(profile) {
  if (!profile) return null;
  return {
    caseId: profile.patient_identity?.case_id,
    age: profile.demographics?.age,
    sex: profile.demographics?.sex,
    weightKg: profile.vitals?.weight_kg?.value,
    lvef: profile.heart_failure_profile?.lvef?.value,
    egfr: profile.labs?.egfr?.value,
    potassium: profile.labs?.potassium?.value,
    systolicBp: profile.vitals?.systolic_bp?.value,
    heartRate: profile.vitals?.heart_rate?.value,
    conditions: profile.conditions?.map((item) => item.normalized_name || item.name).filter(Boolean) || [],
    medications: profile.medications?.map((item) => item.normalized_name || item.name).filter(Boolean) || [],
    allergies: profile.allergy_statements?.map((item) => item.normalized_substance || item.substance).filter(Boolean) || [],
    documents: profile.clinical_documents || [],
  };
}

function statusClass(status) {
  if (["avoid", "blocked", "fail", "high", "missing"].includes(status)) return "danger";
  if (["warning", "consider_with_caution", "moderate", "weak"].includes(status)) return "warning";
  return "success";
}

function readable(value) {
  if (value === null || value === undefined || value === "") return "missing";
  return String(value);
}

function titleCase(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function sourceLink(chunk) {
  return chunk.source_link || chunk.source_url || chunk.metadata?.source_url || "";
}

function EvidenceCard({ chunk }) {
  const link = sourceLink(chunk);
  return (
    <article className="evidence-card">
      <div className="evidence-head">
        <div>
          <strong>{titleCase(chunk.document_id)}</strong>
          <span>{chunk.section || chunk.evidence_level || chunk.source_type}</span>
        </div>
        <span className="score">{Math.round((chunk.quality_score ?? chunk.score ?? 0) * 100)}%</span>
      </div>
      <p>{(chunk.text || "").replace(/\s+/g, " ").slice(0, 360)}</p>
      <div className="evidence-foot">
        {chunk.page && <span>Page {chunk.page}</span>}
        {chunk.metadata?.publisher && <span>{chunk.metadata.publisher}</span>}
        {link && (
          <a href={link} rel="noreferrer" target="_blank">
            Open source <ExternalLink size={14} />
          </a>
        )}
      </div>
    </article>
  );
}

function IntakeField({ label, name, value, onChange, type = "text", placeholder = "" }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input name={name} onChange={onChange} placeholder={placeholder} type={type} value={value} />
    </label>
  );
}

function TextAreaField({ label, name, value, onChange, placeholder = "" }) {
  return (
    <label className="field wide">
      <span>{label}</span>
      <textarea name={name} onChange={onChange} placeholder={placeholder} value={value} />
    </label>
  );
}

async function readClinicalFiles(fileList) {
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
              note: "Uploaded file metadata only. OCR/vision parsing is not enabled for this file type yet.",
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

function App() {
  const [health, setHealth] = useState("checking");
  const [intake, setIntake] = useState(EMPTY_INTAKE);
  const [attachments, setAttachments] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Nhap thong tin benh nhan, upload note/file lam sang neu co, sau do hoi ve tinh trang va thuoc dang dung.",
    },
  ]);
  const [draft, setDraft] = useState(null);
  const [recommendation, setRecommendation] = useState(null);
  const [verification, setVerification] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((response) => setHealth(response.ok ? "ok" : "degraded"))
      .catch(() => setHealth("down"));
  }, []);

  const summary = useMemo(() => summarizePatient(draft?.patient), [draft]);
  const missingFields = draft?.clinical_state?.key_values
    ? Object.entries(draft.clinical_state.key_values)
        .filter(([, value]) => value === null || value === undefined)
        .map(([key]) => key)
    : [];

  function updateIntake(event) {
    const { name, value } = event.target;
    setIntake((current) => ({ ...current, [name]: value }));
  }

  async function handleFiles(event) {
    const parsed = await readClinicalFiles(event.target.files);
    setAttachments((current) => [...current, ...parsed]);
    event.target.value = "";
  }

  function applyExample(example) {
    setIntake((current) => ({ ...current, ...example.intake, caseId: `CASE_${Date.now()}` }));
    setChatInput(example.chat);
  }

  async function submitChat(event) {
    event.preventDefault();
    const message = chatInput.trim();
    if (!message || loading) return;

    const patient = buildPatient(intake);
    setLoading(true);
    setError("");
    setMessages((current) => [...current, { role: "user", content: message }]);

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: apiHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
          patient,
          clinical_attachments: attachments,
          language: "vi",
        }),
      });
      if (!response.ok) {
        throw new Error(`Chat API returned ${response.status}`);
      }
      const data = await response.json();
      setConversationId(data.conversation_id);
      setDraft(data.patient_draft);
      setRecommendation(data.recommendation);
      setVerification(data.verification);
      setMessages((current) => [...current, { role: "assistant", content: data.assistant_message.content }]);
      setChatInput("");
    } catch (requestError) {
      setError(requestError.message);
      setMessages((current) => [...current, { role: "assistant", content: `API error: ${requestError.message}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Heart Failure CDSS</h1>
          <p>Structured intake, clinical document parsing, and evidence-grounded chat.</p>
        </div>
        <div className={`api-status ${health}`}>
          {health === "ok" ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
          <span>API {health}</span>
        </div>
      </header>

      <section className="workspace">
        <aside className="intake-panel">
          <div className="panel-title">
            <Stethoscope size={20} />
            <h2>Patient Intake</h2>
          </div>

          <div className="example-row">
            {EXAMPLES.map((example) => (
              <button key={example.label} onClick={() => applyExample(example)} type="button">
                {example.label}
              </button>
            ))}
          </div>

          <form className="intake-grid">
            <IntakeField label="Case ID" name="caseId" onChange={updateIntake} value={intake.caseId} />
            <IntakeField label="Age" name="age" onChange={updateIntake} type="number" value={intake.age} />
            <label className="field">
              <span>Sex</span>
              <select name="sex" onChange={updateIntake} value={intake.sex}>
                <option value="">Unknown</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
            </label>
            <IntakeField label="Weight kg" name="weightKg" onChange={updateIntake} type="number" value={intake.weightKg} />
            <IntakeField label="LVEF %" name="lvef" onChange={updateIntake} type="number" value={intake.lvef} />
            <IntakeField label="eGFR" name="egfr" onChange={updateIntake} type="number" value={intake.egfr} />
            <IntakeField label="K+ mmol/L" name="potassium" onChange={updateIntake} type="number" value={intake.potassium} />
            <IntakeField label="SBP mmHg" name="systolicBp" onChange={updateIntake} type="number" value={intake.systolicBp} />
            <IntakeField label="Heart rate" name="heartRate" onChange={updateIntake} type="number" value={intake.heartRate} />
            <IntakeField label="NYHA" name="nyhaClass" onChange={updateIntake} placeholder="II, III..." value={intake.nyhaClass} />
            <TextAreaField label="Conditions" name="conditions" onChange={updateIntake} placeholder="CKD, diabetes..." value={intake.conditions} />
            <TextAreaField label="Current medications" name="medications" onChange={updateIntake} placeholder="metoprolol, furosemide..." value={intake.medications} />
            <TextAreaField label="Allergies" name="allergies" onChange={updateIntake} value={intake.allergies} />
            <TextAreaField label="Red flags" name="redFlags" onChange={updateIntake} value={intake.redFlags} />
          </form>

          <label className="upload-zone">
            <Upload size={20} />
            <div>
              <strong>Upload clinical image or file</strong>
              <span>Text/CSV/JSON/XML are parsed in browser; images are attached as metadata for now.</span>
            </div>
            <input accept=".txt,.csv,.json,.md,.xml,.html,image/*,.pdf" multiple onChange={handleFiles} type="file" />
          </label>

          {attachments.length > 0 && (
            <div className="attachment-list">
              {attachments.map((file) => (
                <article key={`${file.file_name}-${file.mime_type}`}>
                  <FileText size={16} />
                  <div>
                    <strong>{file.file_name}</strong>
                    <span>{file.extracted_text ? `${file.extracted_text.length} chars extracted` : file.note}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </aside>

        <section className="chat-panel">
          <div className="panel-title">
            <MessageSquareText size={20} />
            <h2>Clinical Chat</h2>
          </div>

          <div className="message-list">
            {messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="avatar">{message.role === "assistant" ? <Bot size={16} /> : <UserRound size={16} />}</div>
                <p>{message.content}</p>
              </article>
            ))}
            {loading && (
              <article className="message assistant">
                <div className="avatar"><LoaderCircle className="spin" size={16} /></div>
                <p>Dang parse draft, kiem tra safety, retrieve evidence va validate citation...</p>
              </article>
            )}
          </div>

          <form className="composer" onSubmit={submitChat}>
            <textarea
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Benh nhan bi gi, dang uong thuoc gi, va cau hoi lam sang cua bac si..."
              value={chatInput}
            />
            <button disabled={loading || !chatInput.trim()} title="Send clinical question" type="submit">
              <Send size={18} />
            </button>
          </form>
        </section>

        <aside className="result-panel">
          <div className="panel-title">
            <Activity size={20} />
            <h2>Draft & Evidence</h2>
          </div>

          {error && <p className="error-text">{error}</p>}

          {!summary && !error && (
            <p className="empty-state">Nhap intake va chat de tao patient draft. Ket qua se hien o day khi backend parse xong.</p>
          )}

          {summary && (
            <section className="summary-section">
              <h3>Patient Draft</h3>
              <div className="fact-grid">
                <span>Age <strong>{readable(summary.age)}</strong></span>
                <span>Sex <strong>{readable(summary.sex)}</strong></span>
                <span>Weight <strong>{readable(summary.weightKg)}</strong></span>
                <span>LVEF <strong>{readable(summary.lvef)}</strong></span>
                <span>eGFR <strong>{readable(summary.egfr)}</strong></span>
                <span>K+ <strong>{readable(summary.potassium)}</strong></span>
                <span>SBP <strong>{readable(summary.systolicBp)}</strong></span>
                <span>HR <strong>{readable(summary.heartRate)}</strong></span>
              </div>
              <p><strong>Conditions:</strong> {summary.conditions.join(", ") || "none detected"}</p>
              <p><strong>Meds:</strong> {summary.medications.join(", ") || "none detected"}</p>
              <p><strong>Allergies:</strong> {summary.allergies.join(", ") || "none detected"}</p>
              {draft?.clinical_state && (
                <div className="state-strip">
                  <span>{draft.clinical_state.hf_type || "HF type unknown"}</span>
                  <span>{draft.clinical_state.intent}</span>
                  <span>{(draft.clinical_state.focus_medication_classes || []).join(", ") || "no focus drug"}</span>
                </div>
              )}
              {missingFields.length > 0 && (
                <div className="missing-box">
                  <AlertTriangle size={16} />
                  <span>Missing: {missingFields.join(", ")}</span>
                </div>
              )}
            </section>
          )}

          {recommendation && (
            <section className="summary-section">
              <h3>Recommendation</h3>
              <div className={`decision ${statusClass(recommendation.overall_status)}`}>
                <ShieldAlert size={18} />
                <strong>{titleCase(recommendation.overall_status)}</strong>
              </div>
              <div className="recommendation-list">
                {recommendation.recommendations.map((item) => (
                  <article key={item.drug_class}>
                    <div>
                      <strong>{item.drug_class}</strong>
                      <span className={statusClass(item.status)}>{titleCase(item.status)}</span>
                    </div>
                    <p>{item.rationale}</p>
                  </article>
                ))}
              </div>
            </section>
          )}

          {verification?.citation_validation && (
            <section className="summary-section">
              <h3>Citation Validation</h3>
              <div className={`decision ${statusClass(verification.citation_validation.status)}`}>
                <strong>{verification.citation_validation.status}</strong>
              </div>
              <div className="citation-list">
                {verification.citation_validation.supports.slice(0, 5).map((item) => (
                  <article key={`${item.target_type}-${item.target_id}`}>
                    <strong>{item.target_id}</strong>
                    <span>{item.evidence_verdict || item.evidence_status}</span>
                    <small>confidence {Math.round((item.confidence || 0) * 100)}%</small>
                  </article>
                ))}
              </div>
            </section>
          )}

          {verification?.context?.evidence_chunks?.length > 0 && (
            <section className="summary-section">
              <h3>Evidence</h3>
              <div className="evidence-list">
                {verification.context.evidence_chunks.slice(0, 4).map((chunk) => (
                  <EvidenceCard chunk={chunk} key={chunk.chunk_id} />
                ))}
              </div>
            </section>
          )}
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
