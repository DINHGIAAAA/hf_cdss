import { useState } from "react";
import { ExternalLink, FileSearch, LoaderCircle, Search } from "lucide-react";

import { evidenceApi } from "../api/index.js";

export function EvidencePage() {
  const [query, setQuery] = useState("heart failure SGLT2 inhibitor");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [activeChunkId, setActiveChunkId] = useState(null);

  async function handleSearch(event) {
    event.preventDefault();
    const q = query.trim();
    if (q.length < 2) return;

    setLoading(true);
    setError("");
    setActiveChunkId(null);
    try {
      const data = await evidenceApi.search(q, 10);
      setResult(data);
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const chunks = result?.evidence_chunks || [];
  const activeChunk = chunks.find((c) => c.chunk_id === activeChunkId) || chunks[0];

  return (
    <div className="admin-page">
      <header className="admin-page-header">
        <div>
          <h1>Evidence chunks</h1>
          <p>Search and review indexed guideline and drug-label chunks before they inform recommendations.</p>
        </div>
      </header>

      <form className="search-bar" onSubmit={handleSearch}>
        <Search size={18} />
        <input
          aria-label="Evidence search query"
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. sacubitril contraindication, beta blocker bradycardia"
          type="search"
          value={query}
        />
        <button className="primary-action" disabled={loading || query.trim().length < 2} type="submit">
          {loading ? <LoaderCircle className="spin" size={16} /> : <FileSearch size={16} />}
          Search
        </button>
      </form>

      {error && <p className="inline-error" role="alert">{error}</p>}

      {!result && !loading && !error && (
        <div className="admin-empty" role="status">
          <h2>Search clinical evidence</h2>
          <p>Query the GraphRAG index to inspect chunk text, scores, and source links.</p>
        </div>
      )}

      {result && (
        <div className="evidence-layout">
          <section className="evidence-meta">
            <p>
              <strong>{chunks.length}</strong> chunks · sources: {(result.retrieval_sources || []).join(", ") || "—"}
            </p>
            {(result.graph_facts || []).length > 0 && (
              <details>
                <summary>{result.graph_facts.length} graph facts</summary>
                <ul>
                  {result.graph_facts.map((fact) => (
                    <li key={fact.fact_id}>
                      {fact.source_id} — {fact.relationship_type} — {fact.target_id}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>

          <div className="evidence-split">
            <ul className="chunk-list" role="list">
              {chunks.map((chunk) => (
                <li key={chunk.chunk_id}>
                  <button
                    className={activeChunk?.chunk_id === chunk.chunk_id ? "active" : ""}
                    onClick={() => setActiveChunkId(chunk.chunk_id)}
                    type="button"
                  >
                    <strong>{chunk.section || chunk.document_id}</strong>
                    <span>{chunk.source_type} · score {chunk.score?.toFixed(2)}</span>
                    <small>{chunk.text.slice(0, 120)}…</small>
                  </button>
                </li>
              ))}
              {chunks.length === 0 && <li className="admin-empty">No chunks returned for this query.</li>}
            </ul>

            {activeChunk && (
              <article className="chunk-detail">
                <header>
                  <h2>{activeChunk.section || activeChunk.document_id}</h2>
                  <p>
                    {activeChunk.chunk_id} · {activeChunk.source_type}
                    {activeChunk.evidence_level && ` · ${activeChunk.evidence_level}`}
                  </p>
                </header>
                <p className="chunk-text">{activeChunk.text}</p>
                <dl className="detail-grid">
                  <dt>Score</dt>
                  <dd>{activeChunk.score}</dd>
                  <dt>Page</dt>
                  <dd>{activeChunk.page ?? "—"}</dd>
                  <dt>Quality</dt>
                  <dd>{activeChunk.quality_score ?? "—"}</dd>
                </dl>
                {activeChunk.source_link && (
                  <a className="source-link" href={activeChunk.source_link} rel="noreferrer" target="_blank">
                    <ExternalLink size={14} /> Open source
                  </a>
                )}
              </article>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
