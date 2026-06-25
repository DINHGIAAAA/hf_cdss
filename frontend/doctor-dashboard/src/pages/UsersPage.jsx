import { useCallback, useEffect, useState } from "react";
import { LoaderCircle, Plus, RefreshCw, UserCog } from "lucide-react";

import { adminApi } from "../api/index.js";
import { useAuth } from "../auth/AuthContext";

const ROLE_OPTIONS = ["admin", "clinical_lead", "clinician", "viewer"];

const EMPTY_FORM = {
  username: "",
  password: "",
  display_name: "",
  roles: ["clinician"],
};

function emptyEditForm(user) {
  return {
    display_name: user?.display_name || "",
    password: "",
    roles: [...(user?.roles || [])],
  };
}

export function UsersPage() {
  const { hasRole, user: currentUser } = useAuth();
  const isAdmin = hasRole("admin");

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(EMPTY_FORM);
  const [editingUser, setEditingUser] = useState(null);
  const [editForm, setEditForm] = useState(emptyEditForm(null));
  const [saving, setSaving] = useState(false);

  const loadUsers = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    setError("");
    try {
      const result = await adminApi.listUsers();
      setItems(result.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  function toggleRoles(setter, role) {
    setter((current) => {
      const roles = new Set(current.roles);
      if (roles.has(role)) roles.delete(role);
      else roles.add(role);
      return { ...current, roles: [...roles] };
    });
  }

  async function handleCreate(event) {
    event.preventDefault();
    setSaving(true);
    setToast("");
    try {
      await adminApi.createUser({
        username: createForm.username.trim(),
        password: createForm.password,
        display_name: createForm.display_name.trim() || undefined,
        roles: createForm.roles,
      });
      setToast("User created.");
      setCreateForm(EMPTY_FORM);
      setShowCreate(false);
      await loadUsers();
    } catch (err) {
      setToast(err.message);
    } finally {
      setSaving(false);
    }
  }

  function startEdit(user) {
    setEditingUser(user);
    setEditForm(emptyEditForm(user));
    setShowCreate(false);
  }

  async function handleEdit(event) {
    event.preventDefault();
    if (!editingUser) return;
    setSaving(true);
    setToast("");
    try {
      const payload = {
        display_name: editForm.display_name.trim() || null,
        roles: editForm.roles,
      };
      if (editForm.password.trim()) {
        payload.password = editForm.password;
      }
      await adminApi.updateUser(editingUser.id, payload);
      setToast("User updated.");
      setEditingUser(null);
      await loadUsers();
    } catch (err) {
      setToast(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(user) {
    if (user.id === currentUser?.id) {
      setToast("You cannot deactivate your own account.");
      return;
    }
    setSaving(true);
    setToast("");
    try {
      await adminApi.updateUser(user.id, { is_active: !user.is_active });
      setToast(user.is_active ? "User deactivated." : "User reactivated.");
      await loadUsers();
    } catch (err) {
      setToast(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (!isAdmin) {
    return (
      <div className="admin-page">
        <div className="admin-banner warning" role="alert">
          Only <strong>admin</strong> accounts can manage users.
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <header className="admin-page-header">
        <div>
          <h1>
            <UserCog size={24} />
            Users
          </h1>
          <p>Create clinician accounts and manage roles for chat and admin access.</p>
        </div>
        <div className="admin-header-actions">
          <button className="ghost-btn" disabled={loading} onClick={loadUsers} type="button">
            <RefreshCw size={16} />
            Refresh
          </button>
          <button className="primary-btn" onClick={() => setShowCreate((open) => !open)} type="button">
            <Plus size={16} />
            New user
          </button>
        </div>
      </header>

      {showCreate && (
        <form className="user-form" onSubmit={handleCreate}>
          <h2>Create user</h2>
          <div className="user-form-grid">
            <label>
              Username
              <input
                required
                value={createForm.username}
                onChange={(e) => setCreateForm((f) => ({ ...f, username: e.target.value }))}
              />
            </label>
            <label>
              Password
              <input
                required
                minLength={8}
                type="password"
                value={createForm.password}
                onChange={(e) => setCreateForm((f) => ({ ...f, password: e.target.value }))}
              />
            </label>
            <label>
              Display name
              <input
                value={createForm.display_name}
                onChange={(e) => setCreateForm((f) => ({ ...f, display_name: e.target.value }))}
              />
            </label>
          </div>
          <fieldset className="role-picker">
            <legend>Roles</legend>
            {ROLE_OPTIONS.map((role) => (
              <label key={role}>
                <input
                  checked={createForm.roles.includes(role)}
                  type="checkbox"
                  onChange={() => toggleRoles(setCreateForm, role)}
                />
                {role}
              </label>
            ))}
          </fieldset>
          <div className="user-form-actions">
            <button className="primary-btn" disabled={saving} type="submit">
              {saving ? <LoaderCircle className="spin" size={16} /> : "Create"}
            </button>
            <button className="ghost-btn" onClick={() => setShowCreate(false)} type="button">
              Cancel
            </button>
          </div>
        </form>
      )}

      {editingUser && (
        <form className="user-form" onSubmit={handleEdit}>
          <h2>Edit {editingUser.username}</h2>
          <div className="user-form-grid">
            <label>
              Display name
              <input
                value={editForm.display_name}
                onChange={(e) => setEditForm((f) => ({ ...f, display_name: e.target.value }))}
              />
            </label>
            <label>
              New password
              <input
                minLength={8}
                placeholder="Leave blank to keep current"
                type="password"
                value={editForm.password}
                onChange={(e) => setEditForm((f) => ({ ...f, password: e.target.value }))}
              />
            </label>
          </div>
          <fieldset className="role-picker">
            <legend>Roles</legend>
            {ROLE_OPTIONS.map((role) => (
              <label key={role}>
                <input
                  checked={editForm.roles.includes(role)}
                  type="checkbox"
                  onChange={() => toggleRoles(setEditForm, role)}
                />
                {role}
              </label>
            ))}
          </fieldset>
          <div className="user-form-actions">
            <button className="primary-btn" disabled={saving} type="submit">
              {saving ? <LoaderCircle className="spin" size={16} /> : "Save changes"}
            </button>
            <button className="ghost-btn" onClick={() => setEditingUser(null)} type="button">
              Cancel
            </button>
          </div>
        </form>
      )}

      {error && <p className="admin-banner danger">{error}</p>}
      {toast && <p className="admin-toast" role="status">{toast}</p>}

      <section className="admin-table-panel">
        {loading ? (
          <div className="admin-empty" aria-busy="true">
            <LoaderCircle className="spin" size={24} />
            Loading users...
          </div>
        ) : items.length === 0 ? (
          <div className="admin-empty">No users found.</div>
        ) : (
          <table className="admin-table admin-table--users">
            <colgroup>
              <col className="col-username" />
              <col className="col-id" />
              <col className="col-roles" />
              <col className="col-status" />
              <col className="col-actions" />
            </colgroup>
            <thead>
              <tr>
                <th>Username</th>
                <th>ID</th>
                <th>Roles</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((user) => (
                <tr key={user.id}>
                  <td className="cell-ellipsis">
                    <strong title={user.username}>{user.username}</strong>
                    {user.display_name && <small title={user.display_name}>{user.display_name}</small>}
                  </td>
                  <td className="cell-wrap"><code>{user.id}</code></td>
                  <td className="cell-ellipsis" title={user.roles.join(", ")}>{user.roles.join(", ")}</td>
                  <td>
                    <span className={`status-pill ${user.is_active ? "success" : "danger"}`}>
                      {user.is_active ? "active" : "inactive"}
                    </span>
                  </td>
                  <td className="table-actions">
                    <button className="ghost-btn" disabled={saving} onClick={() => startEdit(user)} type="button">
                      Edit
                    </button>
                    <button
                      className="ghost-btn"
                      disabled={saving || user.id === currentUser?.id}
                      onClick={() => toggleActive(user)}
                      title={user.id === currentUser?.id ? "Cannot deactivate your own account" : undefined}
                      type="button"
                    >
                      {user.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
