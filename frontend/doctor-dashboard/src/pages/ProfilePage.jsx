import { useEffect, useRef, useState } from "react";
import { Camera, ChevronRight, LoaderCircle, Shield, Trash2, UserRound } from "lucide-react";

import { deleteMyAvatar, updateMyProfile, uploadMyAvatar } from "@shared/api/client.js";

import { useAuth } from "../auth/AuthContext";
import { ProfileAvatar } from "../components/ProfileAvatar";
import { ProfilePasswordField } from "../components/ProfilePasswordField";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
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
  const [passwordOpen, setPasswordOpen] = useState(false);
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
      setPasswordOpen(false);
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
  const passwordDirty = Boolean(currentPassword || newPassword || confirmPassword);
  const newPasswordOk = newPassword.length >= 8;
  const passwordsMatch = newPassword === confirmPassword && confirmPassword.length > 0;

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
          <div className="profile-form-grid">
            <section aria-labelledby="profile-identity-heading" className="profile-panel">
              <header className="profile-panel__head">
                <span aria-hidden className="profile-panel__icon">
                  <UserRound size={18} />
                </span>
                <div>
                  <p className="profile-panel__kicker" id="profile-identity-heading">
                    Identity
                  </p>
                  <p className="profile-panel__lede">How your name appears across the app.</p>
                </div>
              </header>
              <div className="profile-panel__body">
                <label className="profile-field-label" htmlFor="profile-display-name">
                  Display name
                </label>
                <Input
                  autoComplete="name"
                  className="profile-field-input"
                  id="profile-display-name"
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  type="text"
                  value={displayName}
                />
                <dl className="profile-signin-strip">
                  <dt>Sign-in ID</dt>
                  <dd>
                    <code>{signInId}</code>
                  </dd>
                </dl>
              </div>
            </section>

            <section aria-labelledby="profile-security-heading" className="profile-panel profile-panel--security">
              <header className="profile-panel__head">
                <span aria-hidden className="profile-panel__icon profile-panel__icon--muted">
                  <Shield size={18} />
                </span>
                <div className="profile-panel__head-text">
                  <p className="profile-panel__kicker" id="profile-security-heading">
                    Security
                  </p>
                  <p className="profile-panel__lede">Update your password when you are on a shared device.</p>
                </div>
              </header>

              <div className="profile-panel__body">
                <button
                  aria-expanded={passwordOpen}
                  className="profile-security-trigger"
                  onClick={() => setPasswordOpen((open) => !open)}
                  type="button"
                >
                  <span className="profile-security-trigger__title">Change password</span>
                  <span className="profile-security-trigger__meta">
                    {passwordDirty ? "Unsaved password fields" : "Optional — leave closed to only update your name"}
                  </span>
                  <ChevronRight
                    aria-hidden
                    className={passwordOpen ? "profile-security-trigger__chevron is-open" : "profile-security-trigger__chevron"}
                    size={18}
                  />
                </button>

                <div
                  aria-hidden={!passwordOpen}
                  className={passwordOpen ? "profile-security-drawer is-open" : "profile-security-drawer"}
                >
                  <ProfilePasswordField
                    autoComplete="current-password"
                    id="profile-current-password"
                    label="Current password"
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    value={currentPassword}
                  />
                  <div className="profile-password-row">
                    <ProfilePasswordField
                      aria-invalid={newPassword.length > 0 && !newPasswordOk}
                      autoComplete="new-password"
                      hint={newPassword.length > 0 && !newPasswordOk ? "Use at least 8 characters." : undefined}
                      id="profile-new-password"
                      label="New password"
                      minLength={8}
                      onChange={(e) => setNewPassword(e.target.value)}
                      value={newPassword}
                    />
                    <ProfilePasswordField
                      aria-invalid={confirmPassword.length > 0 && !passwordsMatch}
                      autoComplete="new-password"
                      hint={
                        confirmPassword.length > 0 && !passwordsMatch ? "Passwords do not match." : undefined
                      }
                      id="profile-confirm-password"
                      label="Confirm"
                      minLength={8}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      value={confirmPassword}
                    />
                  </div>
                  {newPasswordOk && passwordsMatch ? (
                    <p className="profile-password-ready" role="status">
                      Ready to save with your profile changes.
                    </p>
                  ) : null}
                </div>
              </div>
            </section>
          </div>

          <footer className="profile-form-footer">
            <Button disabled={saving} size="lg" type="submit">
              {saving ? <LoaderCircle className="spin" size={16} /> : null}
              Save changes
            </Button>
          </footer>
        </form>
      </div>
    </div>
  );
}
