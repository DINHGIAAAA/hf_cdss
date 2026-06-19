import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { LoaderCircle, LogIn, MessageSquareText, Shield } from "lucide-react";

import { useAuth } from "../auth/AuthContext";
import { resolvePostLoginPath, userFromAccessToken } from "../auth/roles";

export function LoginPage() {
  const { isAuthenticated, user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const redirectTo = resolvePostLoginPath(user, location.state?.from);

  if (isAuthenticated) {
    return <Navigate replace to={redirectTo} />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const data = await login(username.trim(), password);
      const nextUser = userFromAccessToken(data.access_token);
      navigate(resolvePostLoginPath(nextUser, location.state?.from), { replace: true });
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <Shield size={28} />
          <div>
            <h1>HF CDSS</h1>
            <p>Sign in for clinical chat. Admin and clinical lead accounts are routed to the governance dashboard.</p>
          </div>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="username">Username</label>
          <input
            autoComplete="username"
            id="username"
            onChange={(e) => setUsername(e.target.value)}
            placeholder="ngovinh"
            required
            type="text"
            value={username}
          />

          <label htmlFor="password">Password</label>
          <input
            autoComplete="current-password"
            id="password"
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            type="password"
            value={password}
          />

          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}

          <button className="primary-action" disabled={loading} type="submit">
            {loading ? <LoaderCircle className="spin" size={18} /> : <LogIn size={18} />}
            Sign in
          </button>
        </form>

        <p className="login-hint">
          Dev accounts are configured via <code>HF_CDSS_AUTH_DEV_USERS_JSON</code>.
        </p>

        <p className="login-hint login-hint--inline">
          <MessageSquareText size={16} />
          Clinical users continue to chat after sign-in. Admin users land on rule governance.
        </p>
      </div>
    </div>
  );
}
