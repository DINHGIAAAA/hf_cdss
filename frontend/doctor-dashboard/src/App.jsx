import { useState } from "react";

import { Sidebar } from "./components/Sidebar";
import { PatientModal } from "./components/PatientModal";
import { ChatMain } from "./components/ChatMain";
import { ClinicalPanel } from "./components/ClinicalPanel";

import { useConversations, useChat, useApiHealth } from "./hooks";
import { readClinicalFiles } from "./utils";

import "./styles/base.css";
import "./styles/layout.css";
import "./styles/sidebar.css";
import "./styles/chat.css";
import "./styles/clinical-panel.css";
import "./styles/modal.css";

function App() {
  const health = useApiHealth();
  const [showModal, setShowModal] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(() => localStorage.getItem("hf_sidebar") !== "0");
  const [panelOpen, setPanelOpen] = useState(() => localStorage.getItem("hf_panel") !== "0");

  const {
    conversations,
    activeId,
    setActiveId,
    patchConversation,
    updateActive,
    createConversation,
  } = useConversations();

  const active = conversations.find((c) => c.id === activeId) || null;

  const { chatInput, setChatInput, loading, streamStatus, error, setError, submitChat } = useChat({
    activeId,
    active,
    patchConversation,
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
      ].filter(Boolean).join(" ")}
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
          setActiveId(id);
          setError("");
        }}
      />

      <ChatMain
        active={active}
        chatInput={chatInput}
        loading={loading}
        streamStatus={streamStatus}
        sidebarOpen={sidebarOpen}
        panelOpen={panelOpen}
        onToggleSidebar={() => setSidebarOpen((v) => { localStorage.setItem("hf_sidebar", v ? "0" : "1"); return !v; })}
        onTogglePanel={() => setPanelOpen((v) => { localStorage.setItem("hf_panel", v ? "0" : "1"); return !v; })}
        onFiles={handleFiles}
        onSubmit={submitChat}
        setChatInput={setChatInput}
      />

      <ClinicalPanel active={active} error={error} open={panelOpen} />
    </main>
  );
}

export default App;
