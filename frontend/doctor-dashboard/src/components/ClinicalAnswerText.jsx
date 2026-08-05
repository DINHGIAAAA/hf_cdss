import { useAuiState } from "@assistant-ui/react";

import {
  ClinicalDoseTable,
  ClinicalStructuredAnswer,
} from "@/components/ClinicalAnswerTables";
import { MarkdownText } from "@/components/markdown-text";
import { useClinicalConversation } from "@/context/ClinicalConversationContext.jsx";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";

const FALLBACK_MARKERS = /safety fallback|dự phòng an toàn|安全备用|フォールバック/i;

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
  const { recommendation, verification } = useClinicalConversation();
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const answerText = useAuiState(messagePlainText);
  const isLastAssistant = useAuiState((s) => {
    const index = s.message.index;
    return s.message.role === "assistant" && index === s.thread.messages.length - 1;
  });

  const hasRecommendation = Boolean(recommendation?.recommendations?.length);
  const trimmed = (answerText || "").trim();
  const useStructuredView =
    !isRunning &&
    isLastAssistant &&
    hasRecommendation &&
    (!trimmed || FALLBACK_MARKERS.test(answerText));

  const showDoseWithMarkdown =
    !isRunning &&
    isLastAssistant &&
    hasRecommendation &&
    !useStructuredView &&
    trimmed &&
    (recommendation.medication_pathway?.length ?? 0) > 0;

  if (useStructuredView) {
    return (
      <ClinicalStructuredAnswer recommendation={recommendation} verification={verification} />
    );
  }

  if (showDoseWithMarkdown) {
    return (
      <div className="space-y-4">
        <MarkdownText />
        <ClinicalDoseTable recommendation={recommendation} />
      </div>
    );
  }

  if (!isRunning && isLastAssistant && !trimmed && !hasRecommendation) {
    return (
      <p className="text-sm text-muted-foreground">{t("clinicalAnswer.emptyResponse")}</p>
    );
  }

  return <MarkdownText />;
}
