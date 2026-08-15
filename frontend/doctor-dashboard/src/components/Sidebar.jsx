import {
  CheckCircle2,
  AlertTriangle,
  Copy,
  LayoutDashboard,
  LogOut,
  MoreHorizontal,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useState, useRef, useEffect, useCallback } from "react";
import { patientSummary } from "../utils";
import { useAuth } from "../auth/AuthContext";
import { isAdminUser } from "../auth/roles";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function ConversationItem({
  conv,
  isActive,
  open,
  copyFeedbackId,
  editingId,
  editValue,
  editInputRef,
  onSelect,
  onStartEdit,
  onEditChange,
  onEditKeyDown,
  onCommitEdit,
  onCopyWithFeedback,
  onDelete,
  t,
}) {
  const patient = patientSummary(conv.draft?.patient || conv.patient);
  const displayName = conv.name || patient?.name || "Conversation";
  const isEditing = editingId === conv.id;

  return (
    <div
      className={cn(
        "group relative w-full min-w-0 rounded-lg transition-colors hover:bg-sidebar-accent",
        open ? "pr-1" : "",
        isActive && "bg-sidebar-accent text-sidebar-foreground",
      )}
    >
      {isEditing ? (
        <input
          ref={editInputRef}
          className={cn(
            "w-full rounded-lg bg-background px-3 py-2 pr-8 text-sm text-foreground outline-none ring-2 ring-ring ring-offset-1",
            open ? "block" : "hidden",
          )}
          value={editValue}
          onChange={onEditChange}
          onKeyDown={onEditKeyDown}
          onBlur={onCommitEdit}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <button
          className={cn(
            "w-full min-w-0 rounded-lg text-left transition-colors",
            open ? "px-3 py-2.5 pr-[4.75rem]" : "flex h-10 w-10 items-center justify-center p-0",
          )}
          onClick={() => onSelect(conv.id)}
          onDoubleClick={(e) => {
            e.preventDefault();
            onStartEdit(conv);
          }}
          title={`${displayName}${patient?.age != null ? `, ${patient.age}` : ""}`}
          type="button"
        >
          {open ? (
            <>
              <strong className="block truncate text-sm font-medium">{displayName}</strong>
              <span className="block truncate text-xs text-sidebar-foreground/70">
                {patient?.name || "—"}
                {patient?.age != null ? ` · ${patient.age}` : ""}
              </span>
            </>
          ) : (
            <span
              aria-hidden="true"
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "bg-sidebar-accent text-sidebar-foreground/80",
              )}
            >
              {(conv.name || patient?.name || "?").trim().charAt(0).toUpperCase()}
            </span>
          )}
        </button>
      )}

      {open && !isEditing ? (
        <div
          className={cn(
            "absolute top-1/2 right-1 flex -translate-y-1/2 items-center gap-0.5",
            "opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100",
            isActive && "opacity-100",
          )}
        >
            <Button
              aria-label={t("sidebar.renameChat")}
              className="h-7 w-7 shrink-0"
              onClick={(e) => {
                e.stopPropagation();
                onStartEdit(conv);
              }}
              size="icon-sm"
            title={t("sidebar.renameChat")}
            type="button"
            variant="ghost"
          >
            <Pencil size={12} />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                  aria-label="More actions"
                  className="h-7 w-7 shrink-0"
                  onClick={(e) => e.stopPropagation()}
                  size="icon-sm"
                title="More"
                type="button"
                variant="ghost"
              >
                <MoreHorizontal size={14} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              <DropdownMenuItem onClick={(e) => onCopyWithFeedback(e, conv.id)}>
                <Copy size={14} />
                {copyFeedbackId === conv.id ? t("sidebar.copied") : t("sidebar.copyChat")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={(e) => onDelete(e, conv.id)}
              >
                <Trash2 size={14} />
                {t("sidebar.deleteChat")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ) : null}

      {!open ? (
        <Button
          aria-label={t("sidebar.deleteChat")}
          className="absolute -top-1 -right-1 h-6 w-6 text-destructive hover:bg-destructive/15 hover:text-destructive"
          onClick={(e) => onDelete(e, conv.id)}
          size="icon-xs"
          title={t("sidebar.deleteChat")}
          type="button"
          variant="ghost"
        >
          <Trash2 size={10} />
        </Button>
      ) : null}
    </div>
  );
}

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  onCopy,
  health,
  open,
}) {
  const { user, logout } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const showAdminLink = isAdminUser(user);

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  function handleDelete(event, conversationId) {
    event.stopPropagation();
    if (!window.confirm(t("chat.deleteConfirm"))) return;
    onDelete?.(conversationId);
  }

  const [copyFeedbackId, setCopyFeedbackId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const editInputRef = useRef(null);

  const handleCopyWithFeedback = useCallback(
    async (event, conversationId) => {
      event.stopPropagation();
      await onCopy?.(conversationId);
      setCopyFeedbackId(conversationId);
      window.setTimeout(() => setCopyFeedbackId(null), 2000);
    },
    [onCopy],
  );

  const startEdit = useCallback((conv) => {
    setEditingId(conv.id);
    setEditValue(conv.name || patientSummary(conv.draft?.patient || conv.patient)?.name || "");
    setTimeout(() => editInputRef.current?.select(), 0);
  }, []);

  const commitEdit = useCallback(() => {
    if (editingId && editValue.trim()) {
      onRename?.(editingId, editValue.trim());
    }
    setEditingId(null);
    setEditValue("");
  }, [editingId, editValue, onRename]);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setEditValue("");
  }, []);

  // Commit on Enter, cancel on Escape
  const handleEditKeyDown = useCallback((e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commitEdit();
    } else if (e.key === "Escape") {
      cancelEdit();
    }
  }, [commitEdit, cancelEdit]);

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
    }
  }, [editingId]);

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground",
        open ? "w-full" : "w-full items-center",
      )}
    >
      <div className={cn("flex shrink-0 items-center gap-2 px-3 py-3", !open && "justify-center px-0")}>
        <Sparkles className="shrink-0 text-primary" size={18} />
        {open && <strong className="min-w-0 truncate text-sm">HF CDSS</strong>}
      </div>

      <div className={cn("shrink-0 px-2", !open && "px-1")}>
        <Button
          className={cn(
            "w-full justify-start gap-2 font-medium shadow-sm",
            !open && "h-10 w-10 justify-center px-0",
          )}
          onClick={onNew}
          title={t("sidebar.newChat")}
          type="button"
          variant={open ? "default" : "secondary"}
        >
          <Plus className="shrink-0" size={18} />
          {open && (
            <span className="min-w-0 truncate">
              {t("sidebar.newChat")}
            </span>
          )}
        </Button>
      </div>

      <nav
        aria-label="Conversations"
        className={cn(
          "mt-2 min-h-0 flex-1 overflow-y-auto overscroll-contain px-2",
          !open && "w-full px-1",
        )}
      >
        <div className="space-y-1">
          {conversations.map((conv) => (
            <ConversationItem
              conv={conv}
              copyFeedbackId={copyFeedbackId}
              editInputRef={editInputRef}
              editValue={editValue}
              editingId={editingId}
              isActive={conv.id === activeId}
              key={conv.id}
              onCommitEdit={commitEdit}
              onCopyWithFeedback={handleCopyWithFeedback}
              onDelete={handleDelete}
              onEditChange={(e) => setEditValue(e.target.value)}
              onEditKeyDown={handleEditKeyDown}
              onSelect={onSelect}
              onStartEdit={startEdit}
              open={open}
              t={t}
            />
          ))}
        </div>
        {copyFeedbackId ? (
          <p aria-live="polite" className="sr-only">
            {t("sidebar.copied")}
          </p>
        ) : null}
      </nav>

      <div className={cn("mt-auto shrink-0 space-y-2 p-2", !open && "w-full px-1")}>
        {showAdminLink && (
          <Link
            className={cn(
              "flex min-w-0 items-center gap-2 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/90 transition-colors hover:bg-sidebar-accent",
              !open && "h-9 w-9 justify-center px-0",
            )}
            title={t("sidebar.adminDashboard")}
            to="/admin/rules"
          >
            <LayoutDashboard className="shrink-0" size={17} />
            {open && <span className="truncate">{t("sidebar.adminDashboard")}</span>}
          </Link>
        )}

        <Separator className="bg-sidebar-border" />

        <div
          className={cn(
            "flex min-w-0 items-center gap-2 rounded-lg px-3 py-2 text-xs",
            health === "ok" ? "text-emerald-300" : "text-amber-300",
            !open && "h-9 w-9 justify-center px-0",
          )}
          title={t("sidebar.apiStatus", { status: health })}
        >
          {health === "ok" ? (
            <CheckCircle2 className="shrink-0" size={16} />
          ) : (
            <AlertTriangle className="shrink-0" size={16} />
          )}
          {open && <span className="truncate">{t("sidebar.apiStatus", { status: health })}</span>}
        </div>

        <Button
          className={cn("w-full justify-start gap-2", !open && "h-9 w-9 justify-center px-0")}
          onClick={handleLogout}
          title={t("sidebar.signOut")}
          type="button"
          variant="ghost"
        >
          <LogOut className="shrink-0" size={17} />
          {open && (
            <span className="min-w-0 truncate">
              {t("sidebar.signOut")}
            </span>
          )}
        </Button>
      </div>
    </aside>
  );
}
