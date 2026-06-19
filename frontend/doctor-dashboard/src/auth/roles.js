export const ADMIN_ROLES = ["admin", "clinical_lead"];

export function isAdminUser(user) {
  return Boolean(user?.roles?.some((role) => ADMIN_ROLES.includes(role)));
}

import { parseAuthSession } from "./session";

export function userFromAccessToken(token) {
  return parseAuthSession(token);
}

export function resolvePostLoginPath(user, from) {
  const adminHome = "/admin/rules";
  const chatHome = "/chat";

  if (from && from !== "/login" && from !== "/") {
    if (from.startsWith("/admin") && isAdminUser(user)) return from;
    if (!from.startsWith("/admin")) return from;
  }

  return isAdminUser(user) ? adminHome : chatHome;
}
