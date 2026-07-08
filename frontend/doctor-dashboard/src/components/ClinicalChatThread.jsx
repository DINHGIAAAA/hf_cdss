import { PanelLeft } from "lucide-react";

import { Thread } from "@/components/thread";
import { LanguageToggle } from "@/components/LanguageToggle";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { patientSummary } from "@/utils";

function ClinicalWelcome() {
  const { t } = useLanguage();
  return (
    <div className="aui-thread-welcome-root mb-6 flex flex-col items-center px-4 text-center">
      <h1 className="text-2xl font-semibold">{t("chat.welcomeTitle")}</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{t("chat.welcomeBody")}</p>
    </div>
  );
}

export function ClinicalChatThread({
  active,
  sidebarOpen,
  onToggleSidebar,
  streamStatus,
}) {
  const { language, languages, setLanguage, t } = useLanguage();
  const summary = patientSummary(active?.draft?.patient || active?.patient);

  return (
    <section aria-label="Clinical chat" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-3 sm:gap-3">
        <Button
          aria-label={sidebarOpen ? t("chat.hideSidebar") : t("chat.showSidebar")}
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
              {summary.name} · {summary.sex ?? "—"} · {summary.age ?? "—"} {t("chat.ageUnit")}
            </div>
          )}
        </div>
        <div className="hidden shrink-0 md:block">
          <LanguageToggle language={language} languages={languages} onChange={setLanguage} variant="light" />
        </div>
      </header>

      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <Thread
          components={{
            Welcome: ClinicalWelcome,
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
