import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Activity,
  BookOpen,
  FileSearch,
  LayoutDashboard,
  LogOut,
  MessageSquareText,
  Network,
  ShieldCheck,
} from "lucide-react";

import { useAuth } from "../auth/AuthContext";

const NAV_ITEMS = [
  { to: "/admin/rules", label: "Rules", icon: ShieldCheck },
  { to: "/admin/evidence", label: "Evidence", icon: FileSearch },
  { to: "/admin/system", label: "System", icon: Activity },
  { to: "/admin/api", label: "API Explorer", icon: Network },
];

export function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <LayoutDashboard size={22} />
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
          <NavLink className="admin-nav-link" to="/chat">
            <MessageSquareText size={18} />
            Clinical chat
          </NavLink>

          <div className="admin-user" title={user?.id}>
            <BookOpen size={16} />
            <span>{user?.id}</span>
            <small>{(user?.roles || []).join(", ")}</small>
          </div>
          <button className="admin-logout" onClick={handleLogout} type="button">
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      </aside>

      <div className="admin-main">
        <Outlet />
      </div>
    </div>
  );
}
