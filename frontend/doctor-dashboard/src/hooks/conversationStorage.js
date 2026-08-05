import { STORAGE_KEY } from "./constants.js";

export const MAX_STORED_CONVERSATIONS = 25;

/** Drop bulky fields; panel evidence can be refetched from the API after login. */
export function stripConversationForStorage(conversation) {
  if (!conversation || typeof conversation !== "object") return conversation;

  const messages = (conversation.messages || []).map((message) => ({
    id: message.id,
    role: message.role,
    content:
      typeof message.content === "string" ? message.content.slice(0, 12_000) : message.content,
  }));

  const attachments = (conversation.attachments || []).map((file) => ({
    file_name: file.file_name,
    mime_type: file.mime_type,
    note: file.note,
  }));

  let verification = conversation.verification;
  if (verification?.context?.evidence_chunks?.length) {
    verification = {
      ...verification,
      context: {
        ...verification.context,
        evidence_chunks: verification.context.evidence_chunks.map((chunk) => ({
          chunk_id: chunk.chunk_id,
          document_id: chunk.document_id,
          source_type: chunk.source_type,
          section: chunk.section,
          score: chunk.score,
          text: typeof chunk.text === "string" ? chunk.text.slice(0, 900) : chunk.text,
          metadata: chunk.metadata,
          source_url: chunk.source_url,
          source_link: chunk.source_link,
          page: chunk.page,
        })),
      },
    };
  }

  return {
    id: conversation.id,
    name: conversation.name,
    patient: conversation.patient,
    draft: conversation.draft,
    recommendation: conversation.recommendation,
    verification,
    attachments,
    messages,
    createdAt: conversation.createdAt,
    updatedAt: conversation.updatedAt,
  };
}

export function persistConversations(conversations) {
  const payload = conversations
    .slice(-MAX_STORED_CONVERSATIONS)
    .map(stripConversationForStorage);

  const tryWrite = (items) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  };

  try {
    tryWrite(payload);
    return;
  } catch (error) {
    if (error?.name !== "QuotaExceededError") {
      console.warn("Persist conversations failed", error);
      return;
    }
  }

  for (const limit of [15, 10, 5, 1]) {
    try {
      tryWrite(payload.slice(-limit));
      return;
    } catch (error) {
      if (error?.name !== "QuotaExceededError") {
        console.warn("Persist conversations failed", error);
        return;
      }
    }
  }

  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
  console.warn("Persist conversations failed: localStorage quota exceeded after trimming");
}
