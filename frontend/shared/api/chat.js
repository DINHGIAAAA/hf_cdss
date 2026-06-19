import { apiGet } from "./client.js";

export const chatApi = {
  getHistory: (conversationId) =>
    apiGet(`/chat/${encodeURIComponent(conversationId)}/history`),
};
