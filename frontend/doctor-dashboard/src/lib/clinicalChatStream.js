import { apiFetch, CHAT_STREAM_TIMEOUT_MS } from "@shared/api/client.js";
import { streamStatusLabel, translate } from "@/i18n/messages.js";
import { parseSseBlock } from "../utils";
import { compactPatientForRequest } from "../hooks/patientPayload.js";
import { STEP_ORDER } from "@/lib/clinicalStreamPipeline.js";

export async function streamClinicalChat({
  message,
  active,
  signal,
  onStatus,
  onProgress,
  onDraft,
  onRecommendation,
  onVerification,
  onAnswerDelta,
  onAnswerReplace,
  onDone,
  onConfirmationNeeded,
}) {
  // Build the request body, including confirmation parameters when present.
  const requestBody = {
    message,
    conversation_id: active.id,
    patient: compactPatientForRequest(active),
    clinical_attachments: active.attachments || [],
  };
  if (active.confirmation_action || active.confirmationAction) {
    requestBody.confirmation_action = active.confirmation_action || active.confirmationAction;
    console.log("Sending confirmation_action:", requestBody.confirmation_action);
  }
  if (active.pending_confirmation || active.pendingConfirmation) {
    requestBody.pending_confirmation = active.pending_confirmation || active.pendingConfirmation;
    console.log("Sending pending_confirmation:", !!requestBody.pending_confirmation);
  }
  if (active.multi_question_action || active.multiQuestionAction) {
    requestBody.multi_question_action =
      active.multi_question_action || active.multiQuestionAction;
  }
  const pendingMulti = active.pending_multi_question || active.pendingMultiQuestion;
  const looksLikeNewMultiQuestion = (text) => (String(text || "").match(/\?/g) || []).length > 1;
  // Send pending_multi_question when:
  // 1. multi_question_action is set (continue/stop response), OR
  // 2. not a new multi-question input (supplemental data or "yes" for continue).
  if (
    pendingMulti &&
    (requestBody.multi_question_action || !looksLikeNewMultiQuestion(message))
  ) {
    requestBody.pending_multi_question = pendingMulti;
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
    throw new Error(translate("chat.stream.noStream"));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload = null;

  const dispatchBlock = (block) => {
    if (!block.trim()) return;
    const { eventName, data } = parseSseBlock(block);

    if (eventName === "status") {
      const rawStep = data?.step;
      if (!rawStep) return;
      const step = STEP_ORDER.includes(rawStep) ? rawStep : rawStep === "processing" ? "received" : null;
      const phase = typeof data?.phase === "string" ? data.phase : null;
      const labelKey = phase && rawStep === "extracting_patient" ? phase : step;
      if (!labelKey && !step) return;
      onProgress?.({ step: step || rawStep, phase, label: streamStatusLabel(labelKey || step) });
      onStatus?.(streamStatusLabel(labelKey || step));
    }
    if (eventName === "draft_ready") {
      onProgress?.({ step: "draft_ready", label: streamStatusLabel("draft_ready") });
      onStatus?.(streamStatusLabel("draft_ready"));
      onConfirmationNeeded?.({
        isInitialDraft: data.is_initial_draft ?? false,
        conflicts: data.conflicts || [],
        missingCheck: data,
        pendingPatient: data.patient || null,
      });
      onDraft?.(data);
    }
    if (eventName === "missing_check") {
      onProgress?.({ step: "missing_check", label: streamStatusLabel("missing_check") });
      onStatus?.(streamStatusLabel("missing_check"));
    }
    if (eventName === "recommendation_ready") {
      onProgress?.({ step: "recommendation_ready", label: streamStatusLabel("recommendation_ready") });
      onStatus?.(streamStatusLabel("recommendation_ready"));
      onRecommendation?.(data);
    }
    if (eventName === "verification_ready") {
      onProgress?.({ step: "verification_ready", label: streamStatusLabel("verification_ready") });
      onStatus?.(streamStatusLabel("verification_ready"));
      onVerification?.(data);
    }
    if (eventName === "answer_delta" && typeof data?.content === "string" && data.content) {
      onAnswerDelta?.(data.content);
    }
    if (eventName === "answer_replace" && typeof data?.content === "string") {
      onAnswerReplace?.(data.content);
    }
    if (eventName === "done") {
      donePayload = typeof data === "object" && data !== null ? data : donePayload;
    }
    if (eventName === "error") {
      throw new Error(data?.message || translate("chat.stream.streamFailed"));
    }
  };

  while (true) {
    const { value, done: eof } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !eof });
    }
    if (eof) {
      buffer += decoder.decode(undefined, { stream: false });
      break;
    }
    const blocks = buffer.split(/\n\n/);
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      dispatchBlock(block);
    }
  }

  if (buffer.trim()) {
    dispatchBlock(buffer);
  }

  onDone?.(donePayload);
  return donePayload;
}

