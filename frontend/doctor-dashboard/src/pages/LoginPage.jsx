import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { LoaderCircle } from "lucide-react";

import { useAuth } from "../auth/AuthContext";
import { resolvePostLoginPath } from "../auth/roles";
import { LanguageToggle } from "../components/LanguageToggle";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function LoginPage() {
  const { isAuthenticated, user, login } = useAuth();
  const { language, languages, setLanguage, t } = useLanguage();
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
      const nextUser = data.user || user;
      navigate(resolvePostLoginPath(nextUser, location.state?.from), { replace: true });
    } catch (err) {
      setError(err.message || t("login.failed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-shell">
        <div className="login-lang">
          <LanguageToggle
            compact
            language={language}
            languages={languages}
            onChange={setLanguage}
            variant="light"
          />
        </div>

        <header className="login-hero">
          <div className="login-mark" aria-hidden>
            <span />
          </div>
          <h1>HF CDSS</h1>
          <p>{t("login.description")}</p>
        </header>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field">
            <label htmlFor="username">{t("login.username")}</label>
            <Input
              autoComplete="username"
              autoFocus
              id="username"
              onChange={(e) => setUsername(e.target.value)}
              required
              type="text"
              value={username}
            />
          </div>

          <div className="login-field">
            <label htmlFor="password">{t("login.password")}</label>
            <Input
              autoComplete="current-password"
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

          <Button className="login-submit" disabled={loading} size="lg" type="submit">
            {loading ? <LoaderCircle className="animate-spin" size={18} aria-hidden /> : null}
            {loading ? t("login.signingIn") : t("login.signIn")}
          </Button>
        </form>
      </div>
    </div>
  );
}
