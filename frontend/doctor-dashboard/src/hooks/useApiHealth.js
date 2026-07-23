import { useEffect, useState } from "react";

import { apiFetch } from "@shared/api/client.js";

const CHECK_TIMEOUT_MS = 5000;
const POLL_INTERVAL_MS = 30_000;

async function probeHealth(signal) {
  const res = await apiFetch("/health", { signal });
  return res.ok ? "ok" : "degraded";
}

export function useApiHealth() {
  const [health, setHealth] = useState("checking");

  useEffect(() => {
    let cancelled = false;
    let timerId = null;

    async function check() {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), CHECK_TIMEOUT_MS);
      try {
        const next = await probeHealth(controller.signal);
        if (!cancelled) setHealth(next);
      } catch {
        if (!cancelled) setHealth("down");
      } finally {
        clearTimeout(timeoutId);
      }
    }

    check();
    timerId = setInterval(check, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (timerId) clearInterval(timerId);
    };
  }, []);

  return health;
}
