import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleImageAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  useExternalStoreRuntime,
} from "@assistant-ui/react";

import { streamClinicalChat } from "@/lib/clinicalChatStream";
import { readClinicalFiles } from "@/utils";

const WELCOME_SUGGESTIONS = {
  vi: [
    "Đánh giá GDMT hiện tại và còn thiếu gì",
    "Có nên tiếp tục MRA với eGFR 24 và K+ 5.7?",
    "Khuyến nghị titration beta-blocker an toàn",
    "Tương tác thuốc và chống chỉ định cần lưu ý",
  ],
  en: [
    "Review current GDMT and identify gaps",
    "Should we continue MRA with eGFR 24 and K+ 5.7?",
    "Safe beta-blocker titration recommendations",
    "Drug interactions and contraindications to watch",
  ],
};

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
  language,
  patchConversation,
  updateActive,
  onStreamStatus,
  onError,
  children,
}) {
  const [isRunning, setIsRunning] = useState(false);
  const abortRef = useRef(null);
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
        createClinicalAttachmentAdapter(() => active, updateAttachments),
        new SimpleImageAttachmentAdapter(),
        new SimpleTextAttachmentAdapter(),
      ]),
    [active, updateAttachments],
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

  const onNew = useCallback(
    async (message) => {
      if (!active) return;
      const text = extractText(message);
      if (!text) return;

      const conversationId = active.id;
      const userId = `${conversationId}-user-${Date.now()}`;
      const assistantId = `${conversationId}-assistant-${Date.now()}`;
      const controller = new AbortController();
      abortRef.current = controller;

      patchConversation(conversationId, (current) => ({
        messages: [
          ...(current.messages || []),
          { id: userId, role: "user", content: text },
          { id: assistantId, role: "assistant", content: "" },
        ],
      }));
      setIsRunning(true);
      onStreamStatus?.("Preparing clinical stream...");
      onError?.("");

      try {
        await streamClinicalChat({
          message: text,
          active,
          language,
          signal: controller.signal,
          onStatus: onStreamStatus,
          onDraft: (data) => patchConversation(conversationId, () => ({ draft: data })),
          onRecommendation: (data) => patchConversation(conversationId, () => ({ recommendation: data })),
          onVerification: (data) => patchConversation(conversationId, () => ({ verification: data })),
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
          onDone: (donePayload) => {
            if (!donePayload) return;
            patchConversation(conversationId, (current) => {
              const updated = [...(current.messages || [])];
              if (donePayload.assistant_message?.content) {
                updated[updated.length - 1] = {
                  id: donePayload.assistant_message.message_id || assistantId,
                  role: "assistant",
                  content: donePayload.assistant_message.content,
                };
              }
              return {
                draft: donePayload.patient_draft,
                recommendation: donePayload.recommendation,
                verification: donePayload.verification,
                messages: updated,
              };
            });
          },
        });
      } catch (err) {
        if (err.name === "AbortError") return;
        const content = `API error: ${err.message}`;
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
        onStreamStatus?.("");
        abortRef.current = null;
      }
    },
    [active, language, onError, onStreamStatus, patchConversation],
  );

  const onCancel = useCallback(async () => {
    abortRef.current?.abort();
    setIsRunning(false);
    onStreamStatus?.("");
  }, [onStreamStatus]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const suggestions = useMemo(
    () =>
      (messages.length <= 1 ? WELCOME_SUGGESTIONS[language] || WELCOME_SUGGESTIONS.en : []).map((prompt) => ({
        prompt,
      })),
    [language, messages.length],
  );

  const runtime = useExternalStoreRuntime({
    isDisabled: !active,
    isRunning,
    messages,
    convertMessage,
    setMessages,
    suggestions,
    onNew,
    onCancel,
    adapters: {
      attachments: attachmentAdapter,
    },
  });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
