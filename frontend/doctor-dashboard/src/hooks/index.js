import { useCallback, useEffect, useState } from "react";
import { buildPatient, makePatientId, parseSseBlock, slugify } from "../utils";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";
const API_KEY_HEADER = import.meta.env.VITE_API_KEY_HEADER ?? "x-api-key";
const STORAGE_KEY = "hf_cdss_conversations_v2";

function apiHeaders(extra = {}) {
  return API_KEY ? { ...extra, [API_KEY_HEADER]: API_KEY } : extra;
}

export function useConversations() {
  const [conversations, setConversations] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    } catch {
      return [];
    }
  });
  const [activeId, setActiveId] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]")[0]?.id || null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  }, [conversations]);

  const patchConversation = useCallback((conversationId, updater) => {
    setConversations((items) =>
      items.map((item) =>
        item.id === conversationId
          ? { ...item, ...updater(item), updatedAt: new Date().toISOString() }
          : item,
      ),
    );
  }, []);

  const updateActive = useCallback(
    (patch) => {
      setConversations((items) =>
        items.map((item) =>
          item.id === activeId ? { ...item, ...patch, updatedAt: new Date().toISOString() } : item,
        ),
      );
    },
    [activeId],
  );

  const createConversation = useCallback((form, patientId, conversationName) => {
    const patient = buildPatient(form, patientId);
    const conversation = {
      id: patientId,
      name: conversationName,
      patient,
      attachments: [],
      messages: [
        {
          role: "assistant",
          content: `Patient ${form.fullName} is ready. Ask the clinical question and attach notes if needed.`,
        },
      ],
      draft: null,
      recommendation: null,
      verification: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    setConversations((items) => [conversation, ...items]);
    setActiveId(patientId);
  }, []);

  return { conversations, activeId, setActiveId, patchConversation, updateActive, createConversation };
}

export function useChat({ activeId, active, patchConversation }) {
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
      const assistantPlaceholder = { role: "assistant", content: "" };

      setLoading(true);
      setStreamStatus("Preparing clinical stream...");
      setError("");
      setChatInput("");

      patchConversation(conversationId, (current) => ({
        messages: [...(current.messages || []), { role: "user", content: message }, assistantPlaceholder],
      }));

      try {
        const response = await fetch(`${API_BASE_URL}/chat/stream`, {
          method: "POST",
          headers: apiHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            message,
            conversation_id: conversationId,
            patient: active.draft?.patient || active.patient,
            clinical_attachments: active.attachments || [],
            language: "vi",
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
            messages[messages.length - 1] = { role: "assistant", content };
          } else {
            messages.push({ role: "assistant", content });
          }
          return { messages };
        });
      } finally {
        setLoading(false);
        setStreamStatus("");
      }
    },
    [chatInput, active, loading, patchConversation],
  );

  return { chatInput, setChatInput, loading, streamStatus, error, setError, submitChat };
}

export function useApiHealth() {
  const [health, setHealth] = useState("checking");
  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((res) => setHealth(res.ok ? "ok" : "degraded"))
      .catch(() => setHealth("down"));
  }, []);
  return health;
}
