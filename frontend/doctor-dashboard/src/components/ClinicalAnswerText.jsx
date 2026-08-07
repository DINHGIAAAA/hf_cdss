import { useAuiState } from "@assistant-ui/react";

import { MarkdownText } from "@/components/markdown-text";
import { Button } from "@/components/ui/button";
import { useClinicalConversation } from "@/context/ClinicalConversationContext.jsx";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";

function messagePlainText(state) {
  const parts = state.message.parts;
  if (Array.isArray(parts)) {
    return parts
      .filter((part) => part.type === "text")
      .map((part) => part.text || "")
      .join("");
  }
  const content = state.message.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter((part) => part?.type === "text")
      .map((part) => part.text || "")
      .join("");
  }
  return "";
}

export function ClinicalAnswerText() {
  const { t } = useLanguage();
  const { recommendation, verification, onOpenEvidencePanel } = useClinicalConversation();
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const answerText = useAuiState(messagePlainText);
  const isLastAssistant = useAuiState((s) => {
    const index = s.message.index;
    return s.message.role === "assistant" && index === s.thread.messages.length - 1;
  });

  const trimmed = (answerText || "").trim();
  const hasRecommendation = Boolean(recommendation?.recommendations?.length);
  const evidenceCount = verification?.context?.evidence_chunks?.length || 0;

  if (!isRunning && isLastAssistant && !trimmed && !hasRecommendation) {
    return (
      <p className="text-sm text-muted-foreground">{t("clinicalAnswer.emptyResponse")}</p>
    );
  }

  return (
    <div className="space-y-3">
      {trimmed ? <MarkdownText /> : null}
      {!isRunning && isLastAssistant && hasRecommendation && !trimmed ? (
        <p className="text-sm text-muted-foreground">{t("clinicalAnswer.seeClinicalPanel")}</p>
      ) : null}
      {!isRunning && isLastAssistant && evidenceCount > 0 && onOpenEvidencePanel ? (
        <Button
          className="h-8 rounded-full px-3 text-xs"
          onClick={() => onOpenEvidencePanel()}
          type="button"
          variant="outline"
        >
          {t("clinicalAnswer.evidenceCount", { count: evidenceCount })}
        </Button>
      ) : null}
    </div>
  );
}
