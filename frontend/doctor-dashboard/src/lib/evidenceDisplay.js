/** Display-time repairs for PDF-extracted evidence snippets (mirrors scraper heuristics). */
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

export function evidenceSectionLabel(chunk) {
  const raw = chunk.section || chunk.evidence_level || chunk.source_type || "";
  return raw.replace(/_/g, " ").replace(/\s+/g, " ").trim();
}
