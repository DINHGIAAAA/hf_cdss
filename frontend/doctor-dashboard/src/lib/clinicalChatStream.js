import { apiFetch } from "@shared/api/client.js";
import { streamStatusLabel, translate } from "@/i18n/messages.js";
import { parseSseBlock } from "../utils";
import { compactPatientForRequest } from "../hooks/patientPayload.js";

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
        onStatus?.(streamStatusLabel(language, data?.step));
      }
      if (eventName === "draft_ready") {
        onStatus?.(streamStatusLabel(language, "draft_ready"));
        onDraft?.(data);
      }
      if (eventName === "missing_check") {
        onStatus?.(streamStatusLabel(language, "missing_check"));
      }
      if (eventName === "recommendation_ready") {
        onStatus?.(streamStatusLabel(language, "recommendation_ready"));
        onRecommendation?.(data);
      }
      if (eventName === "verification_ready") {
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
