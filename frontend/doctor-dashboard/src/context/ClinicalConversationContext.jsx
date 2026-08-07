import { createContext, useContext } from "react";

export const ClinicalConversationContext = createContext({
  recommendation: null,
  verification: null,
  onOpenEvidencePanel: null,
});

export function useClinicalConversation() {
  return useContext(ClinicalConversationContext);
}
