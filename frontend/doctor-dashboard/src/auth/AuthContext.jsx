import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { fetchCurrentUser, login as apiLogin, logout as apiLogout } from "@shared/api/client.js";

import { mapAuthUser } from "./session";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [bootstrapError, setBootstrapError] = useState("");

  const refreshSession = useCallback(async () => {
    try {
      const me = await fetchCurrentUser();
      setUser(mapAuthUser(me));
      setBootstrapError("");
      return mapAuthUser(me);
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setBootstrapError("");
      try {
        const me = await fetchCurrentUser();
        if (!cancelled) {
          setUser(mapAuthUser(me));
        }
      } catch (err) {
        if (!cancelled) {
          setUser(null);
          if (err?.name === "AbortError") {
            setBootstrapError("Session check timed out. The API may be starting or unreachable.");
          }
        }
      } finally {
        if (!cancelled) {
          setBootstrapping(false);
        }
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username, password) => {
    const data = await apiLogin(username, password);
    const nextUser = await refreshSession();
    return { ...data, user: nextUser };
  }, [refreshSession]);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
    }
  }, []);

  const clearSession = useCallback(() => {
    setUser(null);
  }, []);

  const hasRole = useCallback(
    (role) => Boolean(user?.roles?.includes(role)),
    [user],
  );

  const value = useMemo(
    () => ({
      user,
      bootstrapping,
      bootstrapError,
      isAuthenticated: Boolean(user),
      login,
      logout,
      clearSession,
      refreshSession,
      hasRole,
    }),
    [user, bootstrapping, bootstrapError, login, logout, clearSession, refreshSession, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
