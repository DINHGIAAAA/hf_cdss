import { useEffect, useRef } from "react";
import { ArrowUp, Bot, LoaderCircle, PanelLeft, Paperclip, SquarePen, UserRound } from "lucide-react";
import { patientSummary } from "../utils";
import { LanguageToggle } from "./LanguageToggle";

const COMPOSER_PLACEHOLDERS = {
  vi: "Hỏi về GDMT, an toàn thuốc, titration hoặc bằng chứng lâm sàng...",
  en: "Ask about GDMT, medication safety, titration, or clinical evidence...",
};

const EMPTY_COPY = {
  vi: {
    title: "HF CDSS Clinical Assistant",
    body: "Tạo hồ sơ bệnh nhân mới để bắt đầu hội thoại với trợ lý lâm sàng.",
  },
  en: {
    title: "HF CDSS Clinical Assistant",
    body: "Create a new patient profile to start chatting with the clinical assistant.",
  },
};

const WELCOME_COPY = {
  vi: {
    title: "Bạn cần hỗ trợ gì cho ca bệnh này?",
    suggestions: [
      "Đánh giá GDMT hiện tại và còn thiếu gì",
      "Có nên tiếp tục MRA với eGFR 24 và K+ 5.7?",
      "Khuyến nghị titration beta-blocker an toàn",
      "Tương tác thuốc và chống chỉ định cần lưu ý",
    ],
  },
  en: {
    title: "How can I help with this case?",
    suggestions: [
      "Review current GDMT and identify gaps",
      "Should we continue MRA with eGFR 24 and K+ 5.7?",
      "Safe beta-blocker titration recommendations",
      "Drug interactions and contraindications to watch",
    ],
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
  const copy = EMPTY_COPY[language] || EMPTY_COPY.en;
  const welcome = WELCOME_COPY[language] || WELCOME_COPY.en;
  const hasMessages = (active?.messages || []).length > 0;

  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [active?.messages?.length, active?.messages?.at(-1)?.content]);

  function handleSuggestion(text) {
    setChatInput(text);
  }

  if (!active) {
    return (
      <section aria-label="Clinical chat" className="chat-main">
        <header className="chat-topbar">
          <button
            aria-label={sidebarOpen ? "Hide conversation sidebar" : "Show conversation sidebar"}
            className="icon-btn"
            onClick={onToggleSidebar}
            type="button"
          >
            <PanelLeft size={18} />
          </button>
          <div className="chat-topbar-title">HF CDSS</div>
          <LanguageToggle language={language} languages={languages} onChange={onLanguageChange} />
        </header>

        <div className="chat-empty">
          <div aria-hidden="true" className="chat-empty-icon">
            <SquarePen size={28} />
          </div>
          <h1>{copy.title}</h1>
          <p>{copy.body}</p>
        </div>
      </section>
    );
  }

  return (
    <section aria-label="Clinical chat" className="chat-main">
      <header className="chat-topbar">
        <button
          aria-label={sidebarOpen ? "Hide conversation sidebar" : "Show conversation sidebar"}
          className="icon-btn"
          onClick={onToggleSidebar}
          type="button"
        >
          <PanelLeft size={18} />
        </button>

        <div className="chat-topbar-title">
          <span className="chat-topbar-name">{active.name}</span>
          {summary && (
            <span className="chat-topbar-meta">
              {summary.name} · {summary.sex ?? "—"} · {summary.age ?? "—"} {language === "vi" ? "tuổi" : "y"}
            </span>
          )}
        </div>

        <div className="chat-topbar-actions">
          <LanguageToggle language={language} languages={languages} onChange={onLanguageChange} />
        </div>
      </header>

      <div aria-live="polite" className="chat-thread" ref={messagesRef} role="log">
        {!hasMessages && !loading && (
          <div className="chat-welcome">
            <h2>{welcome.title}</h2>
            <div className="suggestion-grid">
              {welcome.suggestions.map((suggestion) => (
                <button
                  className="suggestion-chip"
                  key={suggestion}
                  onClick={() => handleSuggestion(suggestion)}
                  type="button"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {(active.messages || []).map((msg) => (
          <article
            className={`message-row message-row--${msg.role}`}
            key={msg.id || `${msg.role}-${msg.content?.slice(0, 24)}`}
          >
            <div className="message-inner">
              <div aria-hidden="true" className={`message-avatar message-avatar--${msg.role}`}>
                {msg.role === "assistant" ? <Bot size={18} /> : <UserRound size={18} />}
              </div>
              <div className="message-body">
                <p>{msg.content}</p>
              </div>
            </div>
          </article>
        ))}

        {loading && !active.messages?.at(-1)?.content && (
          <article aria-busy="true" className="message-row message-row--assistant">
            <div className="message-inner">
              <div aria-hidden="true" className="message-avatar message-avatar--assistant">
                <LoaderCircle className="spin" size={18} />
              </div>
              <div className="message-body">
                <p className="loading-text">
                  <TypingDots />
                  {streamStatus || (language === "vi" ? "Đang phân tích lâm sàng..." : "Analyzing clinical context...")}
                </p>
              </div>
            </div>
          </article>
        )}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <div className="composer-shell">
          <label aria-label={language === "vi" ? "Đính kèm tệp" : "Attach files"} className="composer-attach">
            <Paperclip size={18} />
            <input accept=".txt,.csv,.json,.md,.xml,.html,image/*,.pdf" multiple onChange={onFiles} type="file" />
          </label>

          <textarea
            aria-label={language === "vi" ? "Nhập câu hỏi lâm sàng" : "Enter clinical question"}
            className="composer-input"
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit(e);
              }
            }}
            placeholder={COMPOSER_PLACEHOLDERS[language] || COMPOSER_PLACEHOLDERS.en}
            rows={1}
            value={chatInput}
          />

          <button
            aria-label={language === "vi" ? "Gửi tin nhắn" : "Send message"}
            className="composer-send"
            disabled={loading || !chatInput.trim()}
            type="submit"
          >
            <ArrowUp size={18} />
          </button>
        </div>
        <p className="composer-hint">
          {language === "vi"
            ? "HF CDSS hỗ trợ quyết định lâm sàng — không thay thế đánh giá của bác sĩ."
            : "HF CDSS supports clinical decisions — not a substitute for physician judgment."}
        </p>
      </form>
    </section>
  );
}
