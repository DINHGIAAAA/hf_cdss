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
