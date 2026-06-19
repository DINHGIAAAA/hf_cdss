import { useState } from "react";

import { Sidebar } from "../components/Sidebar";
import { PatientModal } from "../components/PatientModal";
import { ChatMain } from "../components/ChatMain";
import { ClinicalPanel } from "../components/ClinicalPanel";

import { useConversations, useChat, useApiHealth, useLanguage } from "../hooks";
import { readClinicalFiles } from "../utils";

export function ChatPage() {
  const health = useApiHealth();
  const [showModal, setShowModal] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(() => localStorage.getItem("hf_sidebar") !== "0");
  const [panelOpen, setPanelOpen] = useState(() => localStorage.getItem("hf_panel") !== "0");
  const { language, setLanguage, languages } = useLanguage();

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
      className={[
        "app-shell",
        sidebarOpen ? "" : "app-shell--sidebar-collapsed",
        panelOpen ? "" : "app-shell--panel-collapsed",
      ]
        .filter(Boolean)
        .join(" ")}
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
        panelOpen={panelOpen}
        onToggleSidebar={() =>
          setSidebarOpen((v) => {
            localStorage.setItem("hf_sidebar", v ? "0" : "1");
            return !v;
          })
        }
        onTogglePanel={() =>
          setPanelOpen((v) => {
            localStorage.setItem("hf_panel", v ? "0" : "1");
            return !v;
          })
        }
        onFiles={handleFiles}
        onSubmit={submitChat}
        setChatInput={setChatInput}
      />

      <ClinicalPanel active={active} error={error} open={panelOpen} />
    </main>
  );
}
