/** Clinician-friendly evidence labels shared by admin + clinical UIs. */

export function repairEvidenceText(value) {
  if (!value) return "";

  let text = String(value).replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  if (!text) return "";

  text = text.replace(/(\w)-\s+(?=\w)/g, "$1");
  text = text.replace(/([a-z]{4,})-([a-z]{3,})/gi, "$1$2");
  text = text.replace(/,([A-Za-z])/g, ", $1");
  text = text.replace(/;([A-Za-z])/g, "; $1");
  text = text.replace(/\.([A-Za-z])/g, ". $1");
  text = text.replace(/([a-z]{5,})and([a-z]{5,})/gi, "$1 and $2");
  text = text.replace(/andfor/gi, "and for ");
  text = text.replace(/forpeople/gi, "for people");
  text = text.replace(/peoplewith/gi, "people with");
  text = text.replace(/withCKD/gi, "with CKD");
  text = text.replace(/asthe/gi, "as the");
  text = text.replace(/,so/g, ", so");
  text = text.replace(/sodoes/gi, "so does");
  text = text.replace(/theprevalenceof/gi, "the prevalence of");
  text = text.replace(/dueto/gi, "due to");
  text = text.replace(/lackof/gi, "lack of");
  text = text.replace(/bythe/gi, "by the");
  text = text.replace(/orabsence/gi, "or absence");
  text = text.replace(/ofdiabetes/gi, "of diabetes");
  text = text.replace(/heartfailure/gi, "heart failure");
  text = text.replace(/chronickidney/gi, "chronic kidney");
  text = text.replace(/([a-z])([A-Z])/g, "$1 $2");
  text = text.replace(/\s+/g, " ").trim();

  return text;
}

function titleCaseWords(value) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function looksLikeTechnicalId(value) {
  const text = String(value || "").trim();
  if (!text) return true;
  if (/^[a-f0-9]{8,}$/i.test(text)) return true;
  if (/__/.test(text) && /[a-f0-9]{6,}/i.test(text)) return true;
  if (/^(chunk|claim|doc|rule)[_:]/i.test(text)) return true;
  return false;
}

export function evidenceDocumentTitle(chunk = {}) {
  const meta = chunk.metadata && typeof chunk.metadata === "object" ? chunk.metadata : {};
  const candidates = [
    meta.title,
    meta.document_title,
    meta.guideline_name,
    chunk.document_title,
    chunk.title,
  ];
  for (const candidate of candidates) {
    const text = String(candidate || "").trim();
    if (text && !looksLikeTechnicalId(text)) return titleCaseWords(text);
  }
  const docId = String(chunk.document_id || "").trim();
  if (docId && !looksLikeTechnicalId(docId)) return titleCaseWords(docId);
  return "Clinical source";
}

export function evidenceSectionLabel(chunk = {}) {
  const raw = chunk.section || chunk.evidence_level || "";
  const text = String(raw).replace(/_/g, " ").replace(/\s+/g, " ").trim();
  if (!text || looksLikeTechnicalId(text)) return "";
  return text;
}

export function evidenceSourceTypeLabel(chunk = {}) {
  const raw = String(chunk.source_type || chunk.metadata?.source_type || "")
    .replace(/_/g, " ")
    .trim();
  if (!raw) return "";
  return titleCaseWords(raw);
}

export function evidenceMatchPercent(chunk = {}) {
  const score = chunk.quality_score ?? chunk.score;
  if (score == null || Number.isNaN(Number(score))) return null;
  const n = Number(score);
  const pct = n <= 1 ? Math.round(n * 100) : Math.round(n);
  return Math.max(0, Math.min(100, pct));
}

export function evidenceReadableFacts(chunk = {}) {
  const meta = chunk.metadata && typeof chunk.metadata === "object" ? chunk.metadata : {};
  const facts = [];
  const sourceType = evidenceSourceTypeLabel(chunk);
  if (sourceType) facts.push({ key: "type", value: sourceType });
  if (chunk.page != null && chunk.page !== "") {
    facts.push({ key: "page", value: String(chunk.page) });
  }
  if (meta.publisher) {
    facts.push({ key: "publisher", value: String(meta.publisher) });
  }
  if (meta.year || meta.publication_year) {
    facts.push({
      key: "year",
      value: String(meta.year || meta.publication_year),
    });
  }
  return facts;
}

/** Kept for legacy callers; prefer not showing IDs in clinician UI. */
export function shortenChunkId(chunkId, max = 56) {
  if (!chunkId) return "";
  if (chunkId.length <= max) return chunkId;
  const parts = chunkId.split("__").filter(Boolean);
  if (parts.length >= 2) {
    const tail = parts.slice(-2).join("__");
    if (tail.length <= max) return `…${tail}`;
  }
  const head = Math.max(16, Math.floor(max * 0.45));
  const tailLen = Math.max(10, max - head - 1);
  return `${chunkId.slice(0, head)}…${chunkId.slice(-tailLen)}`;
}
