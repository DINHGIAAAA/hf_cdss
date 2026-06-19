import { useEffect, useState } from "react";

import { apiUrl } from "@shared/api/client.js";

export function useApiHealth() {
  const [health, setHealth] = useState("checking");

  useEffect(() => {
    fetch(apiUrl("/health"))
      .then((res) => setHealth(res.ok ? "ok" : "degraded"))
      .catch(() => setHealth("down"));
  }, []);

  return health;
}
