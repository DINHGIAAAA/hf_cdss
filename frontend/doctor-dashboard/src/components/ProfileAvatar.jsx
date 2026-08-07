import { apiUrl } from "@shared/api/client.js";

import { profileInitial } from "../auth/userDisplay";

export function userAvatarSrc(user, { cacheBust } = {}) {
  if (!user?.avatar_url) return null;
  const base = apiUrl(user.avatar_url);
  const version = cacheBust ?? user.avatar_version;
  if (!version) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}v=${encodeURIComponent(version)}`;
}

export function ProfileAvatar({ user, className = "", size = "default", previewSrc = null }) {
  const src = previewSrc || userAvatarSrc(user);
  const sizeClass =
    size === "hero" ? "profile-avatar--hero" : size === "sidebar" ? "profile-avatar--sidebar" : "";

  return (
    <span className={`profile-avatar ${sizeClass} ${className}`.trim()} aria-hidden={size !== "hero"}>
      {src ? (
        <img alt="" className="profile-avatar-img" decoding="async" src={src} />
      ) : (
        <span className="profile-avatar-fallback">{profileInitial(user)}</span>
      )}
    </span>
  );
}
