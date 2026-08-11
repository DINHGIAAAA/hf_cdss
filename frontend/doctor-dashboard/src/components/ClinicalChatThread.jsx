import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Copy,
  Eraser,
  FileText,
  MoreVertical,
  PanelLeft,
  PanelRight,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";

import { Thread } from "@/components/thread";
import { ClinicalAnswerText } from "@/components/ClinicalAnswerText";
import { ClinicalStreamProgress } from "@/components/ClinicalStreamProgress";
import { ClinicalConversationContext } from "@/context/ClinicalConversationContext.jsx";
import { StreamProgressProvider } from "@/context/StreamProgressContext.jsx";
import { LanguageToggle } from "@/components/LanguageToggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { cn } from "@/lib/utils";
import { patientSummary } from "@/utils";

function ClinicalWelcome() {
  const { t } = useLanguage();
  return (
    <div className="aui-thread-welcome-root mb-8 flex flex-col items-center px-4 text-center">
      <div
        aria-hidden
        className="mb-4 flex size-12 items-center justify-center rounded-2xl border border-[var(--color-rule)] bg-[var(--color-paper-2)] text-primary shadow-sm"
      >
        <Activity className="size-6" strokeWidth={1.75} />
      </div>
      <h1 className="text-2xl font-semibold tracking-tight [font-family:var(--font-display)]">
        {t("chat.welcomeTitle")}
      </h1>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">{t("chat.welcomeBody")}</p>
    </div>
  );
}

function PanelSegmentButton({ active, children, className, onClick }) {
  return (
    <button
      className={cn(
        "inline-flex h-7 cursor-pointer items-center justify-center gap-1 rounded-md px-2.5 text-xs font-medium transition-colors duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-focus)]",
        active
          ? "bg-primary text-primary-foreground shadow-sm"
          : "text-muted-foreground hover:bg-muted/80 hover:text-foreground",
        className,
      )}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  );
}

export function ClinicalChatThread({
  active,
  sidebarOpen,
  onToggleSidebar,
  onNew,
  onClear,
  onDelete,
  onRename,
  onCopy,
  onOpenPanel,
  clinicalPanelTab = "clinical",
  panelOpen = false,
  evidenceCount = 0,
  streamStatus,
  streamProgress,
}) {
  const { language, languages, setLanguage, t } = useLanguage();
  const summary = patientSummary(active?.draft?.patient || active?.patient);
  const hasActive = Boolean(active);
  const showPanelTabs = hasActive && (evidenceCount > 0 || Boolean(active?.recommendation));

  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [copied, setCopied] = useState(false);
  const titleInputRef = useRef(null);

  useEffect(() => {
    setEditingTitle(false);
    setTitleDraft(active?.name || "");
  }, [active?.id, active?.name]);

  useEffect(() => {
    if (editingTitle) {
      titleInputRef.current?.focus();
      titleInputRef.current?.select();
    }
  }, [editingTitle]);

  const commitTitle = useCallback(() => {
    if (active && titleDraft.trim()) {
      onRename?.(active.id, titleDraft.trim());
    }
    setEditingTitle(false);
  }, [active, onRename, titleDraft]);

  function handleClear() {
    if (!active) return;
    if (!window.confirm(t("chat.clearConfirm"))) return;
    onClear?.(active.id);
  }

  function handleDelete() {
    if (!active) return;
    if (!window.confirm(t("chat.deleteConfirm"))) return;
    onDelete?.(active.id);
  }

  async function handleCopy() {
    if (!active) return;
    await onCopy?.();
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  function startTitleEdit() {
    if (!active) return;
    setTitleDraft(active.name || summary?.name || "");
    setEditingTitle(true);
  }

  return (
    <section
      aria-label="Clinical chat"
      className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden border-border/80 bg-[var(--color-paper)]"
    >
      <header
        className="flex shrink-0 items-center gap-2 border-b border-[var(--color-rule)] bg-[var(--color-paper)]/95 px-3 backdrop-blur-sm supports-[backdrop-filter]:bg-[var(--color-paper)]/80 sm:gap-3"
        style={{ minHeight: "var(--chat-header-h)" }}
      >
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
          {editingTitle ? (
            <input
              ref={titleInputRef}
              aria-label={t("chat.renamePlaceholder")}
              className="w-full max-w-md rounded-md border border-[var(--color-rule)] bg-[var(--color-paper-2)] px-2 py-1 text-sm font-medium outline-none ring-[var(--color-focus)] focus-visible:ring-2"
              onBlur={commitTitle}
              onChange={(e) => setTitleDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  commitTitle();
                }
                if (e.key === "Escape") {
                  setEditingTitle(false);
                  setTitleDraft(active?.name || "");
                }
              }}
              value={titleDraft}
            />
          ) : (
            <button
              className="group/title flex max-w-full min-w-0 cursor-pointer items-center gap-1.5 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-focus)] disabled:cursor-default disabled:hover:bg-transparent"
              disabled={!hasActive}
              onClick={startTitleEdit}
              type="button"
            >
              <span className="truncate font-medium [font-family:var(--font-display)]">
                {active?.name || "HF CDSS"}
              </span>
              {hasActive ? (
                <Pencil
                  aria-hidden
                  className="size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover/title:opacity-100"
                />
              ) : null}
            </button>
          )}
          {summary && !editingTitle ? (
            <div className="truncate text-xs text-muted-foreground">
              {summary.name} · {summary.sex ?? "—"} · {summary.age ?? "—"} {t("chat.ageUnit")}
            </div>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
          {showPanelTabs ? (
            <div
              className="mr-1 hidden items-center gap-0.5 rounded-lg border border-[var(--color-rule)] bg-[var(--color-paper-2)] p-0.5 sm:flex"
              role="group"
              aria-label={t("chat.toggleClinicalPanel")}
            >
              <PanelSegmentButton
                active={panelOpen && clinicalPanelTab === "clinical"}
                onClick={() => onOpenPanel?.("clinical")}
              >
                {t("clinicalPanel.tabClinical")}
              </PanelSegmentButton>
              <PanelSegmentButton
                active={panelOpen && clinicalPanelTab === "evidence"}
                className="gap-1"
                onClick={() => onOpenPanel?.("evidence")}
              >
                {t("clinicalPanel.tabEvidence")}
                {evidenceCount > 0 ? (
                  <Badge
                    className={cn(
                      "h-4 min-w-4 justify-center px-1 text-[10px]",
                      panelOpen && clinicalPanelTab === "evidence"
                        ? "border-primary-foreground/20 bg-primary-foreground/15 text-primary-foreground"
                        : "",
                    )}
                    variant="secondary"
                  >
                    {evidenceCount}
                  </Badge>
                ) : null}
              </PanelSegmentButton>
            </div>
          ) : null}

          <Button
            aria-label={t("chat.toggleClinicalPanel")}
            aria-pressed={panelOpen}
            className={cn("shrink-0 sm:hidden", panelOpen && "bg-muted text-foreground")}
            disabled={!showPanelTabs}
            onClick={() => onOpenPanel?.(clinicalPanelTab === "evidence" ? "evidence" : "clinical")}
            size="icon"
            type="button"
            variant="ghost"
          >
            <PanelRight size={18} />
          </Button>

          <div className="hidden md:block">
            <LanguageToggle language={language} languages={languages} onChange={setLanguage} variant="light" />
          </div>

          <Button
            aria-label={t("chat.newChat")}
            className="shrink-0"
            onClick={onNew}
            size="icon"
            title={t("chat.newChat")}
            type="button"
            variant="ghost"
          >
            <Plus size={18} />
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label={t("chat.conversationActions")}
                className="shrink-0"
                disabled={!hasActive}
                size="icon"
                title={t("chat.conversationActions")}
                type="button"
                variant="ghost"
              >
                <MoreVertical size={18} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onClick={onNew}>
                <Plus />
                {t("chat.newChat")}
              </DropdownMenuItem>
              <DropdownMenuItem disabled={!hasActive} onClick={startTitleEdit}>
                <Pencil />
                {t("sidebar.renameChat")}
              </DropdownMenuItem>
              <DropdownMenuItem disabled={!hasActive} onClick={handleCopy}>
                <Copy />
                {copied ? t("chat.copied") : t("chat.copyChat")}
              </DropdownMenuItem>
              {showPanelTabs ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => onOpenPanel?.("clinical")}>
                    <FileText />
                    {t("chat.openClinicalPanel")}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onOpenPanel?.("evidence")}>
                    <PanelRight />
                    {t("chat.openEvidencePanel", { count: evidenceCount })}
                  </DropdownMenuItem>
                </>
              ) : null}
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled={!hasActive} onClick={handleClear}>
                <Eraser />
                {t("chat.clearChat")}
              </DropdownMenuItem>
              <DropdownMenuItem disabled={!hasActive} onClick={handleDelete} variant="destructive">
                <Trash2 />
                {t("chat.deleteChat")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <ClinicalConversationContext.Provider
          value={{
            recommendation: active?.recommendation ?? null,
            verification: active?.verification ?? null,
            onOpenEvidencePanel: () => onOpenPanel?.("evidence"),
          }}
        >
          <StreamProgressProvider value={streamProgress}>
            <Thread
              components={{
                Welcome: ClinicalWelcome,
                TextPart: ClinicalAnswerText,
                hideBranchPicker: true,
              }}
              pendingMultiQuestion={active?.pendingMultiQuestion}
              onContinueMulti={() => patchConversation(active?.id, { multiQuestionAction: "continue" })}
              onStopMulti={() => patchConversation(active?.id, { multiQuestionAction: "stop" })}
            />
          </StreamProgressProvider>
        </ClinicalConversationContext.Provider>
      </div>

      {streamProgress?.step ? (
        <div className="shrink-0 border-t border-[var(--color-rule)] px-3 py-2 sm:px-4">
          <ClinicalStreamProgress
            className="mx-auto w-full max-w-(--thread-max-width)"
            label={streamProgress.label || streamStatus}
            step={streamProgress.step}
          />
        </div>
      ) : null}

      <p aria-live="polite" className="sr-only">
        {copied ? t("chat.copied") : ""}
      </p>
    </section>
  );
}
