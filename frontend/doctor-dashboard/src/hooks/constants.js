export const STORAGE_KEY = "hf_cdss_conversations_v2";
export const LANGUAGE_STORAGE_KEY = "hf_cdss_chat_language";

export const DEFAULT_CHAT_LANGUAGE = import.meta.env.VITE_CHAT_LANGUAGE ?? "vi";

export const CHAT_LANGUAGES = [
  { code: "vi", label: "VI", title: "Tiếng Việt" },
  { code: "en", label: "EN", title: "English" },
];
