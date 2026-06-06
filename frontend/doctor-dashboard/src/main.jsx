import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  BookOpen,
  Bot,
  CheckCircle2,
  ClipboardCheck,
  ExternalLink,
  FileText,
  History,
  LoaderCircle,
  MessageSquareText,
  Send,
  ShieldAlert,
  Stethoscope,
  User,
} from "lucide-react";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const CASE_HISTORY_KEY = "hf_cdss_case_history";

const EXAMPLE_PROMPTS = [
  "Male 68, HFrEF, LVEF 28%, eGFR 48, K 4.9, SBP 88, HR 54. Comorbidities: atrial fibrillation. Current meds: metoprolol, furosemide, apixaban.",
  "Female 71, LVEF 30%, eGFR 24, potassium 5.7, SBP 104, HR 70. CKD, diabetes. Meds: furosemide, warfarin, digoxin, atorvastatin, aspirin.",
  "Bệnh nhân nam 64 tuổi suy tim EF còn 32%, mức lọc cầu thận khoảng 78, kali máu 4.4, huyết áp 118/74 và mạch 74 lần/phút. Có tăng huyết áp, đang uống amlodipine.",
];

const SOURCE_LABELS = {
  "week3_pipeline:patient_profile": {
    title: "Patient facts from chat input",
    detail: "Parsed LVEF, eGFR, potassium, blood pressure, heart rate, comorbidities, medications, and allergies.",
  },
  "week3_pipeline:constraint_rules_v1": {
    title: "Constraint rules v1",
    detail: "Local rule file: backend/app/modules/constraint_builder/rules/constraints_v1.json.",
  },
  "week2_rule:MRA_HARD_RENAL_OR_K": {
    title: "MRA renal/potassium safety rule",
    detail: "Avoid or defer MRA when renal impairment is severe or potassium is high.",
  },
  "week2_rule:MRA_MONITORING_K_RENAL": {
    title: "MRA monitoring rule",
    detail: "Close potassium and renal monitoring when moderate risk is detected.",
  },
  "week2_rule:RAASI_CAUTION_BP_K": {
    title: "RAASi/ARNI caution rule",
    detail: "Caution with low blood pressure or elevated potassium.",
  },
  "week2_rule:BETA_BLOCKER_CAUTION_BRADY": {
    title: "Beta blocker bradycardia rule",
    detail: "Caution when heart rate is low.",
  },
  "week2_rule:SGLT2I_RENAL_REVIEW": {
    title: "SGLT2i renal review rule",
    detail: "Review eligibility and monitoring when renal function is reduced.",
  },
  "week2_rule:ALL_GDMT_POLYPHARMACY_REVIEW": {
    title: "Polypharmacy review rule",
    detail: "Medication burden increases sequencing, adherence, and interaction risk.",
  },
  "week3_rule:MRA_MISSING_RENAL_OR_K_REVIEW": {
    title: "MRA missing safety data rule",
    detail: "MRA eligibility requires recent eGFR and potassium before recommendation.",
  },
  "week3_rule:RAASI_MISSING_BP_OR_K_REVIEW": {
    title: "RAASi/ARNI missing safety data rule",
    detail: "RAAS-inhibiting therapy requires blood pressure and potassium review when data are missing.",
  },
  "week3_rule:BETA_BLOCKER_MISSING_HR_REVIEW": {
    title: "Beta blocker missing heart-rate rule",
    detail: "Beta blocker initiation or titration requires heart-rate review when data are missing.",
  },
  "week3_rule:SGLT2I_MISSING_EGFR_REVIEW": {
    title: "SGLT2i missing eGFR rule",
    detail: "SGLT2 inhibitor eligibility requires renal function review when eGFR is missing.",
  },
};

function titleCase(value) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function numberAfter(pattern, text) {
  const match = text.match(pattern);
  return match ? Number.parseFloat(match[1]) : null;
}

function firstNumberAfter(patterns, text) {
  for (const pattern of patterns) {
    const value = numberAfter(pattern, text);
    if (value !== null) return value;
  }
  return null;
}

function listAfter(pattern, text) {
  const match = text.match(pattern);
  if (!match) return [];

  return match[1]
    .split(/,|;|\band\b|\bva\b/i)
    .map((item) => item.trim().replace(/\.$/, ""))
    .filter(Boolean);
}

function detectComorbidities(text) {
  const lower = text.toLowerCase();
  const comorbidities = [];
  const mappings = [
    ["ckd", ["ckd", "chronic kidney disease", "kidney disease"]],
    ["Diabetes", ["diabetes", "dm", "type 2 diabetes", "t2dm"]],
    ["Hypertension", ["hypertension", "htn", "tang huyet ap"]],
    ["Atrial fibrillation", ["atrial fibrillation", "afib", "af ", "rung nhi"]],
    ["COPD", ["copd", "asthma", "hen"]],
  ];

  mappings.forEach(([label, keywords]) => {
    if (keywords.some((keyword) => lower.includes(keyword))) {
      comorbidities.push(label);
    }
  });

  return [...new Set(comorbidities)];
}

function detectMedications(text) {
  const lower = text.toLowerCase();
  const knownMedications = [
    "amlodipine",
    "apixaban",
    "aspirin",
    "atorvastatin",
    "bisoprolol",
    "bumetanide",
    "candesartan",
    "carvedilol",
    "dapagliflozin",
    "digoxin",
    "empagliflozin",
    "enalapril",
    "eplerenone",
    "furosemide",
    "hydralazine",
    "ivabradine",
    "losartan",
    "metoprolol",
    "patiromer",
    "sacubitril",
    "spironolactone",
    "torsemide",
    "valsartan",
    "warfarin",
  ];

  return knownMedications.filter((medication) => lower.includes(medication));
}

function parsePatient(text) {
  const now = Date.now();
  const age = firstNumberAfter(
    [
      /\b(?:age|tuoi|aged)\s*:?\s*(\d{1,3})\b/i,
      /\b(\d{1,3})\s*(?:year-old|years old|yo|tuoi)\b/i,
      /\b(?:nam|nu|male|female)\s+(\d{1,3})\s*(?:tuoi|yo|years old)?\b/i,
    ],
    text,
  );
  const sex = /\bfemale\b|\bnu\b|bệnh nhân nữ/i.test(text) ? "female" : /\bmale\b|\bnam\b|bệnh nhân nam/i.test(text) ? "male" : null;
  const lvef = firstNumberAfter(
    [
      /\b(?:lvef|ef)\s*(?:is|was|=|:|còn|khoảng|about|around)?\s*(\d+(?:\.\d+)?)\s*%?/i,
      /\b(?:ejection fraction|phan suat tong mau)\s*(?:is|was|=|:|còn|khoảng|about|around)?\s*(\d+(?:\.\d+)?)\s*%?/i,
      /\b(?:suy tim).*?\b(?:ef|lvef)\s*(?:còn|khoảng|about|around)?\s*(\d+(?:\.\d+)?)\s*%?/i,
    ],
    text,
  );
  const egfr = firstNumberAfter(
    [
      /\begfr\s*(?:is|was|=|:|khoảng|about|around)?\s*(\d+(?:\.\d+)?)/i,
      /\b(?:estimated gfr|glomerular filtration rate)\s*(?:is|was|=|:|about|around)?\s*(\d+(?:\.\d+)?)/i,
      /\b(?:mức lọc cầu thận|muc loc cau than|lọc cầu thận|loc cau than)\s*(?:còn|là|khoảng|about|around)?\s*(\d+(?:\.\d+)?)/i,
      /\b(?:thận|than|renal).*?(?:eGFR|mức lọc|loc).*?(\d+(?:\.\d+)?)/i,
    ],
    text,
  );
  const potassium = firstNumberAfter(
    [
      /\b(?:potassium|k\+?|kali)\s*(?:is|was|=|:|máu|mau|là|khoảng|about|around)?\s*(\d+(?:\.\d+)?)/i,
      /\b(?:serum potassium|kali máu|kali mau)\s*(?:is|was|=|:|là|khoảng|about|around)?\s*(\d+(?:\.\d+)?)/i,
    ],
    text,
  );
  const systolic_bp = firstNumberAfter(
    [
      /\b(?:sbp|systolic(?: bp)?|huyet ap tam thu|huyết áp tâm thu)\s*(?:is|was|=|:|là|khoảng|about|around)?\s*(\d+(?:\.\d+)?)/i,
      /\b(?:bp|blood pressure|huyet ap|huyết áp)\s*(?:is|was|=|:|là|khoảng|about|around)?\s*(\d{2,3})(?:\/\d{2,3})?/i,
      /(?:huyết áp|huyet ap)\s*(?:là|la|khoảng|khoang|about|around)?\s*(\d{2,3})(?:\/\d{2,3})?/i,
      /\b(?:áp|ap)\s*(?:là|khoảng)?\s*(\d{2,3})(?:\/\d{2,3})/i,
    ],
    text,
  );
  const heart_rate = firstNumberAfter(
    [
      /\b(?:hr|heart rate|pulse|mach|mạch)\s*(?:is|was|=|:|là|khoảng|about|around)?\s*(\d+(?:\.\d+)?)/i,
      /\b(?:nhịp tim|nhip tim)\s*(?:is|was|=|:|là|khoảng|about|around)?\s*(\d+(?:\.\d+)?)/i,
      /(?:mạch|mach|nhịp tim|nhip tim)\s*(?:là|la|khoảng|khoang|about|around)?\s*(\d+(?:\.\d+)?)/i,
      /\b(\d+(?:\.\d+)?)\s*(?:bpm|lần\/phút|lan\/phut)\b/i,
    ],
    text,
  );
  const medications = [
    ...listAfter(/\b(?:current meds?|medications?|meds?|thuoc dang dung|thuốc đang dùng|thuoc|thuốc|đang uống|dang uong|using|taking)\s*:?\s*([^.;]+)/i, text),
    ...detectMedications(text),
  ];
  const allergies = listAfter(/\b(?:allerg(?:y|ies)|di ung|dị ứng|không dung nạp|khong dung nap)\s*:?\s*([^.;]+)/i, text);
  const explicitComorbidities = listAfter(/\b(?:comorbidit(?:y|ies)|benh nen)\s*:?\s*([^.;]+)/i, text);
  const comorbidities = [...new Set([...detectComorbidities(text), ...explicitComorbidities])];

  return {
    case_id: `CHAT_${now}`,
    age,
    sex,
    lvef,
    egfr,
    potassium,
    systolic_bp,
    heart_rate,
    comorbidities,
    current_medications: [...new Set(medications)],
    allergies,
  };
}

function missingFields(patient) {
  return ["lvef", "egfr", "potassium", "systolic_bp", "heart_rate"].filter((field) => patient[field] === null);
}

function statusClass(status) {
  if (status === "blocked" || status === "avoid" || status === "high") return "danger";
  if (status === "approved_with_warnings" || status === "consider_with_caution" || status === "moderate") return "warning";
  return "success";
}

function statusLabel(status) {
  const labels = {
    approved: "Có thể cân nhắc",
    approved_with_warnings: "Cần thận trọng",
    blocked: "Có chống chỉ định/cần trì hoãn",
    consider: "Cân nhắc sử dụng",
    consider_with_caution: "Cân nhắc nhưng cần thận trọng",
    avoid: "Tránh hoặc trì hoãn",
    review: "Cần bác sĩ xem lại",
    high: "Nguy cơ cao",
    moderate: "Nguy cơ vừa",
    low: "Nguy cơ thấp",
  };

  return labels[status] ?? status;
}

function fieldLabel(field) {
  const labels = {
    lvef: "LVEF/EF",
    egfr: "eGFR",
    potassium: "Kali máu",
    systolic_bp: "Huyết áp tâm thu",
    heart_rate: "Mạch/nhịp tim",
  };

  return labels[field] ?? field;
}

function factStatus(value) {
  return value === null || value === undefined ? "missing" : value;
}

function medicationGroups(recommendations) {
  return {
    avoid: recommendations.filter((item) => item.status === "avoid"),
    caution: recommendations.filter((item) => item.status === "consider_with_caution"),
    consider: recommendations.filter((item) => item.status === "consider"),
    review: recommendations.filter((item) => item.status === "review"),
  };
}

function ruleSourceLookup(rules) {
  return rules.reduce((accumulator, rule) => {
    if (rule.evidence_ref) {
      accumulator[rule.evidence_ref] = rule;
    }
    return accumulator;
  }, {});
}

function collectSources(recommendation, rules) {
  if (!recommendation) return [];

  const ids = new Set();
  const rulesByEvidenceRef = ruleSourceLookup(rules);
  recommendation.recommendations.forEach((item) => item.evidence.forEach((source) => ids.add(source)));
  recommendation.constraints.forEach((constraint) => {
    if (constraint.evidence_ref) ids.add(constraint.evidence_ref);
  });

  return [...ids].map((id) => {
    const rule = rulesByEvidenceRef[id];
    return {
      id,
      title: SOURCE_LABELS[id]?.title ?? rule?.constraint_id ?? id,
      detail: SOURCE_LABELS[id]?.detail ?? rule?.reason ?? "Structured evidence reference returned by the backend.",
      clinical_sources: rule?.clinical_sources ?? [],
    };
  });
}

function buildAssistantMessage(recommendation) {
  const statuses = recommendation.recommendations.map((item) => `${item.drug_class}: ${statusLabel(item.status)}`).join("; ");
  const safetyWarningCount = (recommendation.dose_warnings?.length ?? 0) + (recommendation.interaction_warnings?.length ?? 0);
  const constraints = recommendation.constraints.length || safetyWarningCount
    ? `${recommendation.constraints.length} medication constraint(s) and ${safetyWarningCount} safety warning(s) detected.`
    : "No medication constraints detected.";

  return `Kết luận: ${statusLabel(recommendation.overall_status)}. ${constraints} ${statuses}`;
}

function buildFriendlyAssistantMessage(recommendation) {
  const cautionItems = recommendation.recommendations
    .filter((item) => item.status === "consider_with_caution" || item.status === "avoid")
    .map((item) => item.drug_class);
  const considerItems = recommendation.recommendations
    .filter((item) => item.status === "consider")
    .map((item) => item.drug_class);
  const safetyWarningCount = (recommendation.dose_warnings?.length ?? 0) + (recommendation.interaction_warnings?.length ?? 0);
  let constraintText = recommendation.constraints.length || safetyWarningCount
    ? `Hệ thống phát hiện ${recommendation.constraints.length} cảnh báo an toàn liên quan đến thuốc.`
    : "Hệ thống chưa phát hiện cảnh báo an toàn lớn từ dữ liệu hiện có.";

  if (recommendation.constraints.length || safetyWarningCount) {
    constraintText = `He thong phat hien ${recommendation.constraints.length} rang buoc va ${safetyWarningCount} canh bao lieu/tuong tac thuoc.`;
  }

  const lines = [
    `Kết luận tổng quát: ${statusLabel(recommendation.overall_status)}.`,
    constraintText,
  ];

  if (cautionItems.length > 0) {
    lines.push(`Cần bác sĩ xem kỹ trước khi dùng hoặc tăng liều: ${cautionItems.join(", ")}.`);
  }

  if (considerItems.length > 0) {
    lines.push(`Có thể cân nhắc nếu phù hợp lâm sàng: ${considerItems.join(", ")}.`);
  }

  lines.push("Xem panel kết quả bên phải để biết dữ liệu nào kích hoạt cảnh báo, rule nào được dùng, và nguồn evidence liên quan.");

  return lines.join("\n");
}

const PROCESSING_STEPS = [
  { id: "parse", label: "Đọc và chuẩn hóa dữ liệu bệnh nhân" },
  { id: "recommend", label: "Phân tích nguy cơ và tạo khuyến nghị" },
  { id: "verify", label: "Truy xuất evidence và chạy verification agents" },
  { id: "explain", label: "LLM local đang soạn kết luận cuối" },
];

function ProcessingProgress({ activeStep }) {
  const activeIndex = PROCESSING_STEPS.findIndex((step) => step.id === activeStep);

  return (
    <article className="message assistant processing-message">
      <div className="avatar"><LoaderCircle className="spinner" size={16} /></div>
      <div className="processing-card">
        <strong>Đang xử lý ca bệnh</strong>
        <div className="processing-steps">
          {PROCESSING_STEPS.map((step, index) => (
            <div className={index < activeIndex ? "complete" : index === activeIndex ? "active" : ""} key={step.id}>
              <span />
              <p>{step.label}</p>
            </div>
          ))}
        </div>
      </div>
    </article>
  );
}

function readCaseHistory() {
  try {
    return JSON.parse(localStorage.getItem(CASE_HISTORY_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function writeCaseHistory(records) {
  localStorage.setItem(CASE_HISTORY_KEY, JSON.stringify(records.slice(0, 20)));
}

function MedicationItem({ item }) {
  return (
    <article className="medication-item">
      <div>
        <strong>{item.drug_class}</strong>
        <span>{statusLabel(item.status)}</span>
      </div>
      <p>{item.rationale}</p>
      {item.warnings.length > 0 && (
        <ul>
          {item.warnings.slice(0, 2).map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      )}
    </article>
  );
}

function readableSourceType(sourceType) {
  if (sourceType === "guideline") return "Guideline";
  if (sourceType === "drug_label") return "Drug label";
  return titleCase(sourceType || "Evidence");
}

function evidenceTitle(chunk) {
  const section = chunk.section && chunk.section.length < 80 ? ` - ${titleCase(chunk.section)}` : "";
  return `${titleCase(chunk.document_id || "Clinical source")}${section}`;
}

function evidenceReason(chunk) {
  const text = `${chunk.section || ""} ${chunk.text || ""}`.toLowerCase();
  const reasons = [];
  if (text.includes("heart failure") || text.includes("hfref") || text.includes("ejection fraction")) reasons.push("phu hop voi suy tim EF giam");
  if (text.includes("potassium") || text.includes("hyperkal")) reasons.push("lien quan kali mau");
  if (text.includes("egfr") || text.includes("renal") || text.includes("kidney")) reasons.push("lien quan chuc nang than");
  if (text.includes("blood pressure") || text.includes("hypotension")) reasons.push("lien quan huyet ap");
  if (text.includes("contraindication")) reasons.push("co thong tin chong chi dinh/canh bao");
  if (reasons.length === 0) return "Nguon nay duoc truy xuat vi co lien quan den thuoc, nguy co hoac guideline trong ca benh.";
  return `Nguon nay duoc dung vi ${reasons.slice(0, 3).join(", ")}.`;
}

function cleanEvidenceExcerpt(text) {
  return (text || "")
    .replace(/\s+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/â€|Ã¢|Â/g, "")
    .trim()
    .slice(0, 520);
}

function EvidenceCard({ chunk }) {
  const score = typeof chunk.score === "number" ? Math.round(chunk.score * 100) : null;
  return (
    <article className="evidence-card">
      <div className="evidence-card-header">
        <strong>{evidenceTitle(chunk)}</strong>
        <span>{readableSourceType(chunk.source_type)}</span>
      </div>
      <p>{evidenceReason(chunk)}</p>
      <div className="evidence-meta">
        {score !== null && <span>Do lien quan: {score}%</span>}
        {chunk.metadata?.publisher && <span>{chunk.metadata.publisher}</span>}
        {chunk.metadata?.source_file && <span>{chunk.metadata.source_file.split(/[\\/]/).slice(-1)[0]}</span>}
      </div>
      <details className="lineage-details">
        <summary>Chi tiet ky thuat</summary>
        <p>{cleanEvidenceExcerpt(chunk.text)}</p>
        <code>{chunk.chunk_id}</code>
      </details>
    </article>
  );
}

function CaseReviewPage({ caseHistory, onSelectCase, selectedCaseId }) {
  const selectedCase = caseHistory.find((item) => item.id === selectedCaseId) ?? caseHistory[0];

  if (caseHistory.length === 0) {
    return (
      <section className="page-shell">
        <div className="empty-state">Chưa có ca nào. Hãy chạy một ca ở trang Chat trước, hệ thống sẽ lưu lại để review.</div>
      </section>
    );
  }

  return (
    <section className="review-layout">
      <aside className="review-list">
        <h2>Case Review</h2>
        {caseHistory.map((record) => (
          <button
            className={record.id === selectedCase.id ? "active" : ""}
            key={record.id}
            onClick={() => onSelectCase(record.id)}
            type="button"
          >
            <strong>{record.recommendation.case_id}</strong>
            <span>{new Date(record.created_at).toLocaleString()}</span>
            <em>{statusLabel(record.recommendation.overall_status)}</em>
          </button>
        ))}
      </aside>

      <article className="review-detail">
        <header>
          <h2>{selectedCase.recommendation.case_id}</h2>
          <span className={statusClass(selectedCase.recommendation.overall_status)}>
            {statusLabel(selectedCase.recommendation.overall_status)}
          </span>
        </header>

        <section className="section-card">
          <h3>Input ban đầu</h3>
          <p className="case-note">{selectedCase.input_text}</p>
        </section>

        <section className="section-card">
          <h3>Dữ liệu đã extract</h3>
          <div className="fact-grid friendly">
            <span>LVEF/EF <strong>{factStatus(selectedCase.patient.lvef)}</strong></span>
            <span>eGFR <strong>{factStatus(selectedCase.patient.egfr)}</strong></span>
            <span>Kali <strong>{factStatus(selectedCase.patient.potassium)}</strong></span>
            <span>Huyết áp tâm thu <strong>{factStatus(selectedCase.patient.systolic_bp)}</strong></span>
            <span>Mạch <strong>{factStatus(selectedCase.patient.heart_rate)}</strong></span>
            <span>Số thuốc <strong>{selectedCase.patient.current_medications.length}</strong></span>
          </div>
        </section>

        <section className="section-card">
          <h3>Trace khuyến nghị</h3>
          <div className="review-metrics">
            <span><strong>{selectedCase.recommendation.risk_flags.length}</strong> risks</span>
            <span><strong>{selectedCase.recommendation.constraints.length}</strong> constraints</span>
            <span><strong>{selectedCase.recommendation.recommendations.length}</strong> medication classes</span>
          </div>
          <div className="recommendation-lanes">
            {selectedCase.recommendation.recommendations.map((item) => (
              <MedicationItem item={item} key={item.drug_class} />
            ))}
          </div>
        </section>
      </article>
    </section>
  );
}

function EvidenceBrowserPage({ rules }) {
  const grouped = rules.reduce((accumulator, rule) => {
    const key = rule.constraint_type ?? "unknown";
    accumulator[key] = [...(accumulator[key] ?? []), rule];
    return accumulator;
  }, {});

  return (
    <section className="page-shell">
      <div className="page-heading">
        <h2>Evidence Browser</h2>
        <p>Danh sách rule/source hiện đang được hệ thống Week 3 dùng để tạo constraints.</p>
      </div>

      <div className="evidence-grid">
        {Object.entries(grouped).map(([type, items]) => (
          <section className="section-card" key={type}>
            <h3>{titleCase(type)} rules</h3>
            <div className="source-list">
              {items.map((rule) => (
                <article key={rule.constraint_id}>
                  <div className="rule-heading">
                    <strong>{rule.constraint_id}</strong>
                    <span>{rule.evidence_ref?.startsWith("week3") ? "Week 3 rule" : "Week 2 curated rule"}</span>
                  </div>
                  <p>{rule.reason}</p>
                  <div className="clinical-source-list">
                    {(rule.clinical_sources ?? []).map((source) => (
                      <a href={source.url} key={`${rule.constraint_id}-${source.source_id}`} rel="noreferrer" target="_blank">
                        <div>
                          <strong>{source.title}</strong>
                          <p>{source.note}</p>
                        </div>
                        <ExternalLink size={16} />
                      </a>
                    ))}
                  </div>
                  <div className="rule-meta">
                    <span>Target: {rule.target_drug_class}</span>
                    <span>Action: {rule.action}</span>
                    <span>Risks: {rule.risk_names.join(", ")}</span>
                  </div>
                  <details className="lineage-details">
                    <summary>Rule lineage</summary>
                    <code>{rule.evidence_ref}</code>
                  </details>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

function App() {
  const [activePage, setActivePage] = useState("chat");
  const [health, setHealth] = useState("checking");
  const [input, setInput] = useState(EXAMPLE_PROMPTS[0]);
  const [patient, setPatient] = useState(null);
  const [recommendation, setRecommendation] = useState(null);
  const [caseHistory, setCaseHistory] = useState(() => readCaseHistory());
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [verificationLoading, setVerificationLoading] = useState(false);
  const [processingStep, setProcessingStep] = useState(null);
  const [verification, setVerification] = useState(null);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Nhập tình trạng bệnh nhân theo cách tự nhiên. Tôi sẽ đọc dữ liệu, chạy CDSS, kiểm tra GraphRAG/agents, rồi trả lời bằng ngôn ngữ dễ hiểu.",
    },
  ]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((response) => response.json())
      .then((data) => setHealth(data.status))
      .catch(() => setHealth("offline"));
  }, []);

  useEffect(() => {
    fetch(`${API_BASE_URL}/rules`)
      .then((response) => response.json())
      .then((data) => setRules(data))
      .catch(() => setRules([]));
  }, []);

  const sources = useMemo(() => collectSources(recommendation, rules), [recommendation, rules]);
  const missing = useMemo(() => (patient ? missingFields(patient) : []), [patient]);
  const groupedRecommendations = useMemo(
    () => (recommendation ? medicationGroups(recommendation.recommendations) : null),
    [recommendation],
  );

  function submitCase(event) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;

    const parsedPatient = parsePatient(trimmed);
    setMessages((current) => [...current, { role: "user", content: trimmed }]);
    setPatient(parsedPatient);
    setRecommendation(null);
    setVerification(null);
    setError("");

    setLoading(true);
    setProcessingStep("parse");
    fetch(`${API_BASE_URL}/recommend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient: parsedPatient }),
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        setProcessingStep("recommend");
        setRecommendation(data);
        const record = {
          id: `${data.case_id}_${Date.now()}`,
          created_at: new Date().toISOString(),
          input_text: trimmed,
          patient: parsedPatient,
          recommendation: data,
        };
        setCaseHistory((current) => {
          const next = [record, ...current].slice(0, 20);
          writeCaseHistory(next);
          return next;
        });
        setSelectedCaseId(record.id);
        setVerificationLoading(true);
        setProcessingStep("verify");
        fetch(`${API_BASE_URL}/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ patient: parsedPatient, recommendation: data }),
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`Verification API returned ${response.status}`);
            }
            return response.json();
          })
          .then((verificationData) => {
            setVerification(verificationData);
            setProcessingStep("explain");
            return fetch(`${API_BASE_URL}/llm/answer`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                user_input: trimmed,
                patient: parsedPatient,
                recommendation: data,
                verification: verificationData,
              }),
            });
          })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`LLM API returned ${response.status}`);
            }
            return response.json();
          })
          .then((llmData) => {
            setMessages((current) => [...current, { role: "assistant", content: llmData.answer }]);
            if (false && llmData.used_llm) {
              setMessages((current) => [
                ...current,
                { role: "assistant", content: `Diễn giải thêm từ LLM local:\n\n${llmData.answer}` },
              ]);
            }
          })
          .catch((verificationError) => {
            setVerification({
              final_verdict: "warning",
              context: null,
              agent_results: [
                {
                  agent_name: "verification_client",
                  verdict: "warning",
                  message: verificationError.message,
                  evidence_refs: [],
                },
              ],
            });
            setMessages((current) => [...current, { role: "assistant", content: buildFriendlyAssistantMessage(data) }]);
          })
          .finally(() => {
            setVerificationLoading(false);
            setProcessingStep(null);
          });
      })
      .catch((requestError) => {
        setError(requestError.message);
        setMessages((current) => [
          ...current,
          { role: "assistant", content: `API error: ${requestError.message}` },
        ]);
        setProcessingStep(null);
      })
      .finally(() => setLoading(false));
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Heart Failure CDSS</h1>
          <p>Chat-based clinical recommendation workflow</p>
        </div>
        <div className="topbar-actions">
          <nav className="page-tabs" aria-label="Main pages">
            <button className={activePage === "chat" ? "active" : ""} onClick={() => setActivePage("chat")} type="button">
              <MessageSquareText size={16} /> Chat
            </button>
            <button className={activePage === "review" ? "active" : ""} onClick={() => setActivePage("review")} type="button">
              <History size={16} /> Case Review
            </button>
            <button className={activePage === "evidence" ? "active" : ""} onClick={() => setActivePage("evidence")} type="button">
              <BookOpen size={16} /> Evidence
            </button>
          </nav>
          <div className={`status status-${health}`}>
            {health === "ok" ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
            <span>API {health}</span>
          </div>
        </div>
      </header>

      {activePage === "review" && (
        <CaseReviewPage
          caseHistory={caseHistory}
          onSelectCase={setSelectedCaseId}
          selectedCaseId={selectedCaseId}
        />
      )}

      {activePage === "evidence" && <EvidenceBrowserPage rules={rules} />}

      {activePage === "chat" && <section className="chat-workspace">
        <div className="chat-panel">
          <div className="panel-title">
            <Bot size={20} />
            <h2>Patient Intake Chat</h2>
          </div>

          <div className="message-list">
            {messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="avatar">{message.role === "assistant" ? <Bot size={16} /> : <User size={16} />}</div>
                <p>{message.content}</p>
              </article>
            ))}
            {false && loading && (
              <article className="message assistant">
                <div className="avatar"><Bot size={16} /></div>
                <p>Đang phân tích dữ liệu bệnh nhân, kiểm tra constraints, truy xuất evidence và soạn câu trả lời...</p>
              </article>
            )}
            {false && verificationLoading && !loading && (
              <article className="message assistant">
                <div className="avatar"><Bot size={16} /></div>
                <p>Đã có kết luận CDSS. LLM local đang soạn phần diễn giải bổ sung, bước này có thể mất một lúc khi chạy bằng CPU...</p>
              </article>
            )}
            {processingStep && <ProcessingProgress activeStep={processingStep} />}
          </div>

          <div className="example-row">
            {EXAMPLE_PROMPTS.map((prompt, index) => (
              <button key={prompt} onClick={() => setInput(prompt)} type="button">
                Case {index + 1}
              </button>
            ))}
          </div>

          <form className="composer" onSubmit={submitCase}>
            <textarea
              onChange={(event) => setInput(event.target.value)}
              placeholder="Example: Male 68, LVEF 28%, eGFR 48, K 4.9, SBP 88, HR 54. CKD, diabetes. Meds: metoprolol, furosemide. Allergy: ACEi angioedema."
              value={input}
            />
            <button disabled={loading} title="Send patient case" type="submit">
              <Send size={18} />
            </button>
          </form>
        </div>

        <aside className="output-panel">
          <div className="panel-title">
            <ClipboardCheck size={20} />
            <h2>Kết quả hỗ trợ quyết định</h2>
          </div>

          {error && <p className="error-text">API error: {error}</p>}
          {!recommendation && !error && <p className="empty-state">Nhập tình trạng bệnh nhân ở khung chat để xem khuyến nghị, cảnh báo an toàn và nguồn đã dùng.</p>}

          {patient && (
            <section className="summary-card">
              <h3><Stethoscope size={16} /> Dữ liệu đã đọc từ mô tả</h3>
              <div className="fact-grid friendly">
                <span>LVEF/EF <strong>{factStatus(patient.lvef)}</strong></span>
                <span>eGFR <strong>{factStatus(patient.egfr)}</strong></span>
                <span>Kali <strong>{factStatus(patient.potassium)}</strong></span>
                <span>Huyết áp tâm thu <strong>{factStatus(patient.systolic_bp)}</strong></span>
                <span>Mạch <strong>{factStatus(patient.heart_rate)}</strong></span>
                <span>Số thuốc <strong>{patient.current_medications.length}</strong></span>
              </div>
              <p className="muted">Bệnh nền: {patient.comorbidities.join(", ") || "chưa nhận diện"}</p>
              <p className="muted">Thuốc đang dùng: {patient.current_medications.join(", ") || "chưa nhận diện"}</p>
            </section>
          )}

          {recommendation && groupedRecommendations && (
            <div className="results">
              <div className={`decision-banner ${statusClass(recommendation.overall_status)}`}>
                <ShieldAlert size={22} />
                <div>
                  <span>Kết luận tổng quát</span>
                  <strong>{statusLabel(recommendation.overall_status)}</strong>
                  <p>
                    {recommendation.overall_status === "approved"
                      ? "Không phát hiện cảnh báo chính trong dữ liệu hiện có."
                      : "Có dữ liệu thiếu hoặc yếu tố nguy cơ, cần bác sĩ kiểm tra trước khi dùng thuốc."}
                  </p>
                </div>
              </div>

              {missing.length > 0 && (
                <section className="section-card attention">
                  <h3>Cần bổ sung trước khi quyết định chắc chắn</h3>
                  <div className="missing-list">
                    {missing.map((field) => <span key={field}>{fieldLabel(field)}</span>)}
                  </div>
                </section>
              )}

              <section className="section-card">
                <h3>Khuyến nghị thuốc</h3>
                <div className="recommendation-lanes">
                  {groupedRecommendations.avoid.length > 0 && (
                    <div className="lane danger">
                      <h4>Tránh hoặc trì hoãn</h4>
                      {groupedRecommendations.avoid.map((item) => <MedicationItem item={item} key={item.drug_class} />)}
                    </div>
                  )}
                  {groupedRecommendations.caution.length > 0 && (
                    <div className="lane warning">
                      <h4>Cân nhắc nhưng cần thận trọng</h4>
                      {groupedRecommendations.caution.map((item) => <MedicationItem item={item} key={item.drug_class} />)}
                    </div>
                  )}
                  {groupedRecommendations.consider.length > 0 && (
                    <div className="lane success">
                      <h4>Có thể cân nhắc</h4>
                      {groupedRecommendations.consider.map((item) => <MedicationItem item={item} key={item.drug_class} />)}
                    </div>
                  )}
                  {groupedRecommendations.review.length > 0 && (
                    <div className="lane warning">
                      <h4>Cần xem lại theo phenotype</h4>
                      {groupedRecommendations.review.map((item) => <MedicationItem item={item} key={item.drug_class} />)}
                    </div>
                  )}
                </div>
              </section>

              <section className="section-card">
                <h3>Vì sao hệ thống cảnh báo?</h3>
                <div className="explain-grid">
                  <div>
                    <h4>Yếu tố nguy cơ</h4>
                    {recommendation.risk_flags.map((risk) => (
                      <div className="compact-row" key={`${risk.name}-${risk.evidence}`}>
                        <strong>{titleCase(risk.name)}</strong>
                        <span className={statusClass(risk.severity)}>{statusLabel(risk.severity)}</span>
                        <p>{risk.evidence}</p>
                      </div>
                    ))}
                    {recommendation.risk_flags.length === 0 && <p className="muted">No risk flags detected.</p>}
                  </div>
                  <div>
                    <h4>Ràng buộc dùng thuốc</h4>
                    {recommendation.constraints.map((constraint) => (
                      <div className="compact-row" key={constraint.constraint_id}>
                        <strong>{constraint.target_drug_class}</strong>
                        <span className={statusClass(constraint.action)}>{constraint.constraint_type ?? constraint.action}</span>
                        <p>{constraint.reason}</p>
                      </div>
                    ))}
                    {recommendation.constraints.length === 0 && <p className="muted">No medication constraints detected.</p>}
                  </div>
                  <div>
                    <h4>Dose & interaction</h4>
                    {[...(recommendation.dose_warnings ?? []), ...(recommendation.interaction_warnings ?? [])].map((warning) => (
                      <div className="compact-row" key={warning.warning_id}>
                        <strong>{warning.target}</strong>
                        <span className={statusClass(warning.severity)}>{statusLabel(warning.severity)}</span>
                        <p>{warning.message}</p>
                      </div>
                    ))}
                    {((recommendation.dose_warnings?.length ?? 0) + (recommendation.interaction_warnings?.length ?? 0)) === 0 && (
                      <p className="muted">No dose or interaction warnings detected.</p>
                    )}
                  </div>
                </div>
              </section>

              <section className="section-card">
                <h3><FileText size={16} /> Nguồn và luật đã dùng</h3>
                <div className="source-list">
                  {sources.map((source) => (
                    <article key={source.id}>
                      <strong>{source.title}</strong>
                      <p>{source.detail}</p>
                      {source.clinical_sources.length > 0 && (
                        <div className="clinical-source-list compact">
                          {source.clinical_sources.map((clinicalSource) => (
                            <a href={clinicalSource.url} key={`${source.id}-${clinicalSource.source_id}`} rel="noreferrer" target="_blank">
                              <div>
                                <strong>{clinicalSource.title}</strong>
                                <p>{clinicalSource.note}</p>
                              </div>
                              <ExternalLink size={16} />
                            </a>
                          ))}
                        </div>
                      )}
                      <details className="lineage-details">
                        <summary>Rule/source id</summary>
                        <code>{source.id}</code>
                      </details>
                    </article>
                  ))}
                </div>
              </section>

              <section className="section-card">
                <h3><ShieldAlert size={16} /> GraphRAG và agent verification</h3>
                {verificationLoading && <p className="muted">Đang truy xuất graph/evidence và chạy verification agents...</p>}
                {verification && (
                  <div className="agent-panel">
                    <div className={`agent-verdict ${statusClass(verification.final_verdict === "fail" ? "blocked" : verification.final_verdict === "warning" ? "approved_with_warnings" : "approved")}`}>
                      <strong>Final verdict</strong>
                      <span>{verification.final_verdict}</span>
                    </div>

                    {verification.context && (
                      <div className="context-stats">
                        <span><strong>{verification.context.graph_facts.length}</strong> quan he y khoa</span>
                        <span><strong>{verification.context.evidence_chunks.length}</strong> nguon tham khao</span>
                        <span><strong>{verification.context.retrieval_sources?.join(", ") || "GraphRAG"}</strong></span>
                      </div>
                    )}

                    <div className="agent-grid">
                      {verification.agent_results.map((agent) => (
                        <article className="agent-card" key={agent.agent_name}>
                          <div>
                            <strong>{titleCase(agent.agent_name)}</strong>
                            <span className={statusClass(agent.verdict === "fail" ? "blocked" : agent.verdict === "warning" ? "approved_with_warnings" : "approved")}>
                              {agent.verdict}
                            </span>
                          </div>
                          <p>{agent.message}</p>
                          {agent.evidence_refs.length > 0 && <code>{agent.evidence_refs.slice(0, 3).join(" | ")}</code>}
                        </article>
                      ))}
                    </div>

                    {verification.context?.evidence_chunks?.length > 0 && (
                      <div className="evidence-summary-list">
                        <h4>Nguon tham khao he thong da dung</h4>
                        {verification.context.evidence_chunks.slice(0, 3).map((chunk) => (
                          <EvidenceCard chunk={chunk} key={`friendly-${chunk.chunk_id}`} />
                        ))}
                      </div>
                    )}

                    {verification.context?.evidence_chunks?.length > 0 && (
                      <details className="retrieval-details">
                        <summary>Evidence chunks retrieved</summary>
                        {verification.context.evidence_chunks.slice(0, 3).map((chunk) => (
                          <article key={chunk.chunk_id}>
                            <strong>{chunk.document_id} · {chunk.section}</strong>
                            <p>{chunk.text}</p>
                          </article>
                        ))}
                      </details>
                    )}
                  </div>
                )}
              </section>

              <p className="disclaimer">{recommendation.disclaimer}</p>
            </div>
          )}
        </aside>
      </section>}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
