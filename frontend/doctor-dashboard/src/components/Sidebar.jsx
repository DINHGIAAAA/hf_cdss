import { CheckCircle2, AlertTriangle, LayoutDashboard, LogOut, Plus, Sparkles } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { patientSummary } from "../utils";
import { LanguageToggle } from "./LanguageToggle";
import { useAuth } from "../auth/AuthContext";
import { isAdminUser } from "../auth/roles";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  health,
  open,
}) {
  const { user, logout } = useAuth();
  const { language, languages, setLanguage, t } = useLanguage();
  const navigate = useNavigate();
  const showAdminLink = isAdminUser(user);

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

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
          className={cn("w-full justify-start gap-2", !open && "h-9 w-9 justify-center px-0")}
          onClick={onNew}
          title={t("sidebar.newChat")}
          type="button"
          variant="secondary"
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
          {conversations.map((conv) => {
            const patient = patientSummary(conv.draft?.patient || conv.patient);
            const active = conv.id === activeId;
            const initial = (conv.name || patient?.name || "?").trim().charAt(0).toUpperCase();

            return (
              <button
                className={cn(
                  "w-full min-w-0 rounded-lg transition-colors hover:bg-sidebar-accent",
                  open ? "px-3 py-2 text-left" : "flex h-9 w-9 items-center justify-center p-0",
                  active && "bg-sidebar-accent text-sidebar-foreground",
                )}
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                title={`${conv.name} — ${patient?.name || ""}${patient?.age != null ? `, ${patient.age}` : ""}`}
                type="button"
              >
                {open ? (
                  <>
                    <strong className="block truncate text-sm font-medium">{conv.name}</strong>
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
                      active
                        ? "bg-primary text-primary-foreground"
                        : "bg-sidebar-accent text-sidebar-foreground/80",
                    )}
                  >
                    {initial}
                  </span>
                )}
              </button>
            );
          })}
        </div>
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

        <LanguageToggle
          className={open ? "w-full" : undefined}
          compact={!open}
          language={language}
          languages={languages}
          onChange={setLanguage}
        />

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
