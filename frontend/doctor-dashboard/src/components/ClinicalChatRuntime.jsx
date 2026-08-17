import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleImageAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  useExternalStoreRuntime,
} from "@assistant-ui/react";

import { streamClinicalChat } from "@/lib/clinicalChatStream";
import { translate } from "@/i18n/messages.js";
import { assistantTextFromChatDone, readClinicalFiles } from "@/utils";
import { confirmationTrigger } from "./ClinicalAnswerText.jsx";

function extractText(message) {
  const part = message.content?.find?.((item) => item.type === "text");
  return part?.text?.trim() || "";
}

function convertMessage(message) {
  return {
    id: message.id,
    role: message.role,
    content: [{ type: "text", text: message.content || "" }],
  };
}

function resolveReloadUserTurn(messages, parentId) {
  if (!messages?.length) return null;

  if (parentId) {
    const byId = messages.findIndex((m) => m.id === parentId);
    if (byId >= 0) {
      if (messages[byId].role === "user") {
        return { userIndex: byId, text: messages[byId].content || "" };
      }
      for (let i = byId - 1; i >= 0; i -= 1) {
        if (messages[i].role === "user") {
          return { userIndex: i, text: messages[i].content || "" };
        }
      }
    }
  }

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === "user") {
      return { userIndex: i, text: messages[i].content || "" };
    }
  }
  return null;
}

function createClinicalAttachmentAdapter(getConversation, updateAttachments) {
  return {
    accept: ".txt,.csv,.json,.md,.xml,.html,image/*,.pdf",
    async add({ file }) {
      const parsed = await readClinicalFiles([file]);
      const current = getConversation();
      updateAttachments([...(current?.attachments || []), ...parsed]);
      return {
        id: `${file.name}-${Date.now()}`,
        type: file.type.startsWith("image/") ? "image" : "document",
        name: file.name,
        contentType: file.type,
        file,
        status: { type: "requires-action", reason: "composer-send" },
      };
    },
    async remove() {},
    async send(attachment) {
      return {
        ...attachment,
        status: { type: "complete" },
        content: [],
      };
    },
  };
}

export function ClinicalChatRuntimeProvider({
  active,
  patchConversation,
  updateActive,
  onStreamStatus,
  onStreamProgress,
  onError,
  children,
}) {
  // Called when a needs_confirmation response arrives from the backend.
  const handleConfirmationNeeded = useCallback(
    ({ isInitialDraft, conflicts, missingCheck, pendingPatient }) => {
      if (!active) return;
      patchConversation(active.id, () => ({
        isInitialDraft,
        conflicts,
        lastMissingCheck: missingCheck || null,
        pendingConfirmation: pendingPatient || null,
        confirmationAction: null, // clear any stale action
      }));
    },
    [active, patchConversation],
  );
  const [isRunning, setIsRunning] = useState(false);
  const abortRef = useRef(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  const messages = active?.messages || [];

  const updateAttachments = useCallback(
    (attachments) => {
      if (!active) return;
      updateActive({ attachments });
    },
    [active, updateActive],
  );

  const attachmentAdapter = useMemo(
    () =>
      new CompositeAttachmentAdapter([
        createClinicalAttachmentAdapter(() => activeRef.current, updateAttachments),
        new SimpleImageAttachmentAdapter(),
        new SimpleTextAttachmentAdapter(),
      ]),
    [updateAttachments],
  );

  const setMessages = useCallback(
    (nextMessages) => {
      if (!active) return;
      patchConversation(active.id, () => ({
        messages: nextMessages.map((message) => ({
          id: message.id,
          role: message.role,
          content: typeof message.content === "string" ? message.content : extractText(message),
        })),
      }));
    },
    [active, patchConversation],
  );

  const runClinicalStream = useCallback(
    async ({ conversationId, userText, assistantId, confirmationAction, pendingConfirmation }) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setIsRunning(true);
      const preparing = { step: "preparing", label: translate("chat.stream.preparing") };
      onStreamProgress?.(preparing);
      onStreamStatus?.(preparing.label);
      onError?.("");

      // Build active object with explicit confirmation data if provided
      // Backend expects confirmation_action (snake_case)
      const activeWithConfirmation = confirmationAction
        ? { ...activeRef.current, confirmation_action: confirmationAction, pending_confirmation: pendingConfirmation }
        : activeRef.current;

      try {
        await streamClinicalChat({
          message: userText,
          active: activeWithConfirmation,
          signal: controller.signal,
          onStatus: onStreamStatus,
          onProgress: onStreamProgress,
          onDraft: (data) => patchConversation(conversationId, () => ({ draft: data })),
          onRecommendation: (data) => patchConversation(conversationId, () => ({ recommendation: data })),
          onVerification: (data) => patchConversation(conversationId, () => ({ verification: data })),
          onConfirmationNeeded: handleConfirmationNeeded,
          onAnswerDelta: (delta) => {
            patchConversation(conversationId, (current) => {
              const updated = [...(current.messages || [])];
              const last = updated[updated.length - 1];
              if (!last || last.role !== "assistant") return { messages: updated };
              updated[updated.length - 1] = {
                ...last,
                content: `${last.content || ""}${delta}`,
              };
              return { messages: updated };
            });
          },
          onAnswerReplace: (content) => {
            patchConversation(conversationId, (current) => {
              const updated = [...(current.messages || [])];
              const last = updated[updated.length - 1];
              if (!last || last.role !== "assistant") return { messages: updated };
              updated[updated.length - 1] = { ...last, content };
              return { messages: updated };
            });
          },
          onDone: (donePayload) => {
            if (!donePayload || typeof donePayload !== "object") return;
            const assistantContent = assistantTextFromChatDone(donePayload);
            patchConversation(conversationId, (current) => {
              const updated = [...(current.messages || [])];
              if (assistantContent.trim()) {
                updated[updated.length - 1] = {
                  id: donePayload.assistant_message?.message_id || assistantId,
                  role: "assistant",
                  content: assistantContent,
                };
              }
              const isNeedsConfirmation = donePayload.status === "needs_confirmation";
              // For needs_confirmation, preserve conflicts/pendingConfirmation from prior callback
              // to avoid race conditions between onConfirmationNeeded and onDone
              const preservedConflicts = isNeedsConfirmation
                ? (donePayload.conflicts || current.conflicts)
                : donePayload.conflicts;
              const preservedPendingConfirmation = isNeedsConfirmation
                ? (donePayload.patient_draft?.patient || current.pendingConfirmation)
                : null;
              return {
                draft: donePayload.patient_draft,
                recommendation: donePayload.recommendation,
                verification: donePayload.verification,
                messages: updated,
                pendingConfirmation: preservedPendingConfirmation,
                confirmationAction: null,
                conflicts: preservedConflicts,
                pendingMultiQuestion:
                  donePayload.pending_multi_question ?? current.pendingMultiQuestion ?? null,
                multiQuestionAction: null,
              };
            });
          },
        });
      } catch (err) {
        if (err.name === "AbortError") return;
        const content = translate("chat.stream.apiError", { message: err.message });
        onError?.(err.message);
        patchConversation(conversationId, (current) => {
          const updated = [...(current.messages || [])];
          if (updated[updated.length - 1]?.role === "assistant") {
            updated[updated.length - 1] = { ...updated[updated.length - 1], content };
          } else {
            updated.push({ id: `${conversationId}-error-${Date.now()}`, role: "assistant", content });
          }
          return { messages: updated };
        });
      } finally {
        setIsRunning(false);
        onStreamProgress?.(null);
        onStreamStatus?.("");
        abortRef.current = null;
      }
    },
    [onError, onStreamStatus, onStreamProgress, patchConversation, handleConfirmationNeeded],
  );

  // Handle confirmation trigger from ValueConflictInline buttons
  useEffect(() => {
    const unsubscribe = confirmationTrigger.subscribe((action, pendingPatient) => {
      if (!activeRef.current) return;
      const convId = activeRef.current.id;
      const assistantId = `${convId}-assistant-${Date.now()}`;
      const confirmationAction = action;
      const pendingConfirmation = pendingPatient || activeRef.current.pendingConfirmation;

      // Clear conflicts immediately - we'll show a simple confirmation message
      patchConversation(convId, {
        conflicts: null,
        pendingConfirmation: null,
      });

      // Add confirmation message with simple confirmation
      patchConversation(convId, (current) => ({
        messages: [
          ...(current.messages || []),
          { id: `${convId}-user-confirm-${Date.now()}`, role: "user", content: action === "confirm" ? "yes" : "no" },
          { id: assistantId, role: "assistant", content: "" },
        ],
        confirmationAction,
        pendingConfirmation,
      }));

      // Run the stream with explicit confirmation data
      runClinicalStream({
        conversationId: convId,
        userText: action === "confirm" ? "yes" : "no",
        assistantId,
        confirmationAction,
        pendingConfirmation,
      });
    });
    return unsubscribe;
  }, [patchConversation, runClinicalStream]);

  const onNew = useCallback(
    async (message) => {
      const current = activeRef.current;
      if (!current) return;
      const text = extractText(message);
      if (!text) return;

      const conversationId = current.id;
      const userId = `${conversationId}-user-${Date.now()}`;
      const assistantId = `${conversationId}-assistant-${Date.now()}`;

      const continuePattern = /^(yes|y|continue|ok|okay)$/i;
      const isMultiContinue =
        current.pendingMultiQuestion?.remaining_qs?.length > 0 &&
        continuePattern.test(text.trim());

      if (isMultiContinue) {
        patchConversation(conversationId, (prev) => ({
          messages: [
            ...(prev.messages || []),
            { id: userId, role: "user", content: text },
            { id: assistantId, role: "assistant", content: "" },
          ],
          multiQuestionAction: "continue",
        }));
        await runClinicalStream({ conversationId, userText: text, assistantId });
        patchConversation(conversationId, () => ({ multiQuestionAction: null }));
        return;
      }

      patchConversation(conversationId, (prev) => ({
        messages: [
          ...(prev.messages || []),
          { id: userId, role: "user", content: text },
          { id: assistantId, role: "assistant", content: "" },
        ],
      }));

      await runClinicalStream({ conversationId, userText: text, assistantId });
    },
    [patchConversation, runClinicalStream],
  );

  const onReload = useCallback(
    async (parentId) => {
      const current = activeRef.current;
      if (!current) return;

      const turn = resolveReloadUserTurn(current.messages || [], parentId);
      if (!turn?.text?.trim()) return;

      const conversationId = current.id;
      const msgs = current.messages || [];
      const kept = msgs.slice(0, turn.userIndex + 1);
      const priorAssistant = msgs[turn.userIndex + 1];
      const assistantId =
        priorAssistant?.role === "assistant"
          ? priorAssistant.id
          : `${conversationId}-assistant-${Date.now()}`;

      patchConversation(conversationId, () => ({
        messages: [...kept, { id: assistantId, role: "assistant", content: "" }],
        recommendation: null,
        verification: null,
      }));

      await runClinicalStream({
        conversationId,
        userText: turn.text.trim(),
        assistantId,
      });
    },
    [patchConversation, runClinicalStream],
  );

  const onCancel = useCallback(async () => {
    abortRef.current?.abort();
    setIsRunning(false);
    onStreamStatus?.("");
    onStreamProgress?.(null);
  }, [onStreamStatus, onStreamProgress]);

  const suggestions = useMemo(() => {
    const prompts = translate("chat.suggestions");
    const list = Array.isArray(prompts) ? prompts : [];
    return (messages.length <= 1 ? list : []).map((prompt) => ({ prompt }));
  }, [messages.length]);

  const runtime = useExternalStoreRuntime({
    isDisabled: !active,
    isRunning,
    messages,
    convertMessage,
    setMessages,
    suggestions,
    onNew,
    onReload,
    onCancel,
    adapters: {
      attachments: attachmentAdapter,
    },
  });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
