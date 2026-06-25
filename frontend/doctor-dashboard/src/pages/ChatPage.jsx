import { useState } from "react";

import { Sidebar } from "../components/Sidebar";
import { PatientModal } from "../components/PatientModal";
import { ChatMain } from "../components/ChatMain";
import { ClinicalPanel } from "../components/ClinicalPanel";

import { useConversations, useChat, useApiHealth, useLanguage, useHorizontalResize } from "../hooks";
import { readClinicalFiles } from "../utils";

export function ChatPage() {
  const health = useApiHealth();
  const [showModal, setShowModal] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(() => localStorage.getItem("hf_sidebar") !== "0");
  const { language, setLanguage, languages } = useLanguage();
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

  const { chatInput, setChatInput, loading, streamStatus, error, setError, submitChat } = useChat({
    active,
    patchConversation,
    language,
  });

  const shouldShowModal = showModal || conversations.length === 0;

  async function handleFiles(event) {
    if (!active) return;
    const parsed = await readClinicalFiles(event.target.files);
    updateActive({ attachments: [...(active.attachments || []), ...parsed] });
    event.target.value = "";
  }

  function handleCreate(form, patientId, conversationName) {
    createConversation(form, patientId, conversationName);
    setShowModal(false);
    setError("");
  }

  return (
    <main
      className={["app-shell", sidebarOpen ? "" : "app-shell--sidebar-collapsed"].filter(Boolean).join(" ")}
      ref={containerRef}
      style={{ "--panel-width": `${panelWidth}px` }}
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
        language={language}
        languages={languages}
        onLanguageChange={setLanguage}
        open={sidebarOpen}
        onNew={() => setShowModal(true)}
        onSelect={(id) => {
          selectConversation(id);
          setError("");
        }}
      />

      <ChatMain
        active={active}
        chatInput={chatInput}
        language={language}
        languages={languages}
        loading={loading}
        onLanguageChange={setLanguage}
        streamStatus={streamStatus}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() =>
          setSidebarOpen((v) => {
            localStorage.setItem("hf_sidebar", v ? "0" : "1");
            return !v;
          })
        }
        onFiles={handleFiles}
        onSubmit={submitChat}
        setChatInput={setChatInput}
      />

      <div
        aria-label="Resize evidence panel"
        aria-orientation="vertical"
        aria-valuemax={520}
        aria-valuemin={0}
        aria-valuenow={Math.round(panelWidth)}
        className="panel-resize-handle"
        onPointerDown={onPointerDown}
        role="separator"
        tabIndex={0}
      />

      <ClinicalPanel active={active} error={error} open={panelOpen} />
    </main>
  );
}
