import { apiFetch } from "@shared/api/client.js";
import { parseSseBlock } from "../utils";
import { compactPatientForRequest } from "../hooks/patientPayload.js";

const STATUS_LABELS = {
  received: "Opening streaming bundle...",
  extracting_patient: "Collecting patient draft...",
  building_recommendation: "Processing medication safety...",
  verifying_evidence: "Retrieving and validating evidence...",
  generating_answer: "Reasoning over the verified recommendation...",
};

export async function streamClinicalChat({
  message,
  active,
  language,
  signal,
  onStatus,
  onDraft,
  onRecommendation,
  onVerification,
  onAnswerDelta,
  onDone,
  onError,
}) {
  const response = await apiFetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: active.id,
      patient: compactPatientForRequest(active),
      clinical_attachments: active.attachments || [],
      language,
    }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    let messageText = `Chat API returned ${response.status}`;
    if (text) {
      try {
        const data = JSON.parse(text);
        messageText =
          (typeof data === "object" && (data?.error?.message || data?.detail)) ||
          messageText;
        if (typeof messageText !== "string") {
          messageText = JSON.stringify(messageText);
        }
      } catch {
        messageText = text;
      }
    }
    throw new Error(messageText);
  }
  if (!response.body) {
    throw new Error("Chat API did not return a stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\n\n/);
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      if (!block.trim()) continue;
      const { eventName, data } = parseSseBlock(block);

      if (eventName === "status") {
        onStatus?.(STATUS_LABELS[data?.step] || "Processing clinical context...");
      }
      if (eventName === "draft_ready") {
        onStatus?.("Patient draft collected...");
        onDraft?.(data);
      }
      if (eventName === "missing_check") {
        onStatus?.("Checking required clinical fields...");
      }
      if (eventName === "recommendation_ready") {
        onStatus?.("Recommendation bundle ready...");
        onRecommendation?.(data);
      }
      if (eventName === "verification_ready") {
        onStatus?.("Evidence bundle verified...");
        onVerification?.(data);
      }
      if (eventName === "answer_delta" && data?.content) {
        onAnswerDelta?.(data.content);
      }
      if (eventName === "done") {
        donePayload = data;
      }
      if (eventName === "error") {
        throw new Error(data?.message || "Streaming chat failed");
      }
    }
  }

  onDone?.(donePayload);
  return donePayload;
}
