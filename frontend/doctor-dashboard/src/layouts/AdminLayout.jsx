import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Activity,
  ClipboardList,
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
  Users,
} from "lucide-react";

import { useAuth } from "../auth/AuthContext";
import { profileLabel, roleSummary } from "../auth/userDisplay";
import { ProfileAvatar } from "../components/ProfileAvatar";

const NAV_ITEMS = [
  { to: "/admin/rules", label: "Constraints", icon: ShieldCheck },
  { to: "/admin/dose-rules", label: "Dose rules", icon: Pill },
  { to: "/admin/dose-safety-warnings", label: "Dose safety", icon: ShieldAlert },
  { to: "/admin/interaction-rules", label: "Interactions", icon: Link2 },
  { to: "/admin/gdmt-policies", label: "GDMT policies", icon: HeartPulse },
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
          <Sparkles size={22} />
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

          <NavLink
            className={({ isActive }) => `admin-user-btn${isActive ? " active" : ""}`}
            title="Profile & password"
            to="/admin/profile"
          >
            <ProfileAvatar size="sidebar" user={user} />
            <span className="admin-user-info">
              <strong>{profileLabel(user)}</strong>
              {roleSummary(user) ? <span>{roleSummary(user)}</span> : null}
            </span>
          </NavLink>
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
