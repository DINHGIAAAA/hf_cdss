import { CheckCircle2, AlertTriangle, LayoutDashboard, Plus, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { patientSummary } from "../utils";
import { LanguageToggle } from "./LanguageToggle";
import { useAuth } from "../auth/AuthContext";
import { isAdminUser } from "../auth/roles";

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  health,
  open,
  language,
  languages,
  onLanguageChange,
}) {
  const { user } = useAuth();
  const showAdminLink = isAdminUser(user);

  return (
    <aside className={`conversation-sidebar${open ? "" : " sidebar--collapsed"}`}>
      <div className="brand">
        <Sparkles size={18} />
        {open && <strong>HF CDSS</strong>}
      </div>

      <button className="new-chat" onClick={onNew} type="button" title="New conversation">
        <Plus size={18} />
        {open && (language === "vi" ? "Hội thoại mới" : "New chat")}
      </button>

      <nav className="conversation-list">
        {conversations.map((conv) => {
          const patient = patientSummary(conv.draft?.patient || conv.patient);
          return (
            <button
              className={conv.id === activeId ? "active" : ""}
              key={conv.id}
              onClick={() => onSelect(conv.id)}
              title={`${patient?.name} - ${patient?.age ?? "age ?"}`}
              type="button"
            >
              <strong>{conv.name}</strong>
              {open && (
                <span>{patient?.name} - {patient?.age ?? "age ?"}</span>
              )}
            </button>
          );
        })}
      </nav>

      {showAdminLink && (
        <Link className="admin-link" title="Admin dashboard" to="/admin/rules">
          <LayoutDashboard size={17} />
          {open && "Admin dashboard"}
        </Link>
      )}

      <LanguageToggle
        compact={!open}
        language={language}
        languages={languages}
        onChange={onLanguageChange}
      />

      <div className={`api-status ${health}`} title={`API ${health}`}>
        {health === "ok" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
        {open && <span>API {health}</span>}
      </div>
    </aside>
  );
}
