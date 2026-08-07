import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { LoaderCircle } from "lucide-react";

import { useAuth } from "../auth/AuthContext";

const DOCTOR_DASHBOARD_URL = import.meta.env.VITE_DOCTOR_DASHBOARD_URL ?? "http://127.0.0.1:5173";

export function LoginPage() {
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const redirectTo = location.state?.from || "/rules";

  if (isAuthenticated) {
    return <Navigate replace to={redirectTo} />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(username.trim(), password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-shell">
        <header className="login-hero">
          <div className="login-mark" aria-hidden>
            <span />
          </div>
          <h1>HF CDSS</h1>
          <p>Admin console</p>
        </header>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field">
            <label htmlFor="username">Username</label>
            <input
              autoComplete="username"
              autoFocus
              className="input"
              id="username"
              onChange={(e) => setUsername(e.target.value)}
              required
              type="text"
              value={username}
            />
          </div>

          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              autoComplete="current-password"
              className="input"
              id="password"
              onChange={(e) => setPassword(e.target.value)}
              required
              type="password"
              value={password}
            />
          </div>

          {error ? (
            <p className="login-error" role="alert">
              {error}
            </p>
          ) : null}

          <button className="login-submit" disabled={loading} type="submit">
            {loading ? <LoaderCircle className="spin" size={18} aria-hidden /> : null}
            {loading ? "Signing in…" : "Continue"}
          </button>
        </form>

        <a className="login-footer-link" href={DOCTOR_DASHBOARD_URL}>
          Clinical chat
        </a>
      </div>
    </div>
  );
}
