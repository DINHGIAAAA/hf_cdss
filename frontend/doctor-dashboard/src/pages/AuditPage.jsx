import { useState } from "react";
import { ClipboardList, LoaderCircle, Search } from "lucide-react";

import { adminApi } from "../api/index.js";

export function AuditPage() {
  const [caseId, setCaseId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function handleSearch(event) {
    event.preventDefault();
    const normalized = caseId.trim();
    if (!normalized) return;

    setLoading(true);
    setError("");
    try {
      const data = await adminApi.auditByCase(normalized);
      setResult(data);
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-header">
        <div>
          <h1>
            <ClipboardList size={24} />
            Audit log
          </h1>
          <p>Search recommendation and pipeline audit events by case ID.</p>
        </div>
      </header>

      <form className="search-bar" onSubmit={handleSearch}>
        <Search size={18} />
        <input
          placeholder="Case ID (e.g. AUTH_CASE)"
          value={caseId}
          onChange={(e) => setCaseId(e.target.value)}
        />
        <button className="primary-btn" disabled={loading || !caseId.trim()} type="submit">
          Search
        </button>
      </form>

      {error && <p className="admin-banner danger">{error}</p>}

      {loading && (
        <div className="admin-empty" aria-busy="true">
          <LoaderCircle className="spin" size={24} />
          Loading audit events...
        </div>
      )}

      {result && !loading && (
        <section className="admin-section">
          <h2>
            Case <code>{result.case_id}</code>
            {result.status && <small> · {result.status}</small>}
          </h2>
          {(result.events || []).length === 0 ? (
            <p className="admin-empty">No audit events found for this case.</p>
          ) : (
            <table className="admin-table compact admin-table--audit">
              <colgroup>
                <col className="col-time" />
                <col className="col-type" />
                <col className="col-payload" />
              </colgroup>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Type</th>
                  <th>Payload</th>
                </tr>
              </thead>
              <tbody>
                {result.events.map((event) => (
                  <tr key={event.id}>
                    <td className="cell-ellipsis">{new Date(event.created_at).toLocaleString()}</td>
                    <td className="cell-ellipsis" title={event.event_type}>{event.event_type}</td>
                    <td className="cell-wrap">
                      <pre className="audit-payload">{JSON.stringify(event.payload, null, 2)}</pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
