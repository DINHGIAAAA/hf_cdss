import { useCallback, useEffect, useState } from "react";

import { chatApi } from "@shared/api/chat.js";
import { buildPatient } from "../utils";
import { STORAGE_KEY } from "./constants.js";
import { mapBackendMessages } from "./patientPayload.js";

const DEMO_CONVERSATION_URL = "/demo/demo_chat_conversation.json";

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

  const syncConversationFromServer = useCallback(async (conversationId) => {
    if (!conversationId) return;
    try {
      const history = await chatApi.getHistory(conversationId);
      if (!history?.messages?.length) return;

      setConversations((items) =>
        items.map((item) => {
          if (item.id !== conversationId) return item;
          return {
            ...item,
            messages: mapBackendMessages(history.messages),
            draft: history.patient_draft
              ? { patient: history.patient_draft.patient, ...history.patient_draft }
              : item.draft,
            updatedAt: new Date().toISOString(),
          };
        }),
      );
    } catch {
      // Keep local cache when backend history is unavailable.
    }
  }, []);

  const selectConversation = useCallback((conversationId) => {
    setActiveId(conversationId);
  }, []);

  const createConversation = useCallback((form, patientId, conversationName) => {
    const patient = buildPatient(form, patientId);
    const conversation = {
      id: patientId,
      name: conversationName,
      patient,
      attachments: [],
      messages: [
        {
          id: `${patientId}-welcome`,
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

  const loadDemoConversation = useCallback(async () => {
    const response = await fetch(DEMO_CONVERSATION_URL);
    if (!response.ok) {
      throw new Error("Demo conversation file not found");
    }
    const seeded = await response.json();
    const demo = Array.isArray(seeded) ? seeded[0] : seeded;
    if (!demo?.id) {
      throw new Error("Invalid demo conversation");
    }
    setConversations((items) => [demo, ...items.filter((item) => item.id !== demo.id)]);
    setActiveId(demo.id);
    return demo;
  }, []);

  const deleteConversation = useCallback((conversationId) => {
    setConversations((items) => {
      const next = items.filter((item) => item.id !== conversationId);
      setActiveId((current) => {
        if (current !== conversationId) return current;
        return next[0]?.id || null;
      });
      return next;
    });
  }, []);

  const clearConversation = useCallback((conversationId) => {
    setConversations((items) =>
      items.map((item) => {
        if (item.id !== conversationId) return item;
        const name =
          item.draft?.patient?.patient_identity?.full_name ||
          item.patient?.patient_identity?.full_name ||
          item.name ||
          "patient";
        return {
          ...item,
          attachments: [],
          messages: [
            {
              id: `${conversationId}-welcome-${Date.now()}`,
              role: "assistant",
              content: `Patient ${name} is ready. Ask the clinical question and attach notes if needed.`,
            },
          ],
          recommendation: null,
          verification: null,
          updatedAt: new Date().toISOString(),
        };
      }),
    );
  }, []);

  useEffect(() => {
    if (activeId) {
      syncConversationFromServer(activeId);
    }
  }, [activeId, syncConversationFromServer]);

  return {
    conversations,
    activeId,
    selectConversation,
    patchConversation,
    updateActive,
    createConversation,
    loadDemoConversation,
    deleteConversation,
    clearConversation,
  };
}
