import { LoaderCircle } from "lucide-react";

import "./session-loading.css";

/**
 * Visible system status while auth/session is resolving (Nielsen #1).
 */
export function SessionLoading({
  title = "Checking session…",
  detail = "Connecting to the clinical API. This usually takes a few seconds.",
  error = "",
}) {
  return (
    <div aria-busy={error ? "false" : "true"} className="session-loading" role="status">
      {!error ? <LoaderCircle aria-hidden className="session-loading-spinner" size={28} /> : null}
      <p className="session-loading-title">{error || title}</p>
      {!error ? <p className="session-loading-detail">{detail}</p> : null}
      {error ? (
        <p className="session-loading-detail">
          Confirm the backend is running, then reload the page or sign in again.
        </p>
      ) : null}
    </div>
  );
}
