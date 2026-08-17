import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { CheckCircle2, Circle, ChevronRight } from "lucide-react";
import { multiQuestionTrigger } from "./ClinicalChatRuntime.jsx";

function QuestionItem({ text, status, index }) {
  const isAnswered = status === "answered";
  const isCurrent = status === "current";
  const isRemaining = status === "remaining";

  return (
    <li className={cn(
      "flex items-start gap-2 rounded-md px-2.5 py-1.5 text-sm",
      isCurrent && "bg-primary/8 font-medium",
      isRemaining && "text-muted-foreground",
    )}>
      <span className="mt-0.5 shrink-0">
        {isAnswered ? (
          <CheckCircle2 className="size-4 text-green-600" aria-hidden />
        ) : (
          <Circle className={cn("size-4", isCurrent ? "fill-primary/20 text-primary" : "text-muted-foreground/50")} aria-hidden />
        )}
      </span>
      <span className="min-w-0 flex-1">
        {isCurrent && <span className="mr-1.5 text-xs text-muted-foreground">Q{index}: </span>}
        {isRemaining && <span className="mr-1.5 text-xs text-muted-foreground">Q{index}: </span>}
        <span className="text-wrap">{text}</span>
      </span>
    </li>
  );
}

export function PendingQuestionsBanner({ pendingMultiQuestion, onContinue, onStop, disabled }) {
  const { t } = useLanguage();

  if (!pendingMultiQuestion) return null;

  const answered = pendingMultiQuestion.answered_qs || [];
  const remaining = pendingMultiQuestion.remaining_qs || [];
  const currentQuestion = pendingMultiQuestion.current_question;
  const total = answered.length + remaining.length;

  if (total <= 1) return null;

  const allItems = [
    ...answered.map((q, i) => ({ text: q, status: "answered", index: i + 1 })),
    ...remaining.map((q, i) => ({
      text: q,
      status: i === 0 ? "current" : "remaining",
      index: answered.length + i + 1,
    })),
  ];

  const handleContinue = () => {
    multiQuestionTrigger.trigger("continue");
  };

  const handleStop = () => {
    multiQuestionTrigger.trigger("stop");
  };

  return (
    <div className="border-t border-[var(--color-rule)] bg-[var(--color-paper-2)] px-4 py-3">
      <div className="mx-auto max-w-3xl">
        {currentQuestion && (
          <div className="mb-2 rounded-md bg-primary/5 px-3 py-2">
            <p className="text-xs font-medium text-primary">
              {t("chat.multiQuestion.answering")}: {currentQuestion}
            </p>
          </div>
        )}
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-medium text-muted-foreground">
            {t("chat.multiQuestion.title", { count: total })}
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleStop}
              disabled={disabled}
              type="button"
            >
              {t("chat.multiQuestion.stop")}
            </Button>
            <Button
              size="sm"
              className="h-7 text-xs"
              onClick={handleContinue}
              disabled={disabled}
              type="button"
            >
              {t("chat.multiQuestion.continue")}
              <ChevronRight className="ml-0.5 size-3" aria-hidden />
            </Button>
          </div>
        </div>
        <ol className="space-y-0.5" aria-label="Pending questions">
          {allItems.map((item, i) => (
            <QuestionItem key={i} {...item} />
          ))}
        </ol>
      </div>
    </div>
  );
}
