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
    roles: payload.roles || [],
    expiresAt,
  };
}

export function readStoredAuthSession(getToken) {
  return parseAuthSession(getToken());
}
