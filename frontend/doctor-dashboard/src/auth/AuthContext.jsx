import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { getAuthToken, login as apiLogin, logout as apiLogout, setAuthToken } from "@shared/api/client.js";

import { parseAuthSession } from "./session";

const AuthContext = createContext(null);

function readInitialSession() {
  const token = getAuthToken();
  const user = parseAuthSession(token);
  if (token && !user) {
    setAuthToken(null);
    return { token: null, user: null };
  }
  return { token: user ? token : null, user };
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(readInitialSession);
  const { token, user } = session;

  const login = useCallback(async (username, password) => {
    const data = await apiLogin(username, password);
    const nextUser = parseAuthSession(data.access_token);
    if (!nextUser) {
      setAuthToken(null);
      throw new Error("Invalid session token");
    }
    setSession({ token: data.access_token, user: nextUser });
    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setAuthToken(null);
      setSession({ token: null, user: null });
    }
  }, []);

  const clearSession = useCallback(() => {
    setAuthToken(null);
    setSession({ token: null, user: null });
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
