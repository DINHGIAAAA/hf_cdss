import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { LoaderCircle, LogIn, MessageSquareText, Shield } from "lucide-react";

import { useAuth } from "../auth/AuthContext";
import { resolvePostLoginPath } from "../auth/roles";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

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
      const nextUser = data.user || user;
      navigate(resolvePostLoginPath(nextUser, location.state?.from), { replace: true });
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-b from-accent/40 to-background px-4 py-10">
      <Card className="w-full max-w-md border-border/80 shadow-lg">
        <CardHeader className="space-y-4">
          <div className="flex items-start gap-3">
            <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Shield size={24} />
            </div>
            <div className="space-y-1">
              <CardTitle className="text-2xl">HF CDSS</CardTitle>
              <CardDescription>
                Sign in for clinical chat. Admin and clinical lead accounts are routed to the governance dashboard.
              </CardDescription>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="username">Username</label>
              <Input
                autoComplete="username"
                id="username"
                onChange={(e) => setUsername(e.target.value)}
                placeholder="ngovinh"
                required
                type="text"
                value={username}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="password">Password</label>
              <Input
                autoComplete="current-password"
                id="password"
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                type="password"
                value={password}
              />
            </div>

            {error && (
              <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            <Button className="w-full" disabled={loading} size="lg" type="submit">
              {loading ? <LoaderCircle className="animate-spin" size={18} /> : <LogIn size={18} />}
              Sign in
            </Button>
          </form>

          <p className="mt-5 text-sm text-muted-foreground">
            Accounts are stored in PostgreSQL. Initial users can be seeded via{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">HF_CDSS_AUTH_SEED_USERS_JSON</code> on first bootstrap.
          </p>

          <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
            <MessageSquareText size={16} />
            Clinical users continue to chat after sign-in. Admin users land on rule governance.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
