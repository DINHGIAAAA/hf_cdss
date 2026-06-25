export function decodeJwtPayload(token) {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function parseAuthSession(token) {
  if (!token) return null;

  const payload = decodeJwtPayload(token);
  if (!payload?.sub) return null;

  const expiresAt = typeof payload.exp === "number" ? payload.exp * 1000 : null;
  if (expiresAt && Date.now() >= expiresAt) return null;

  return {
    id: payload.sub,
    username: payload.username || payload.preferred_username || null,
    display_name: payload.display_name || payload.name || null,
    roles: payload.roles || [],
    expiresAt,
  };
}

export function mapAuthUser(me) {
  if (!me?.id) return null;
  return {
    id: me.id,
    username: me.username,
    display_name: me.display_name ?? null,
    roles: me.roles || [],
  };
}

export function readStoredAuthSession(getToken) {
  return parseAuthSession(getToken());
}
