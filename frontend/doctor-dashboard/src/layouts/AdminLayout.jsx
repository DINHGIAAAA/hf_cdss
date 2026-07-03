import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Activity,
  BookOpen,
  ClipboardList,
  FileSearch,
  LayoutDashboard,
  LogOut,
  MessageSquareText,
  Network,
  Pill,
  ShieldCheck,
  Users,
} from "lucide-react";

import { useAuth } from "../auth/AuthContext";

const NAV_ITEMS = [
  { to: "/admin/rules", label: "Constraints", icon: ShieldCheck },
  { to: "/admin/dose-rules", label: "Dose rules", icon: Pill },
  { to: "/admin/evidence", label: "Evidence", icon: FileSearch },
  { to: "/admin/audit", label: "Audit", icon: ClipboardList },
  { to: "/admin/system", label: "System", icon: Activity },
  { to: "/admin/api", label: "API Explorer", icon: Network },
];

export function AdminLayout() {
  const { user, logout, hasRole } = useAuth();
  const navigate = useNavigate();
  const navItems = [
    ...NAV_ITEMS,
    ...(hasRole("admin") ? [{ to: "/admin/users", label: "Users", icon: Users }] : []),
  ];

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
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              className={({ isActive }) => `admin-nav-link${isActive ? " active" : ""}`}
              key={to}
              title={label}
              to={to}
            >
              <Icon size={18} />
              <span className="admin-nav-label">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="admin-sidebar-footer">
          <NavLink className="admin-nav-link" title="Clinical chat" to="/chat">
            <MessageSquareText size={18} />
            <span className="admin-nav-label">Clinical chat</span>
          </NavLink>

          <div className="admin-user" title={user?.id}>
            <BookOpen size={16} />
            <span>{user?.username || user?.id}</span>
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
