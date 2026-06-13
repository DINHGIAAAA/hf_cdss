import { useEffect, useRef } from "react";
import { Bot, ChevronLeft, ChevronRight, LoaderCircle, PanelLeft, PanelRight, Send, Upload, UserRound } from "lucide-react";
import { patientSummary } from "../utils";

export function ChatMain({
  active,
  chatInput,
  setChatInput,
  loading,
  streamStatus,
  onSubmit,
  onFiles,
  sidebarOpen,
  panelOpen,
  onToggleSidebar,
  onTogglePanel,
}) {
  const messagesRef = useRef(null);
  const summary = patientSummary(active?.draft?.patient || active?.patient);

  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [active?.messages?.length, active?.messages?.at(-1)?.content]);

  if (!active) {
    return (
      <section className="chat-main">
        {/* Toggle buttons khi không có conversation */}
        <div className="chat-toggles chat-toggles--empty">
          <button className="toggle-btn" onClick={onToggleSidebar} title={sidebarOpen ? "Hide sidebar" : "Show sidebar"} type="button">
            {sidebarOpen ? <ChevronLeft size={16} /> : <PanelLeft size={16} />}
          </button>
          <button className="toggle-btn toggle-btn--right" onClick={onTogglePanel} title={panelOpen ? "Hide panel" : "Show panel"} type="button">
            {panelOpen ? <ChevronRight size={16} /> : <PanelRight size={16} />}
          </button>
        </div>
        <div className="empty-chat">
          <h1>Start a patient conversation</h1>
          <p>Create a new conversation to begin clinical decision support.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="chat-main">
      <header className="chat-header">
        {/* Sidebar toggle */}
        <button
          className="toggle-btn"
          onClick={onToggleSidebar}
          title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
          type="button"
        >
          {sidebarOpen ? <ChevronLeft size={16} /> : <PanelLeft size={16} />}
        </button>

        <div className="chat-header-info">
          <h1>{active.name}</h1>
          <p>
            {summary?.name} - {summary?.sex ?? "sex ?"} - {summary?.age ?? "age ?"} years
          </p>
        </div>

        <div className="chat-header-actions">
          <label className="attach-button">
            <Upload size={16} />
            Attach
            <input accept=".txt,.csv,.json,.md,.xml,.html,image/*,.pdf" multiple onChange={onFiles} type="file" />
          </label>

          {/* Panel toggle */}
          <button
            className="toggle-btn"
            onClick={onTogglePanel}
            title={panelOpen ? "Hide evidence panel" : "Show evidence panel"}
            type="button"
          >
            {panelOpen ? <ChevronRight size={16} /> : <PanelRight size={16} />}
          </button>
        </div>
      </header>

      <div className="messages" ref={messagesRef}>
        {(active.messages || []).map((msg, i) => (
          <article className={`message ${msg.role}`} key={`${msg.role}-${i}`}>
            <div className="avatar">
              {msg.role === "assistant" ? <Bot size={16} /> : <UserRound size={16} />}
            </div>
            <p>{msg.content}</p>
          </article>
        ))}

        {loading && !active.messages?.at(-1)?.content && (
          <article className="message assistant">
            <div className="avatar">
              <LoaderCircle className="spin" size={16} />
            </div>
            <p className="loading-text">{streamStatus || "Processing clinical stream..."}</p>
          </article>
        )}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <textarea
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit(e);
            }
          }}
          placeholder="Ask about symptoms, current medications, titration, contraindications, or monitoring... (Enter to send, Shift+Enter for newline)"
          value={chatInput}
        />
        <button disabled={loading || !chatInput.trim()} type="submit">
          <Send size={18} />
        </button>
      </form>
    </section>
  );
}
