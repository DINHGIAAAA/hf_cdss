import { useCallback, useState } from "react";

import { CHAT_LANGUAGES, DEFAULT_CHAT_LANGUAGE, LANGUAGE_STORAGE_KEY } from "./constants.js";

function readStoredLanguage() {
  const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if (stored && CHAT_LANGUAGES.some((item) => item.code === stored)) {
    return stored;
  }
  return DEFAULT_CHAT_LANGUAGE;
}

export function useLanguage() {
  const [language, setLanguageState] = useState(readStoredLanguage);

  const setLanguage = useCallback((code) => {
    if (!CHAT_LANGUAGES.some((item) => item.code === code)) return;
    localStorage.setItem(LANGUAGE_STORAGE_KEY, code);
    setLanguageState(code);
  }, []);

  return { language, setLanguage, languages: CHAT_LANGUAGES };
}
