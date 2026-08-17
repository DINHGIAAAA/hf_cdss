import { useCallback, useEffect, useMemo, useState } from "react";

import { chatApi } from "@shared/api/chat.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { buildPatient } from "../utils";
import { STORAGE_KEY } from "./constants.js";
import { persistConversations } from "./conversationStorage.js";
import { mapBackendMessages } from "./patientPayload.js";

const DEMO_CONVERSATION_URL = "/demo/demo_chat_conversation.json";

export function useConversations() {
  const { isAuthenticated, bootstrapping } = useAuth();
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
    persistConversations(conversations);
  }, [conversations]);

  const patchConversation = useCallback((conversationId, patchOrUpdater) => {
    setConversations((items) =>
      items.map((item) => {
        if (item.id !== conversationId) return item;
        // Support both function updater and plain object
        const patch = typeof patchOrUpdater === "function"
          ? patchOrUpdater(item)
          : patchOrUpdater;
        return { ...item, ...patch, updatedAt: new Date().toISOString() };
      }),
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
            lastMissingCheck: history.patient_draft ? (history.patient_draft.last_missing_check || null) : null,
            isInitialDraft: history.patient_draft ? (history.patient_draft.is_initial_draft || false) : false,
            conflicts: history.patient_draft ? (history.patient_draft.conflicts || null) : null,
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
      lastMissingCheck: null,
      isInitialDraft: true,
      pendingConfirmation: null,
      conflicts: null,
      recommendation: null,
      verification: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    setConversations((items) => [conversation, ...items.filter((item) => item.id !== patientId)]);
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

    // The demo file always ships the same fixed id, so opening it a second
    // time is meant to be idempotent — reopen whatever conversation is
    // already there (keeping any chat done in it) instead of overwriting it
    // with a fresh copy from disk every time this is clicked.
    const existing = conversations.find((item) => item.id === demo.id);
    if (existing) {
      setActiveId(existing.id);
      return existing;
    }

    setConversations((items) => [demo, ...items]);
    setActiveId(demo.id);
    return demo;
  }, [conversations]);

  const renameConversation = useCallback((conversationId, newName) => {
    if (!newName?.trim()) return;
    setConversations((items) =>
      items.map((item) =>
        item.id === conversationId
          ? { ...item, name: newName.trim(), updatedAt: new Date().toISOString() }
          : item,
      ),
    );
  }, []);

  const copyConversation = useCallback(async (conversationId) => {
    const conv = conversations.find((c) => c.id === conversationId);
    if (!conv) return;

    const lines = [
      `# ${conv.name || "Conversation"}`,
      "",
      ...(conv.messages || []).map((msg) => {
        const role = msg.role === "assistant" ? "Assistant" : "User";
        return `**${role}:**\n${msg.content || ""}`;
      }),
    ];

    await navigator.clipboard.writeText(lines.join("\n\n"));
    return conv.name || "Conversation";
  }, [conversations]);

  const deleteConversation = useCallback((conversationId) => {
    setConversations((items) => {
      const next = items.filter((item) => item.id !== conversationId);
      setActiveId((current) => {
        if (current !== conversationId) return current;
        return next[0]?.id || null;
      });
      return next;
    });
    // Local-only removal previously left the server's copy intact, so
    // reopening a conversation that reuses the same id (e.g. the demo case,
    // which always has a fixed id) resurrected the "deleted" history via
    // syncConversationFromServer. Best-effort — the local list is already
    // the source of truth for what the user sees.
    chatApi.deleteHistory(conversationId).catch(() => {});
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
          draft: null,
          lastMissingCheck: null,
          isInitialDraft: true,
          pendingConfirmation: null,
          conflicts: null,
          recommendation: null,
          verification: null,
          updatedAt: new Date().toISOString(),
        };
      }),
    );
  }, []);

  useEffect(() => {
    if (bootstrapping || !isAuthenticated || !activeId) {
      return;
    }
    syncConversationFromServer(activeId);
  }, [activeId, syncConversationFromServer, bootstrapping, isAuthenticated]);

  // Derive the active conversation from conversations + activeId
  const active = useMemo(
    () => conversations.find((c) => c.id === activeId) || null,
    [conversations, activeId]
  );

  return {
    conversations,
    activeId,
    active,
    selectConversation,
    patchConversation,
    updateActive,
    createConversation,
    loadDemoConversation,
    deleteConversation,
    renameConversation,
    copyConversation,
    clearConversation,
  };
}
