import { useCallback, useEffect, useState } from "react";
import { Activity, CheckCircle2, LoaderCircle, RefreshCw, XCircle } from "lucide-react";

import { systemApi } from "../api/index.js";

function DependencyCard({ name, status }) {
  const ok = status?.status === "ok";
  return (
    <div className={`dep-card ${ok ? "ok" : "degraded"}`}>
      <div className="dep-card-head">
        {ok ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
        <strong>{name}</strong>
      </div>
      <p>{status?.status || "unknown"}</p>
      {status?.detail && <small>{status.detail}</small>}
      {status?.storage && <small>storage: {status.storage}</small>}
    </div>
  );
}

export function SystemPage() {
  const [health, setHealth] = useState(null);
  const [version, setVersion] = useState(null);
  const [dependencies, setDependencies] = useState(null);
  const [routes, setRoutes] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [healthData, versionData, depData, routesData] = await Promise.all([
        systemApi.health(),
        systemApi.version(),
        systemApi.dependencies(),
        systemApi.routes(),
      ]);
      setHealth(healthData);
      setVersion(versionData);
      setDependencies(depData);
      setRoutes(routesData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const deps = dependencies?.dependencies && typeof dependencies.dependencies === "object"
    ? dependencies.dependencies
    : {};

  return (
    <div className="admin-page">
      <header className="admin-page-header">
        <div>
          <h1>System health</h1>
          <p>Monitor API readiness, datastore bootstrap status, and registered routes.</p>
        </div>
        <button className="secondary-action" onClick={load} type="button">
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      {loading && (
        <div className="admin-empty" aria-busy="true">
          <LoaderCircle className="spin" size={24} /> Checking system...
        </div>
      )}

      {error && <p className="inline-error" role="alert">{error}</p>}

      {!loading && (
        <>
          <div className="admin-stats">
            <div className="stat-card">
              <span>API</span>
              <strong className={health?.status === "ok" ? "text-ok" : ""}>{health?.status || "—"}</strong>
            </div>
            <div className="stat-card">
              <span>Readiness</span>
              <strong className={dependencies?.status === "ok" ? "text-ok" : ""}>
                {dependencies?.status || "—"}
              </strong>
            </div>
            <div className="stat-card">
              <span>Version</span>
              <strong>{version?.version || "—"}</strong>
              <small>{version?.environment}</small>
            </div>
            <div className="stat-card">
              <span>Routes</span>
              <strong>{routes?.routes?.length ?? "—"}</strong>
            </div>
          </div>

          <section className="admin-section">
            <h2>
              <Activity size={18} /> Datastores
            </h2>
            <div className="dep-grid">
              {Object.entries(deps).map(([name, status]) => (
                <DependencyCard key={name} name={name} status={status} />
              ))}
              {Object.keys(deps).length === 0 && (
                <p className="admin-empty">Dependency details unavailable.</p>
              )}
            </div>
          </section>

          <section className="admin-section">
            <h2>Route catalog</h2>
            <div className="route-table-wrap">
              <table className="admin-table compact">
                <thead>
                  <tr>
                    <th>Path</th>
                    <th>Methods</th>
                    <th>Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {(routes?.routes || []).map((route) => (
                    <tr key={`${route.path}-${route.methods?.join(",")}`}>
                      <td><code>{route.path}</code></td>
                      <td>{(route.methods || []).join(", ")}</td>
                      <td>{(route.tags || []).join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
