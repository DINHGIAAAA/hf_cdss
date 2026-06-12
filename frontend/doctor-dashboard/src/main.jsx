import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ExternalLink,
  FileText,
  LoaderCircle,
  MessageSquareText,
  Plus,
  Send,
  ShieldAlert,
  Upload,
  UserRound,
} from "lucide-react";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";
const API_KEY_HEADER = import.meta.env.VITE_API_KEY_HEADER ?? "x-api-key";
const STORAGE_KEY = "hf_cdss_conversations_v2";

const EMPTY_PATIENT = {
  fullName: "",
  age: "",
  sex: "",
  weightKg: "",
  systolicBp: "",
  heartRate: "",
  lvef: "",
  egfr: "",
  potassium: "",
  nyhaClass: "",
  conditions: "",
  medications: "",
  allergies: "no known drug allergies",
  redFlags: "stable",
};

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

function slugify(value) {
  return String(value || "patient")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 32) || "patient";
}

function makePatientId(fullName) {
  return `${slugify(fullName)}_${Date.now().toString(36).slice(-6)}`;
}

function buildPatient(patientForm, patientId) {
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

function patientSummary(patient) {
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
  return chunk.source_link || chunk.source_url || chunk.metadata?.source_locator || chunk.metadata?.source_url || "";
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

function Field({ label, name, value, onChange, type = "text", placeholder = "" }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input name={name} onChange={onChange} placeholder={placeholder} type={type} value={value} />
    </label>
  );
}

function TextField({ label, name, value, onChange, placeholder = "" }) {
  return (
    <label className="field wide">
      <span>{label}</span>
      <textarea name={name} onChange={onChange} placeholder={placeholder} value={value} />
    </label>
  );
}

function PatientModal({ onCreate }) {
  const [form, setForm] = useState(EMPTY_PATIENT);
  const patientId = useMemo(() => makePatientId(form.fullName), [form.fullName]);
  const conversationName = `${slugify(form.fullName)}_${patientId.split("_").at(-1)}`;

  function update(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  function submit(event) {
    event.preventDefault();
    if (!form.fullName.trim()) return;
    onCreate(form, patientId, conversationName);
  }

  return (
    <div className="modal-backdrop">
      <form className="patient-modal" onSubmit={submit}>
        <div className="modal-head">
          <div>
            <h1>New Conversation</h1>
            <p>{conversationName}</p>
          </div>
          <UserRound size={22} />
        </div>
        <div className="modal-grid">
          <Field label="Patient name" name="fullName" onChange={update} placeholder="Nguyen Van A" value={form.fullName} />
          <Field label="Age" name="age" onChange={update} type="number" value={form.age} />
          <label className="field">
            <span>Sex</span>
            <select name="sex" onChange={update} value={form.sex}>
              <option value="">Unknown</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
          </label>
          <Field label="Weight kg" name="weightKg" onChange={update} type="number" value={form.weightKg} />
          <Field label="SBP mmHg" name="systolicBp" onChange={update} type="number" value={form.systolicBp} />
          <Field label="Heart rate" name="heartRate" onChange={update} type="number" value={form.heartRate} />
          <Field label="LVEF %" name="lvef" onChange={update} type="number" value={form.lvef} />
          <Field label="eGFR" name="egfr" onChange={update} type="number" value={form.egfr} />
          <Field label="K+ mmol/L" name="potassium" onChange={update} type="number" value={form.potassium} />
          <Field label="NYHA" name="nyhaClass" onChange={update} placeholder="II, III..." value={form.nyhaClass} />
          <TextField label="Conditions" name="conditions" onChange={update} placeholder="HFrEF, CKD..." value={form.conditions} />
          <TextField label="Current medications" name="medications" onChange={update} placeholder="metoprolol, furosemide..." value={form.medications} />
        </div>
        <button className="primary-action" disabled={!form.fullName.trim()} type="submit">
          Start conversation
        </button>
      </form>
    </div>
  );
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
      <p>{(chunk.text || "").replace(/\s+/g, " ").slice(0, 280)}</p>
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

function RecommendationCard({ item }) {
  return (
    <article className="recommendation-card">
      <div className="recommendation-title">
        <strong>{item.drug_class}</strong>
        <span className={statusClass(item.status)}>{titleCase(item.status)}</span>
      </div>
      <p>{item.rationale}</p>
      {(item.action_items || []).length > 0 && (
        <div className="clinical-block">
          <b>Next clinical step</b>
          <ul>
            {item.action_items.slice(0, 2).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {(item.monitoring || []).length > 0 && (
        <div className="clinical-block">
          <b>Monitor</b>
          <ul>
            {item.monitoring.slice(0, 2).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

function App() {
  const [health, setHealth] = useState("checking");
  const [conversations, setConversations] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    } catch {
      return [];
    }
  });
  const [activeId, setActiveId] = useState(() => conversations[0]?.id || null);
  const [showModal, setShowModal] = useState(() => conversations.length === 0);
  const [chatInput, setChatInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const active = conversations.find((item) => item.id === activeId) || null;
  const summary = patientSummary(active?.draft?.patient || active?.patient);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  }, [conversations]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((response) => setHealth(response.ok ? "ok" : "degraded"))
      .catch(() => setHealth("down"));
  }, []);

  function updateActive(patch) {
    setConversations((items) =>
      items.map((item) => (item.id === activeId ? { ...item, ...patch, updatedAt: new Date().toISOString() } : item)),
    );
  }

  function createConversation(form, patientId, conversationName) {
    const patient = buildPatient(form, patientId);
    const conversation = {
      id: patientId,
      name: conversationName,
      patient,
      attachments: [],
      messages: [
        {
          role: "assistant",
          content: `Patient ${form.fullName} is ready. Ask the clinical question and attach notes if needed.`,
        },
      ],
      draft: null,
      recommendation: null,
      verification: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    setConversations((items) => [conversation, ...items]);
    setActiveId(patientId);
    setShowModal(false);
    setChatInput("");
    setError("");
  }

  async function handleFiles(event) {
    if (!active) return;
    const parsed = await readClinicalFiles(event.target.files);
    updateActive({ attachments: [...(active.attachments || []), ...parsed] });
    event.target.value = "";
  }

  async function submitChat(event) {
    event.preventDefault();
    const message = chatInput.trim();
    if (!message || !active || loading) return;

    setLoading(true);
    setError("");
    updateActive({ messages: [...active.messages, { role: "user", content: message }] });

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: apiHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          message,
          conversation_id: active.id,
          patient: active.draft?.patient || active.patient,
          clinical_attachments: active.attachments || [],
          language: "vi",
        }),
      });
      if (!response.ok) throw new Error(`Chat API returned ${response.status}`);
      const data = await response.json();
      updateActive({
        draft: data.patient_draft,
        recommendation: data.recommendation,
        verification: data.verification,
        messages: [
          ...active.messages,
          { role: "user", content: message },
          { role: "assistant", content: data.assistant_message.content },
        ],
      });
      setChatInput("");
    } catch (requestError) {
      const content = `API error: ${requestError.message}`;
      setError(requestError.message);
      updateActive({ messages: [...active.messages, { role: "user", content: message }, { role: "assistant", content }] });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="chatgpt-shell">
      {showModal && <PatientModal onCreate={createConversation} />}

      <aside className="conversation-sidebar">
        <div className="brand">
          <MessageSquareText size={21} />
          <strong>HF CDSS</strong>
        </div>
        <button className="new-chat" onClick={() => setShowModal(true)} type="button">
          <Plus size={17} />
          New conversation
        </button>
        <div className="conversation-list">
          {conversations.map((conversation) => {
            const patient = patientSummary(conversation.draft?.patient || conversation.patient);
            return (
              <button
                className={conversation.id === activeId ? "active" : ""}
                key={conversation.id}
                onClick={() => setActiveId(conversation.id)}
                type="button"
              >
                <strong>{conversation.name}</strong>
                <span>{patient?.name} · {patient?.age || "age ?"}</span>
              </button>
            );
          })}
        </div>
        <div className={`api-status ${health}`}>
          {health === "ok" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span>API {health}</span>
        </div>
      </aside>

      <section className="chat-main">
        {active ? (
          <>
            <header className="chat-header">
              <div>
                <h1>{active.name}</h1>
                <p>{summary?.name} · {summary?.sex || "sex ?"} · {summary?.age || "age ?"} years</p>
              </div>
              <label className="attach-button">
                <Upload size={16} />
                Attach
                <input accept=".txt,.csv,.json,.md,.xml,.html,image/*,.pdf" multiple onChange={handleFiles} type="file" />
              </label>
            </header>

            <div className="messages">
              {(active.messages || []).map((message, index) => (
                <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                  <div className="avatar">{message.role === "assistant" ? <Bot size={16} /> : <UserRound size={16} />}</div>
                  <p>{message.content}</p>
                </article>
              ))}
              {loading && (
                <article className="message assistant">
                  <div className="avatar"><LoaderCircle className="spin" size={16} /></div>
                  <p>Checking patient context, safety constraints, retrieval evidence, and citations...</p>
                </article>
              )}
            </div>

            <form className="composer" onSubmit={submitChat}>
              <textarea
                onChange={(event) => setChatInput(event.target.value)}
                placeholder="Ask about symptoms, current medications, titration, contraindications, or monitoring..."
                value={chatInput}
              />
              <button disabled={loading || !chatInput.trim()} type="submit">
                <Send size={18} />
              </button>
            </form>
          </>
        ) : (
          <div className="empty-chat">
            <h1>Start a patient conversation</h1>
            <button className="primary-action" onClick={() => setShowModal(true)} type="button">
              New conversation
            </button>
          </div>
        )}
      </section>

      <aside className="clinical-panel">
        {error && <p className="error-text">{error}</p>}
        {summary ? (
          <>
            <section>
              <h2>Patient</h2>
              <div className="fact-grid">
                <span>ID <strong>{readable(summary.id)}</strong></span>
                <span>Weight <strong>{readable(summary.weightKg)}</strong></span>
                <span>LVEF <strong>{readable(summary.lvef)}</strong></span>
                <span>eGFR <strong>{readable(summary.egfr)}</strong></span>
                <span>K+ <strong>{readable(summary.potassium)}</strong></span>
                <span>SBP <strong>{readable(summary.systolicBp)}</strong></span>
                <span>HR <strong>{readable(summary.heartRate)}</strong></span>
              </div>
              <p><b>Conditions:</b> {summary.conditions.join(", ") || "none detected"}</p>
              <p><b>Meds:</b> {summary.medications.join(", ") || "none detected"}</p>
              {(active?.attachments || []).length > 0 && (
                <div className="attachment-list">
                  {active.attachments.map((file) => (
                    <article key={`${file.file_name}-${file.mime_type}`}>
                      <FileText size={15} />
                      <div>
                        <strong>{file.file_name}</strong>
                        <span>{file.extracted_text ? `${file.extracted_text.length} chars` : file.note}</span>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            {active?.recommendation && (
              <section>
                <h2>Recommendation</h2>
                <div className={`decision ${statusClass(active.recommendation.overall_status)}`}>
                  <ShieldAlert size={17} />
                  <strong>{titleCase(active.recommendation.overall_status)}</strong>
                </div>
                <div className="recommendation-list">
                  {active.recommendation.recommendations.map((item) => (
                    <RecommendationCard item={item} key={item.drug_class} />
                  ))}
                </div>
              </section>
            )}

            {active?.verification?.context?.evidence_chunks?.length > 0 && (
              <section>
                <h2>Evidence</h2>
                <div className="evidence-list">
                  {active.verification.context.evidence_chunks.slice(0, 4).map((chunk) => (
                    <EvidenceCard chunk={chunk} key={chunk.chunk_id} />
                  ))}
                </div>
              </section>
            )}
          </>
        ) : (
          <p className="empty-state">Patient context and evidence will appear here.</p>
        )}
      </aside>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
