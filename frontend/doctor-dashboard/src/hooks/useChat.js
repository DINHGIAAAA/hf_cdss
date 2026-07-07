import { useCallback, useState } from "react";

import { apiFetch } from "@shared/api/client.js";
import { parseSseBlock } from "../utils";
import { compactPatientForRequest } from "./patientPayload.js";

export function useChat({ active, patchConversation, language }) {
  const [chatInput, setChatInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState("");
  const [error, setError] = useState("");

  const submitChat = useCallback(
    async (event) => {
      event.preventDefault();
      const message = chatInput.trim();
      if (!message || !active || loading) return;

      const conversationId = active.id;
      const assistantPlaceholder = {
        id: `${conversationId}-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
      };

      setLoading(true);
      setStreamStatus("Preparing clinical stream...");
      setError("");
      setChatInput("");

      patchConversation(conversationId, (current) => ({
        messages: [
          ...(current.messages || []),
          { id: `${conversationId}-user-${Date.now()}`, role: "user", content: message },
          assistantPlaceholder,
        ],
      }));

      try {
        const response = await apiFetch("/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            conversation_id: conversationId,
            patient: compactPatientForRequest(active),
            clinical_attachments: active.attachments || [],
            language,
          }),
        });

        if (!response.ok) throw new Error(`Chat API returned ${response.status}`);
        if (!response.body) throw new Error("Chat API did not return a stream");

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
              const statusLabels = {
                received: "Opening streaming bundle...",
                extracting_patient: "Collecting patient draft...",
                building_recommendation: "Processing medication safety...",
                verifying_evidence: "Retrieving and validating evidence...",
                generating_answer: "Reasoning over the verified recommendation...",
              };
              setStreamStatus(statusLabels[data?.step] || "Processing clinical context...");
            }

            if (eventName === "draft_ready") {
              setStreamStatus("Patient draft collected...");
              patchConversation(conversationId, () => ({ draft: data }));
            }
            if (eventName === "missing_check") {
              setStreamStatus("Checking required clinical fields...");
            }
            if (eventName === "recommendation_ready") {
              setStreamStatus("Recommendation bundle ready...");
              patchConversation(conversationId, () => ({ recommendation: data }));
            }
            if (eventName === "verification_ready") {
              setStreamStatus("Evidence bundle verified...");
              patchConversation(conversationId, () => ({ verification: data }));
            }

            if (eventName === "answer_delta" && data?.content) {
              patchConversation(conversationId, (current) => {
                const messages = [...(current.messages || [])];
                const last = messages[messages.length - 1] || assistantPlaceholder;
                messages[messages.length - 1] = {
                  ...last,
                  role: "assistant",
                  content: `${last.content || ""}${data.content}`,
                };
                return { messages };
              });
            }

            if (eventName === "done") donePayload = data;
            if (eventName === "error") throw new Error(data?.message || "Streaming chat failed");
          }
        }

        if (donePayload) {
          patchConversation(conversationId, (current) => {
            const messages = [...(current.messages || [])];
            if (donePayload.assistant_message?.content) {
              messages[messages.length - 1] = {
                id: donePayload.assistant_message.message_id || messages[messages.length - 1]?.id,
                role: "assistant",
                content: donePayload.assistant_message.content,
              };
            }
            return {
              draft: donePayload.patient_draft,
              recommendation: donePayload.recommendation,
              verification: donePayload.verification,
              messages,
            };
          });
        }
      } catch (err) {
        const content = `API error: ${err.message}`;
        setError(err.message);
        patchConversation(conversationId, (current) => {
          const messages = [...(current.messages || [])];
          if (messages[messages.length - 1]?.role === "assistant") {
            messages[messages.length - 1] = { ...messages[messages.length - 1], role: "assistant", content };
          } else {
            messages.push({
              id: `${conversationId}-error-${Date.now()}`,
              role: "assistant",
              content,
            });
          }
          return { messages };
        });
      } finally {
        setLoading(false);
        setStreamStatus("");
      }
    },
    [chatInput, active, loading, patchConversation, language],
  );

  return { chatInput, setChatInput, loading, streamStatus, error, setError, submitChat };
}
