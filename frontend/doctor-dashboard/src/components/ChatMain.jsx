import { useEffect, useRef } from "react";
import { ArrowUp, Bot, LoaderCircle, PanelLeft, Paperclip, SquarePen, UserRound } from "lucide-react";
import { patientSummary } from "../utils";
import { LanguageToggle } from "./LanguageToggle";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

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
    <span aria-hidden="true" className="inline-flex items-center gap-1">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </span>
  );
}

function MessageBubble({ msg }) {
  const isAssistant = msg.role === "assistant";
  return (
    <article className={cn("flex gap-3 px-4 py-3", isAssistant ? "bg-muted/50" : "bg-background")}>
      <Avatar className="size-8 shrink-0">
        <AvatarFallback className={cn(isAssistant ? "bg-primary/10 text-primary" : "bg-secondary text-foreground")}>
          {isAssistant ? <Bot size={16} /> : <UserRound size={16} />}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1 pt-0.5">
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-foreground">{msg.content}</p>
      </div>
    </article>
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

  const topbar = (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-3">
      <Button aria-label={sidebarOpen ? "Hide conversation sidebar" : "Show conversation sidebar"} onClick={onToggleSidebar} size="icon" type="button" variant="ghost">
        <PanelLeft size={18} />
      </Button>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{active?.name || "HF CDSS"}</div>
        {summary && (
          <div className="truncate text-xs text-muted-foreground">
            {summary.name} · {summary.sex ?? "—"} · {summary.age ?? "—"} {language === "vi" ? "tuổi" : "y"}
          </div>
        )}
      </div>
      <LanguageToggle language={language} languages={languages} onChange={onLanguageChange} variant="light" />
    </header>
  );

  if (!active) {
    return (
      <section aria-label="Clinical chat" className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
        {topbar}
        <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
          <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <SquarePen size={28} />
          </div>
          <h1 className="text-2xl font-semibold">{copy.title}</h1>
          <p className="mt-2 max-w-md text-muted-foreground">{copy.body}</p>
        </div>
      </section>
    );
  }

  return (
    <section aria-label="Clinical chat" className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
      {topbar}

      <div className="min-h-0 flex-1 overflow-y-auto" ref={messagesRef}>
        <div aria-live="polite" className="mx-auto w-full max-w-3xl" role="log">
          {!hasMessages && !loading && (
            <div className="px-4 py-10">
              <h2 className="text-center text-xl font-semibold">{welcome.title}</h2>
              <div className="mt-6 grid gap-2 sm:grid-cols-2">
                {welcome.suggestions.map((suggestion) => (
                  <Button
                    className="h-auto min-h-11 justify-start whitespace-normal px-4 py-3 text-left text-sm font-normal"
                    key={suggestion}
                    onClick={() => handleSuggestion(suggestion)}
                    type="button"
                    variant="outline"
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {(active.messages || []).map((msg) => (
            <MessageBubble key={msg.id || `${msg.role}-${msg.content?.slice(0, 24)}`} msg={msg} />
          ))}

          {loading && !active.messages?.at(-1)?.content && (
            <article aria-busy="true" className="flex gap-3 bg-muted/50 px-4 py-3">
              <Avatar className="size-8">
                <AvatarFallback className="bg-primary/10 text-primary">
                  <LoaderCircle className="animate-spin" size={16} />
                </AvatarFallback>
              </Avatar>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <TypingDots />
                {streamStatus || (language === "vi" ? "Đang phân tích lâm sàng..." : "Analyzing clinical context...")}
              </div>
            </article>
          )}
        </div>
      </div>

      <form className="border-t border-border bg-background px-4 py-4" onSubmit={onSubmit}>
        <Card className="mx-auto max-w-3xl border-border/80 p-2 shadow-md">
          <div className="flex items-end gap-2">
            <label aria-label={language === "vi" ? "Đính kèm tệp" : "Attach files"} className="relative flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
              <Paperclip size={18} />
              <input accept=".txt,.csv,.json,.md,.xml,.html,image/*,.pdf" className="absolute inset-0 cursor-pointer opacity-0" multiple onChange={onFiles} type="file" />
            </label>

            <Textarea
              aria-label={language === "vi" ? "Nhập câu hỏi lâm sàng" : "Enter clinical question"}
              className="min-h-11 max-h-40 flex-1 resize-none border-0 bg-transparent px-1 shadow-none focus-visible:ring-0"
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

            <Button
              aria-label={language === "vi" ? "Gửi tin nhắn" : "Send message"}
              className="shrink-0 rounded-xl"
              disabled={loading || !chatInput.trim()}
              size="icon"
              type="submit"
            >
              <ArrowUp size={18} />
            </Button>
          </div>
        </Card>
        <p className="mx-auto mt-2 max-w-3xl text-center text-xs text-muted-foreground">
          {language === "vi"
            ? "HF CDSS hỗ trợ quyết định lâm sàng — không thay thế đánh giá của bác sĩ."
            : "HF CDSS supports clinical decisions — not a substitute for physician judgment."}
        </p>
        {loading && streamStatus && (
          <div className="mx-auto mt-2 flex max-w-3xl justify-center">
            <Badge variant="secondary">{streamStatus}</Badge>
          </div>
        )}
      </form>
    </section>
  );
}
