import { createContext, useCallback, useContext, useMemo } from "react";

import { translate } from "./messages.js";

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const t = useCallback((key, vars) => translate(key, vars), []);

  const value = useMemo(() => ({ t }), [t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return context;
}

export function useTranslation() {
  return useLanguage();
}
