import { apiFetch } from "@shared/api/client.js";
import { streamStatusLabel, translate } from "@/i18n/messages.js";
import { parseSseBlock } from "../utils";
import { compactPatientForRequest } from "../hooks/patientPayload.js";
import { STEP_ORDER } from "@/lib/clinicalStreamPipeline.js";

export async function streamClinicalChat({
  message,
  active,
  language,
  signal,
  onStatus,
  onProgress,
  onDraft,
  onRecommendation,
  onVerification,
  onAnswerDelta,
  onDone,
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
    throw new Error(translate(language, "chat.stream.noStream"));
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
        const rawStep = data?.step;
        if (!rawStep) continue;
        const step = STEP_ORDER.includes(rawStep) ? rawStep : rawStep === "processing" ? "received" : null;
        if (!step) continue;
        onProgress?.({ step, label: streamStatusLabel(language, step) });
        onStatus?.(streamStatusLabel(language, step));
      }
      if (eventName === "draft_ready") {
        onProgress?.({ step: "draft_ready", label: streamStatusLabel(language, "draft_ready") });
        onStatus?.(streamStatusLabel(language, "draft_ready"));
        onDraft?.(data);
      }
      if (eventName === "missing_check") {
        onProgress?.({ step: "missing_check", label: streamStatusLabel(language, "missing_check") });
        onStatus?.(streamStatusLabel(language, "missing_check"));
      }
      if (eventName === "recommendation_ready") {
        onProgress?.({ step: "recommendation_ready", label: streamStatusLabel(language, "recommendation_ready") });
        onStatus?.(streamStatusLabel(language, "recommendation_ready"));
        onRecommendation?.(data);
      }
      if (eventName === "verification_ready") {
        onProgress?.({ step: "verification_ready", label: streamStatusLabel(language, "verification_ready") });
        onStatus?.(streamStatusLabel(language, "verification_ready"));
        onVerification?.(data);
      }
      if (eventName === "answer_delta" && data?.content) {
        onAnswerDelta?.(data.content);
      }
      if (eventName === "done") {
        donePayload = data;
      }
      if (eventName === "error") {
        throw new Error(data?.message || translate(language, "chat.stream.streamFailed"));
      }
    }
  }

  onDone?.(donePayload);
  return donePayload;
}
