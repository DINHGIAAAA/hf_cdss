import { useState } from "react";
import { ExternalLink, FileSearch, LoaderCircle, Search } from "lucide-react";

import { evidenceApi } from "../api/index.js";
import {
  evidenceDocumentTitle,
  evidenceMatchPercent,
  evidenceReadableFacts,
  evidenceSectionLabel,
  evidenceSourceTypeLabel,
  repairEvidenceText,
} from "@shared/evidenceDisplay.js";

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
  const activeFacts = activeChunk ? evidenceReadableFacts(activeChunk) : [];
  const activeMatch = activeChunk ? evidenceMatchPercent(activeChunk) : null;

  return (
    <div className="admin-page">
      <header className="admin-page-header">
        <div>
          <h1>Evidence</h1>
          <p>Search guideline and drug-label passages that support clinical recommendations.</p>
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
          <p>Find readable source passages with page and publisher details — no technical IDs.</p>
        </div>
      )}

      {result && (
        <div className="evidence-layout">
          <section className="evidence-meta">
            <p>
              <strong>{chunks.length}</strong> passages found
            </p>
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
                    <strong>{evidenceDocumentTitle(chunk)}</strong>
                    <span>
                      {[evidenceSourceTypeLabel(chunk), evidenceMatchPercent(chunk) != null ? `${evidenceMatchPercent(chunk)}% match` : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                    <small>{repairEvidenceText(chunk.text).slice(0, 140)}…</small>
                  </button>
                </li>
              ))}
              {chunks.length === 0 && <li className="admin-empty">No passages returned for this query.</li>}
            </ul>

            {activeChunk && (
              <article className="chunk-detail">
                <header>
                  <h2>{evidenceDocumentTitle(activeChunk)}</h2>
                  <p>
                    {[evidenceSectionLabel(activeChunk), evidenceSourceTypeLabel(activeChunk)]
                      .filter(Boolean)
                      .join(" · ") || "Clinical source"}
                    {activeMatch != null ? ` · ${activeMatch}% match` : ""}
                  </p>
                </header>
                <p className="chunk-text">{repairEvidenceText(activeChunk.text)}</p>
                {activeFacts.length ? (
                  <ul className="evidence-fact-chips">
                    {activeFacts.map((fact) => (
                      <li key={fact.key}>
                        <span>
                          {fact.key === "type"
                            ? "Type"
                            : fact.key === "page"
                              ? "Page"
                              : fact.key === "publisher"
                                ? "Publisher"
                                : fact.key === "year"
                                  ? "Year"
                                  : fact.key}
                        </span>{" "}
                        {fact.value}
                      </li>
                    ))}
                  </ul>
                ) : null}
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
