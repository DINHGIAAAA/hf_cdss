import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { getAuthToken, login as apiLogin, logout as apiLogout, setAuthToken } from "@shared/api/client.js";

const AuthContext = createContext(null);

function decodeJwtPayload(token) {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => getAuthToken());

  const user = useMemo(() => {
    if (!token) return null;
    const payload = decodeJwtPayload(token);
    if (!payload?.sub) return null;
    return {
      id: payload.sub,
      roles: payload.roles || [],
    };
  }, [token]);

  const login = useCallback(async (username, password) => {
    const data = await apiLogin(username, password);
    setToken(data.access_token);
    return data;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setToken(null);
  }, []);

  const clearSession = useCallback(() => {
    setAuthToken(null);
    setToken(null);
  }, []);

  const hasRole = useCallback(
    (role) => Boolean(user?.roles?.includes(role)),
    [user],
  );

  const value = useMemo(
    () => ({
      token,
      user,
      isAuthenticated: Boolean(token && user),
      login,
      logout,
      clearSession,
      hasRole,
    }),
    [token, user, login, logout, clearSession, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
