import { useEffect, useRef, useState } from "react";
import { Camera, KeyRound, LoaderCircle, Trash2, UserCircle } from "lucide-react";

import { deleteMyAvatar, updateMyProfile, uploadMyAvatar } from "@shared/api/client.js";

import { useAuth } from "../auth/AuthContext";
import { ProfileAvatar } from "../components/ProfileAvatar";
import {
  loginId,
  profileLabel,
  roleSummary,
  usesDisplayName,
} from "../auth/userDisplay";

const MAX_AVATAR_BYTES = 900_000;
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];

export function ProfilePage() {
  const { user, refreshSession } = useAuth();
  const fileInputRef = useRef(null);
  const [displayName, setDisplayName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [avatarPreview, setAvatarPreview] = useState(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setDisplayName(user?.display_name || "");
  }, [user?.display_name, user?.id]);

  useEffect(() => {
    return () => {
      if (avatarPreview) URL.revokeObjectURL(avatarPreview);
    };
  }, [avatarPreview]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setToast("");

    const trimmedName = displayName.trim();
    const nameChanged = trimmedName !== (user?.display_name || "");
    const wantsPassword = Boolean(newPassword || confirmPassword || currentPassword);

    if (wantsPassword) {
      if (!currentPassword) {
        setError("Enter your current password to set a new one.");
        return;
      }
      if (newPassword.length < 8) {
        setError("New password must be at least 8 characters.");
        return;
      }
      if (newPassword !== confirmPassword) {
        setError("New password and confirmation do not match.");
        return;
      }
    }

    if (!nameChanged && !wantsPassword) {
      setToast("No changes to save.");
      return;
    }

    const payload = {};
    if (nameChanged) {
      payload.display_name = trimmedName || null;
    }
    if (wantsPassword) {
      payload.current_password = currentPassword;
      payload.new_password = newPassword;
    }

    setSaving(true);
    try {
      await updateMyProfile(payload);
      await refreshSession();
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setToast("Profile updated.");
    } catch (err) {
      setError(err.message || "Could not update profile.");
    } finally {
      setSaving(false);
    }
  }

  async function handleAvatarFile(file) {
    if (!file) return;
    setError("");
    setToast("");

    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError("Use a JPEG, PNG, or WebP image.");
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setError("Image must be 900 KB or smaller.");
      return;
    }

    const preview = URL.createObjectURL(file);
    setAvatarPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return preview;
    });

    setAvatarBusy(true);
    try {
      await uploadMyAvatar(file);
      await refreshSession();
      setToast("Profile photo updated.");
    } catch (err) {
      setError(err.message || "Could not upload photo.");
      setAvatarPreview((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    } finally {
      setAvatarBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleRemoveAvatar() {
    if (!user?.avatar_url) return;
    setError("");
    setToast("");
    setAvatarBusy(true);
    try {
      await deleteMyAvatar();
      await refreshSession();
      setAvatarPreview((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setToast("Profile photo removed.");
    } catch (err) {
      setError(err.message || "Could not remove photo.");
    } finally {
      setAvatarBusy(false);
    }
  }

  const visibleName = profileLabel(user);
  const roles = roleSummary(user);
  const signInId = loginId(user);

  return (
    <div className="admin-page admin-page--profile">
      <header className="profile-hero">
        <div className="profile-hero-avatar-wrap">
          <ProfileAvatar previewSrc={avatarPreview} size="hero" user={user} />
          {avatarBusy ? (
            <span aria-live="polite" className="profile-hero-avatar-busy">
              <LoaderCircle className="spin" size={22} />
            </span>
          ) : null}
        </div>

        <div className="profile-hero-photo-actions">
          <input
            ref={fileInputRef}
            accept={ACCEPTED_TYPES.join(",")}
            className="profile-avatar-input"
            onChange={(e) => handleAvatarFile(e.target.files?.[0])}
            type="file"
          />
          <button
            className="profile-photo-btn"
            disabled={avatarBusy}
            onClick={() => fileInputRef.current?.click()}
            type="button"
          >
            <Camera size={16} />
            {user?.avatar_url || avatarPreview ? "Change photo" : "Upload photo"}
          </button>
          {user?.avatar_url ? (
            <button
              className="profile-photo-btn profile-photo-btn--danger"
              disabled={avatarBusy}
              onClick={handleRemoveAvatar}
              type="button"
            >
              <Trash2 size={16} />
              Remove
            </button>
          ) : null}
        </div>
        <p className="profile-hero-photo-hint">JPEG, PNG, or WebP · max 900 KB</p>

        <h1>{visibleName}</h1>
        <div className="profile-hero-meta">
          {roles ? <span className="profile-role-pill">{roles}</span> : null}
          <span className="profile-login-id">
            Sign-in ID <code>{signInId}</code>
          </span>
        </div>
        {usesDisplayName(user) ? (
          <p className="profile-hero-note">
            Your display name appears in the sidebar. The sign-in ID is only used when you log in.
          </p>
        ) : (
          <p className="profile-hero-note">
            Set a display name below to show your name instead of <code>{signInId}</code> in the app.
          </p>
        )}
      </header>

      <div className="profile-stack">
        {toast ? <div className="admin-toast profile-feedback">{toast}</div> : null}
        {error ? <div className="admin-banner danger profile-feedback">{error}</div> : null}

        <form className="profile-form" onSubmit={handleSubmit}>
          <section className="profile-section">
            <h2>
              <UserCircle aria-hidden size={18} />
              Personal information
            </h2>
            <div className="form-group">
              <label htmlFor="profile-display-name">Display name</label>
              <input
                autoComplete="name"
                id="profile-display-name"
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Your name"
                type="text"
                value={displayName}
              />
            </div>
            <dl className="profile-readonly-meta">
              <div>
                <dt>Sign-in ID</dt>
                <dd>
                  <code>{signInId}</code>
                </dd>
              </div>
            </dl>
          </section>

          <section className="profile-section">
            <h2>
              <KeyRound aria-hidden size={18} />
              Change password
            </h2>
            <div className="form-group">
              <label htmlFor="profile-current-password">Current password</label>
              <input
                autoComplete="current-password"
                id="profile-current-password"
                onChange={(e) => setCurrentPassword(e.target.value)}
                type="password"
                value={currentPassword}
              />
            </div>
            <div className="form-group">
              <label htmlFor="profile-new-password">New password</label>
              <input
                autoComplete="new-password"
                id="profile-new-password"
                minLength={8}
                onChange={(e) => setNewPassword(e.target.value)}
                type="password"
                value={newPassword}
              />
            </div>
            <div className="form-group">
              <label htmlFor="profile-confirm-password">Confirm new password</label>
              <input
                autoComplete="new-password"
                id="profile-confirm-password"
                minLength={8}
                onChange={(e) => setConfirmPassword(e.target.value)}
                type="password"
                value={confirmPassword}
              />
            </div>
            <p className="profile-hint">Leave password fields blank if you only update your display name.</p>
          </section>

          <div className="profile-actions">
            <button className="primary-action" disabled={saving} type="submit">
              {saving ? <LoaderCircle className="spin" size={16} /> : null}
              Save changes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
