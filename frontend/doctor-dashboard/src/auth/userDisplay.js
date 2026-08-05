export function profileLabel(user) {
  const name = user?.display_name?.trim();
  if (name) return name;
  return user?.username || user?.id || "Profile";
}

export function profileInitial(user) {
  return profileLabel(user).slice(0, 1).toUpperCase();
}

export function formatRole(role) {
  return String(role)
    .split("_")
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1) : ""))
    .join(" ");
}

export function roleSummary(user) {
  const roles = user?.roles || [];
  if (!roles.length) return "";
  return roles.map(formatRole).join(", ");
}

/** Login identifier (unchanged when display name is updated). */
export function loginId(user) {
  return user?.username || user?.id || "";
}

export function usesDisplayName(user) {
  const name = user?.display_name?.trim();
  return Boolean(name && name !== loginId(user));
}
