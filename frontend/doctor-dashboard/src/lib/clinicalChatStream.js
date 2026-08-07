import { apiFetch, CHAT_STREAM_TIMEOUT_MS } from "@shared/api/client.js";
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
  onConfirmationNeeded,
}) {
  // Build the request body, including confirmation parameters when present.
  const requestBody = {
    message,
    conversation_id: active.id,
    patient: compactPatientForRequest(active),
    clinical_attachments: active.attachments || [],
    language,
  };
  if (active.confirmation_action) {
    requestBody.confirmation_action = active.confirmation_action;
  }
  if (active.pending_confirmation) {
    requestBody.pending_confirmation = active.pending_confirmation;
  }

  const response = await apiFetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
    signal,
    timeoutMs: CHAT_STREAM_TIMEOUT_MS,
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
        // Also emit confirmation data so the caller can store it on the conversation.
        onConfirmationNeeded?.({
          isInitialDraft: data.is_initial_draft ?? false,
          conflicts: data.conflicts || [],
          missingCheck: data,
          pendingPatient: data.patient || null,
        });
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
