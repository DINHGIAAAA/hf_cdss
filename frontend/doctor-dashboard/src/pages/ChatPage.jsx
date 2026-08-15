import { useState, useEffect, useCallback } from "react";

import { Sidebar } from "../components/Sidebar";
import { PatientModal } from "../components/PatientModal";
import { ClinicalPanel } from "../components/ClinicalPanel";
import { ClinicalChatRuntimeProvider } from "../components/ClinicalChatRuntime";
import { ClinicalChatThread } from "../components/ClinicalChatThread";

import { useConversations, useApiHealth, useLanguage, useHorizontalResize } from "../hooks";
import { cn } from "@/lib/utils";

export function ChatPage() {
  const health = useApiHealth();
  const [showModal, setShowModal] = useState(false);
  const [streamStatus, setStreamStatus] = useState("");
  const [streamProgress, setStreamProgress] = useState(null);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(() => localStorage.getItem("hf_sidebar") !== "0");
  const { t } = useLanguage();
  const { width: panelWidth, isOpen: panelOpen, setWidth, containerRef, onPointerDown } = useHorizontalResize({
    collapseThreshold: 56,
    edge: "right",
    initial: 380,
    max: 520,
    min: 0,
    storageKey: "hf_panel_width",
  });

  const [clinicalPanelTab, setClinicalPanelTab] = useState("clinical");

  const {
    conversations,
    activeId,
    selectConversation,
    patchConversation,
    updateActive,
    createConversation,
    loadDemoConversation,
    deleteConversation,
    renameConversation,
    copyConversation,
    clearConversation,
  } = useConversations();

  const active = conversations.find((c) => c.id === activeId) || null;
  const evidenceCount = active?.verification?.context?.evidence_chunks?.length || 0;
  const shouldShowModal = showModal || conversations.length === 0;

  useEffect(() => {
    setClinicalPanelTab("clinical");
  }, [active?.id]);

  const openClinicalPanel = useCallback(
    (tab = "clinical") => {
      setClinicalPanelTab(tab);
      if (panelWidth <= 56) {
        setWidth(380);
      }
    },
    [panelWidth, setWidth],
  );

  async function handleCopyConversation(conversationId) {
    await copyConversation(conversationId);
  }

  function handleCreate(form, patientId, conversationName) {
    createConversation(form, patientId, conversationName);
    setShowModal(false);
    setError("");
  }

  async function handleLoadDemo() {
    await loadDemoConversation();
    setShowModal(false);
    setError("");
  }

  return (
    <main
      className="chat-shell chat-workbench grid h-full min-h-0 overflow-hidden bg-[var(--color-paper)]"
      ref={containerRef}
      style={{
        gridTemplateColumns: `${sidebarOpen ? 260 : 56}px minmax(0, 1fr) 4px ${panelOpen ? panelWidth : 0}px`,
      }}
    >
      {shouldShowModal && (
        <PatientModal
          onCreate={handleCreate}
          onLoadDemo={handleLoadDemo}
          onClose={conversations.length > 0 ? () => setShowModal(false) : undefined}
        />
      )}

      <Sidebar
        conversations={conversations}
        activeId={activeId}
        health={health}
        open={sidebarOpen}
        onCopy={handleCopyConversation}
        onDelete={deleteConversation}
        onNew={() => setShowModal(true)}
        onRename={renameConversation}
        onSelect={(id) => {
          selectConversation(id);
          setError("");
        }}
      />

      <ClinicalChatRuntimeProvider
        active={active}
        onError={setError}
        onStreamStatus={setStreamStatus}
        onStreamProgress={setStreamProgress}
        patchConversation={patchConversation}
        updateActive={updateActive}
      >
        <ClinicalChatThread
          active={active}
          clinicalPanelTab={clinicalPanelTab}
          evidenceCount={evidenceCount}
          panelOpen={panelOpen}
          sidebarOpen={sidebarOpen}
          onClear={clearConversation}
          onCopy={() => (active ? handleCopyConversation(active.id) : undefined)}
          onDelete={deleteConversation}
          onNew={() => setShowModal(true)}
          onOpenPanel={openClinicalPanel}
          onRename={renameConversation}
          onToggleSidebar={() =>
            setSidebarOpen((value) => {
              localStorage.setItem("hf_sidebar", value ? "0" : "1");
              return !value;
            })
          }
          streamStatus={streamStatus}
          streamProgress={streamProgress}
        />
      </ClinicalChatRuntimeProvider>

      <div
        aria-label={t("chat.resizePanel")}
        aria-orientation="vertical"
        aria-valuemax={520}
        aria-valuemin={0}
        aria-valuenow={Math.round(panelWidth)}
        className={cn(
          "group relative z-10 cursor-col-resize bg-border/60 transition-colors hover:bg-primary/30",
          panelOpen ? "w-1" : "w-0",
        )}
        onPointerDown={onPointerDown}
        role="separator"
        tabIndex={0}
      />

      <ClinicalPanel
        active={active}
        error={error}
        onPanelTabChange={setClinicalPanelTab}
        open={panelOpen}
        panelTab={clinicalPanelTab}
      />
    </main>
  );
}
