import { useState } from "react";

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
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(() => localStorage.getItem("hf_sidebar") !== "0");
  const { language, t } = useLanguage();
  const { width: panelWidth, isOpen: panelOpen, containerRef, onPointerDown } = useHorizontalResize({
    collapseThreshold: 56,
    edge: "right",
    initial: 380,
    max: 520,
    min: 0,
    storageKey: "hf_panel_width",
  });

  const {
    conversations,
    activeId,
    selectConversation,
    patchConversation,
    updateActive,
    createConversation,
  } = useConversations();

  const active = conversations.find((c) => c.id === activeId) || null;
  const shouldShowModal = showModal || conversations.length === 0;

  function handleCreate(form, patientId, conversationName) {
    createConversation(form, patientId, conversationName);
    setShowModal(false);
    setError("");
  }

  return (
    <main
      className="chat-shell grid h-full min-h-0 overflow-hidden bg-background"
      ref={containerRef}
      style={{
        gridTemplateColumns: `${sidebarOpen ? 260 : 56}px minmax(0, 1fr) 4px ${panelOpen ? panelWidth : 0}px`,
      }}
    >
      {shouldShowModal && (
        <PatientModal
          onCreate={handleCreate}
          onClose={conversations.length > 0 ? () => setShowModal(false) : undefined}
        />
      )}

      <Sidebar
        conversations={conversations}
        activeId={activeId}
        health={health}
        open={sidebarOpen}
        onNew={() => setShowModal(true)}
        onSelect={(id) => {
          selectConversation(id);
          setError("");
        }}
      />

      <ClinicalChatRuntimeProvider
        active={active}
        language={language}
        onError={setError}
        onStreamStatus={setStreamStatus}
        patchConversation={patchConversation}
        updateActive={updateActive}
      >
        <ClinicalChatThread
          active={active}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() =>
            setSidebarOpen((value) => {
              localStorage.setItem("hf_sidebar", value ? "0" : "1");
              return !value;
            })
          }
          streamStatus={streamStatus}
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

      <ClinicalPanel active={active} error={error} open={panelOpen} />
    </main>
  );
}
