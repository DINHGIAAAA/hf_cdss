import { PanelLeft } from "lucide-react";

import { Thread } from "@/components/thread";
import { LanguageToggle } from "@/components/LanguageToggle";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { patientSummary } from "@/utils";

const WELCOME_COPY = {
  vi: {
    title: "Bạn cần hỗ trợ gì cho ca bệnh này?",
    body: "Hỏi về GDMT, an toàn thuốc, titration hoặc bằng chứng lâm sàng.",
  },
  en: {
    title: "How can I help with this case?",
    body: "Ask about GDMT, medication safety, titration, or clinical evidence.",
  },
};

function ClinicalWelcome({ language }) {
  const copy = WELCOME_COPY[language] || WELCOME_COPY.en;
  return (
    <div className="aui-thread-welcome-root mb-6 flex flex-col items-center px-4 text-center">
      <h1 className="text-2xl font-semibold">{copy.title}</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{copy.body}</p>
    </div>
  );
}

export function ClinicalChatThread({
  active,
  language,
  languages,
  onLanguageChange,
  sidebarOpen,
  onToggleSidebar,
  streamStatus,
}) {
  const summary = patientSummary(active?.draft?.patient || active?.patient);

  return (
    <section aria-label="Clinical chat" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-3 sm:gap-3">
        <Button
          aria-label={sidebarOpen ? "Hide conversation sidebar" : "Show conversation sidebar"}
          className="shrink-0"
          onClick={onToggleSidebar}
          size="icon"
          type="button"
          variant="ghost"
        >
          <PanelLeft size={18} />
        </Button>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{active?.name || "HF CDSS"}</div>
          {summary && (
            <div className="truncate text-xs text-muted-foreground">
              {summary.name} · {summary.sex ?? "—"} · {summary.age ?? "—"}{" "}
              {language === "vi" ? "tuổi" : "y"}
            </div>
          )}
        </div>
        <div className="hidden shrink-0 md:block">
          <LanguageToggle language={language} languages={languages} onChange={onLanguageChange} variant="light" />
        </div>
      </header>

      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <Thread
          components={{
            Welcome: () => <ClinicalWelcome language={language} />,
          }}
        />
      </div>

      {streamStatus ? (
        <div className="shrink-0 border-t border-border px-4 py-2">
          <Badge className="w-full max-w-full justify-center truncate py-1.5" variant="secondary">
            {streamStatus}
          </Badge>
        </div>
      ) : null}
    </section>
  );
}
