import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Activity,
  BookOpen,
  FileSearch,
  HeartPulse,
  Sparkles,
  Link2,
  LogOut,
  MessageSquareText,
  Network,
  Pill,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import { useAuth } from "../auth/AuthContext";

const DOCTOR_DASHBOARD_URL = import.meta.env.VITE_DOCTOR_DASHBOARD_URL ?? "http://127.0.0.1:5173";

const NAV_ITEMS = [
  { to: "/rules", label: "Constraints", icon: ShieldCheck },
  { to: "/dose-rules", label: "Dose rules", icon: Pill },
  { to: "/dose-safety-warnings", label: "Dose safety", icon: ShieldAlert },
  { to: "/interaction-rules", label: "Interactions", icon: Link2 },
  { to: "/gdmt-policies", label: "GDMT policies", icon: HeartPulse },
  { to: "/evidence", label: "Evidence", icon: FileSearch },
  { to: "/system", label: "System", icon: Activity },
  { to: "/api", label: "API Explorer", icon: Network },
];

export function AdminLayout() {
  const { user, logout, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <Sparkles size={22} />
          <div>
            <strong>HF CDSS Admin</strong>
            <span>Clinical knowledge governance</span>
          </div>
        </div>

        <nav aria-label="Admin navigation" className="admin-nav">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              className={({ isActive }) => `admin-nav-link${isActive ? " active" : ""}`}
              key={to}
              to={to}
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="admin-sidebar-footer">
          <a className="admin-nav-link" href={DOCTOR_DASHBOARD_URL}>
            <MessageSquareText size={18} />
            Clinical chat
          </a>

          {isAuthenticated ? (
            <>
              <div className="admin-user" title={user?.id}>
                <BookOpen size={16} />
                <span>{user?.id}</span>
                <small>{(user?.roles || []).join(", ")}</small>
              </div>
              <button className="admin-logout" onClick={handleLogout} type="button">
                <LogOut size={16} />
                Sign out
              </button>
            </>
          ) : (
            <NavLink className="admin-nav-link" to="/login">
              Sign in
            </NavLink>
          )}
        </div>
      </aside>

      <div className="admin-main">
        <Outlet />
      </div>
    </div>
  );
}
