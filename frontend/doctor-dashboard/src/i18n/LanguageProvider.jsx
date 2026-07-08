import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { CHAT_LANGUAGES, DEFAULT_CHAT_LANGUAGE, LANGUAGE_STORAGE_KEY } from "../hooks/constants.js";
import { translate } from "./messages.js";

const LanguageContext = createContext(null);

function readStoredLanguage() {
  const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if (stored && CHAT_LANGUAGES.some((item) => item.code === stored)) {
    return stored;
  }
  return DEFAULT_CHAT_LANGUAGE;
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(readStoredLanguage);

  const setLanguage = useCallback((code) => {
    if (!CHAT_LANGUAGES.some((item) => item.code === code)) return;
    localStorage.setItem(LANGUAGE_STORAGE_KEY, code);
    setLanguageState(code);
  }, []);

  const t = useCallback((key, vars) => translate(language, key, vars), [language]);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      languages: CHAT_LANGUAGES,
      t,
    }),
    [language, setLanguage, t],
  );

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
