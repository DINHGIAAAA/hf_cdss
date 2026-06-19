import { useCallback, useEffect, useState } from "react";

import { chatApi } from "@shared/api/chat.js";
import { buildPatient } from "../utils";
import { STORAGE_KEY } from "./constants.js";
import { mapBackendMessages } from "./patientPayload.js";

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
  };
}
