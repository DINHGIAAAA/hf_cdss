import { CheckCircle2, AlertTriangle, MessageSquareText, Plus } from "lucide-react";
import { patientSummary } from "../utils";

export function Sidebar({ conversations, activeId, onSelect, onNew, health, open }) {
  return (
    <aside className={`conversation-sidebar${open ? "" : " sidebar--collapsed"}`}>
      <div className="brand">
        <MessageSquareText size={21} />
        {open && <strong>HF CDSS</strong>}
      </div>

      <button className="new-chat" onClick={onNew} type="button" title="New conversation">
        <Plus size={17} />
        {open && "New conversation"}
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

      <div className={`api-status ${health}`} title={`API ${health}`}>
        {health === "ok" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
        {open && <span>API {health}</span>}
      </div>
    </aside>
  );
}
