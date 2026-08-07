import { createContext, useContext } from "react";

import { useConversations as useConversationsState } from "../hooks/useConversations.js";

const ConversationsContext = createContext(null);

export function ConversationsProvider({ children }) {
  const value = useConversationsState();
  return <ConversationsContext.Provider value={value}>{children}</ConversationsContext.Provider>;
}

export function useConversations() {
  const ctx = useContext(ConversationsContext);
  if (!ctx) {
    throw new Error("useConversations must be used within ConversationsProvider");
  }
  return ctx;
}

/**
 * Shape of a conversation object managed by ConversationsContext.
 * @typedef {Object} Conversation
 * @property {string} id
 * @property {string} name
 * @property {import("./types").Patient} [patient]
 * @property {Array} [attachments]
 * @property {Array<import("./types").Message>} messages
 * @property {import("./types").PatientDraft|null} draft
 * @property {import("./types").MissingCheck|null} lastMissingCheck
 * @property {boolean} isInitialDraft
 * @property {import("./types").PendingConfirmation|null} pendingConfirmation
 * @property {Array<import("./types").Conflict>|null} conflicts
 * @property {object|null} recommendation
 * @property {object|null} verification
 * @property {string} createdAt
 * @property {string} updatedAt
 */
