import { useEffect, useRef } from "react";
import { Bot, ChevronLeft, LoaderCircle, MessageSquareHeart, PanelLeft, Send, Stethoscope, Upload, UserRound } from "lucide-react";
import { patientSummary } from "../utils";
import { LanguageToggle } from "./LanguageToggle";

const COMPOSER_PLACEHOLDERS = {
  vi: "Hỏi về triệu chứng, thuốc đang dùng, titration, chống chỉ định hoặc theo dõi... (Enter gửi, Shift+Enter xuống dòng)",
  en: "Ask about symptoms, current medications, titration, contraindications, or monitoring... (Enter to send, Shift+Enter for newline)",
};

const EMPTY_COPY = {
  vi: {
    title: "Bắt đầu hội thoại lâm sàng",
    body: "Tạo hồ sơ bệnh nhân mới để trò chuyện với trợ lý HF CDSS về GDMT, an toàn thuốc và bằng chứng điều trị.",
  },
  en: {
    title: "Start a clinical conversation",
    body: "Create a new patient profile to chat with the HF CDSS assistant about GDMT, medication safety, and evidence.",
  },
};

function TypingDots() {
  return (
    <span aria-hidden="true" className="typing-dots">
      <span />
      <span />
      <span />
    </span>
  );
}

export function ChatMain({
  active,
  chatInput,
  setChatInput,
  loading,
  streamStatus,
  onSubmit,
  onFiles,
  sidebarOpen,
  onToggleSidebar,
  language,
  languages,
  onLanguageChange,
}) {
  const messagesRef = useRef(null);
  const summary = patientSummary(active?.draft?.patient || active?.patient);

  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [active?.messages?.length, active?.messages?.at(-1)?.content]);

  if (!active) {
    const copy = EMPTY_COPY[language] || EMPTY_COPY.en;
    return (
      <section aria-label="Clinical chat" className="chat-main">
        <div className="chat-toggles chat-toggles--empty">
          <button
            aria-label={sidebarOpen ? "Hide conversation sidebar" : "Show conversation sidebar"}
            className="toggle-btn"
            onClick={onToggleSidebar}
            type="button"
          >
            {sidebarOpen ? <ChevronLeft size={16} /> : <PanelLeft size={16} />}
          </button>
          <LanguageToggle language={language} languages={languages} onChange={onLanguageChange} />
        </div>
        <div className="empty-chat">
          <div aria-hidden="true" className="empty-chat-icon">
            <MessageSquareHeart size={28} />
          </div>
          <h1>{copy.title}</h1>
          <p>{copy.body}</p>
        </div>
      </section>
    );
  }

  return (
    <section aria-label="Clinical chat" className="chat-main">
      <header className="chat-header">
        <button
          aria-label={sidebarOpen ? "Hide conversation sidebar" : "Show conversation sidebar"}
          className="toggle-btn"
          onClick={onToggleSidebar}
          type="button"
        >
          {sidebarOpen ? <ChevronLeft size={16} /> : <PanelLeft size={16} />}
        </button>

        <div className="chat-header-info">
          <div className="chat-header-badge">
            <Stethoscope size={12} />
            HF CDSS
          </div>
          <h1>{active.name}</h1>
          <p>
            {summary?.name} · {summary?.sex ?? "—"} · {summary?.age ?? "—"} {language === "vi" ? "tuổi" : "years"}
          </p>
        </div>

        <div className="chat-header-actions">
          <LanguageToggle language={language} languages={languages} onChange={onLanguageChange} />

          <label className="attach-button">
            <Upload aria-hidden="true" size={16} />
            {language === "vi" ? "Đính kèm" : "Attach"}
            <input accept=".txt,.csv,.json,.md,.xml,.html,image/*,.pdf" multiple onChange={onFiles} type="file" />
          </label>
        </div>
      </header>

      <div aria-live="polite" className="messages" ref={messagesRef} role="log">
        {(active.messages || []).map((msg) => (
          <article className={`message ${msg.role}`} key={msg.id || `${msg.role}-${msg.content?.slice(0, 24)}`}>
            <div aria-hidden="true" className="avatar">
              {msg.role === "assistant" ? <Bot size={16} /> : <UserRound size={16} />}
            </div>
            <p>{msg.content}</p>
          </article>
        ))}

        {loading && !active.messages?.at(-1)?.content && (
          <article aria-busy="true" className="message assistant">
            <div aria-hidden="true" className="avatar">
              <LoaderCircle className="spin" size={16} />
            </div>
            <p className="loading-text">
              <TypingDots />
              {streamStatus || (language === "vi" ? "Đang phân tích lâm sàng..." : "Processing clinical stream...")}
            </p>
          </article>
        )}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <textarea
          aria-label={language === "vi" ? "Nhập câu hỏi lâm sàng" : "Enter clinical question"}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit(e);
            }
          }}
          placeholder={COMPOSER_PLACEHOLDERS[language] || COMPOSER_PLACEHOLDERS.en}
          value={chatInput}
        />
        <button
          aria-label={language === "vi" ? "Gửi tin nhắn" : "Send message"}
          disabled={loading || !chatInput.trim()}
          type="submit"
        >
          <Send aria-hidden="true" size={18} />
        </button>
      </form>
    </section>
  );
}
