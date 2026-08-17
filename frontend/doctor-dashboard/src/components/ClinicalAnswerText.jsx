import { useAuiState } from "@assistant-ui/react";

import { ClinicalStructuredAnswer } from "@/components/ClinicalAnswerTables";
import { DosePlanDisplay } from "@/components/DosePlanDisplay";
import { ValueConflictInline } from "@/components/ValueConflictInline";
import { MarkdownText } from "@/components/markdown-text";
import { Button } from "@/components/ui/button";
import { useClinicalConversation } from "@/context/ClinicalConversationContext.jsx";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { useConversations } from "@/conversations/ConversationsContext.jsx";
import {
  shouldShowDosePlans,
  shouldShowStructuredRecommendation,
} from "@/lib/clinicalIntent.js";

// Create a simple event for triggering confirmation
export const confirmationTrigger = {
  listeners: new Set(),
  trigger(action, pendingPatient) {
    this.listeners.forEach((cb) => cb(action, pendingPatient));
  },
  subscribe(cb) {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  },
};

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
  const { recommendation, verification, clinicalState, onOpenEvidencePanel } =
    useClinicalConversation();
  const { patchConversation, active } = useConversations();
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const answerText = useAuiState(messagePlainText);
  const isLastAssistant = useAuiState((s) => {
    const index = s.message.index;
    return s.message.role === "assistant" && index === s.thread.messages.length - 1;
  });

  const conflicts = active?.conflicts;
  const conversationId = active?.id;

  const handleConfirmConflict = () => {
    console.log("Confirm clicked!", { conversationId, conflicts, pendingConfirmation: active?.pendingConfirmation });
    if (!conversationId || !conflicts) {
      console.log("Early return: missing conversationId or conflicts");
      return;
    }
    // Get the pending patient from active state
    const pendingPatient = active?.pendingConfirmation;
    console.log("Triggering confirm with pendingPatient:", !!pendingPatient);
    // Trigger confirmation event with pending patient
    confirmationTrigger.trigger("confirm", pendingPatient);
  };

  const handleCancelConflict = () => {
    console.log("Cancel clicked!", { conversationId });
    if (!conversationId) return;
    // Clear conflicts and show cancel message
    patchConversation(conversationId, { conflicts: null, pendingConfirmation: null });
    // Trigger cancel event
    confirmationTrigger.trigger("cancel", null);
  };

  const trimmed = (answerText || "").trim();
  const hasRecommendation = Boolean(recommendation?.recommendations?.length);
  const evidenceCount = verification?.context?.evidence_chunks?.length || 0;
  const showDosePlans =
    !isRunning &&
    isLastAssistant &&
    shouldShowDosePlans(clinicalState) &&
    recommendation?.dose_plans?.length > 0;
  const showStructured =
    !isRunning &&
    isLastAssistant &&
    shouldShowStructuredRecommendation(clinicalState, recommendation);
  const focusClassIds = (clinicalState?.focus_medication_classes || [])
    .map((c) => String(c || "").toLowerCase())
    .filter(Boolean);

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
      {showDosePlans ? (
        <DosePlanDisplay
          dosePlans={recommendation.dose_plans}
          version={recommendation.dose_rules_version}
        />
      ) : null}
      {showStructured ? (
        <ClinicalStructuredAnswer
          recommendation={recommendation}
          verification={verification}
          focusClassIds={focusClassIds}
        />
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
      {conflicts && conflicts.length > 0 && isLastAssistant ? (
        <ValueConflictInline
          conflicts={conflicts}
          onConfirm={handleConfirmConflict}
          onCancel={handleCancelConflict}
        />
      ) : null}
    </div>
  );
}
