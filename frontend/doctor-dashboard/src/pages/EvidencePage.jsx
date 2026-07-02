import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ExternalLink, FileSearch, LoaderCircle, Search } from "lucide-react";

import { adminApi } from "../api/index.js";
import { ResizableSplit } from "../components/ResizableSplit.jsx";
import { useDebouncedValue } from "../hooks/useDebouncedValue.js";

const MIN_QUERY_LENGTH = 2;
const SEARCH_DEBOUNCE_MS = 350;

export function EvidencePage() {
  const [query, setQuery] = useState("heart failure SGLT2 inhibitor");
  const [staging, setStaging] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [activeChunkId, setActiveChunkId] = useState(null);

  const debouncedQuery = useDebouncedValue(query.trim(), SEARCH_DEBOUNCE_MS);
  const abortRef = useRef(null);
  const resultsLiveId = useId();
  const statusLiveId = useId();

  const runSearch = useCallback(async (q, useStaging, signal) => {
    if (q.length < MIN_QUERY_LENGTH) {
      setResult(null);
      setError("");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");
    setActiveChunkId(null);
    try {
      const data = await adminApi.searchEvidence(q, 10, { staging: useStaging, signal });
      if (signal?.aborted) return;
      setResult(data);
    } catch (err) {
      if (signal?.aborted || err.name === "AbortError") return;
      setError(err.message);
      setResult(null);
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    runSearch(debouncedQuery, staging, controller.signal);
    return () => controller.abort();
  }, [debouncedQuery, staging, runSearch]);

  const chunks = result?.evidence_chunks || [];
  const activeChunk = chunks.find((c) => c.chunk_id === activeChunkId) || chunks[0];
  const sourceLabel = result?.source_set === "staging" ? "draft workspace" : "published index";
  const showEmptyPrompt = debouncedQuery.length < MIN_QUERY_LENGTH && !loading && !error;

  return (
    <div className="admin-page admin-page--evidence">
      <header className="admin-page-header">
        <div>
          <h1>Evidence chunks</h1>
          <p>Search and review indexed guideline and drug-label chunks before they inform recommendations.</p>
        </div>
      </header>

      <div className="search-bar" role="search">
        <Search size={18} aria-hidden="true" />
        <input
          aria-controls={resultsLiveId}
          aria-describedby={statusLiveId}
          aria-label="Evidence search query"
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. sacubitril contraindication, beta blocker bradycardia"
          type="search"
          value={query}
        />
        <label className="evidence-staging-toggle">
          <input
            checked={staging}
            onChange={(e) => setStaging(e.target.checked)}
            type="checkbox"
          />
          Draft workspace
        </label>
        <span aria-hidden="true" className="search-bar-status">
          {loading ? <LoaderCircle className="spin" size={16} /> : <FileSearch size={16} />}
        </span>
      </div>

      <p className="sr-only" id={statusLiveId}>
        {loading
          ? "Searching evidence index."
          : result
            ? `${chunks.length} chunks found in ${sourceLabel}.`
            : "Enter at least two characters to search."}
      </p>

      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}

      {showEmptyPrompt && (
        <div className="admin-empty" role="status">
          <h2>Search clinical evidence</h2>
          <p>Query the GraphRAG index to inspect chunk text, scores, and source links. Results update as you type.</p>
        </div>
      )}

      {result && (
        <div aria-busy={loading} aria-live="polite" className="evidence-layout" id={resultsLiveId}>
          <section aria-label="Search summary" className="evidence-meta admin-clip">
            <p className="text-break">
              <strong>{chunks.length}</strong> chunks · source: {sourceLabel} ·{" "}
              {(result.retrieval_sources || []).join(", ") || "—"}
            </p>
            {(result.graph_facts || []).length > 0 && (
              <details className="evidence-facts">
                <summary>{result.graph_facts.length} graph facts</summary>
                <ul>
                  {result.graph_facts.map((fact) => (
                    <li
                      className="text-clamp-2 text-break"
                      key={fact.fact_id}
                      title={`${fact.source_id} — ${fact.relationship_type} — ${fact.target_id}`}
                    >
                      {fact.source_id} — {fact.relationship_type} — {fact.target_id}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>

          {chunks.length === 0 ? (
            <div className="admin-empty" role="status">
              No chunks returned for &ldquo;{result.query}&rdquo; in {sourceLabel}.
            </div>
          ) : (
            <ResizableSplit
              ariaLabel="Resize chunk list and detail"
              className="evidence-split"
              initial={320}
              list={
                <div aria-label="Evidence chunks" role="tablist">
                  <ul className="chunk-list" role="presentation">
                    {chunks.map((chunk) => {
                      const selected = activeChunk?.chunk_id === chunk.chunk_id;
                      return (
                        <li key={chunk.chunk_id} role="presentation">
                          <button
                            aria-selected={selected}
                            className={selected ? "active" : ""}
                            onClick={() => setActiveChunkId(chunk.chunk_id)}
                            role="tab"
                            title={chunk.section || chunk.document_id}
                            type="button"
                          >
                            <strong>{chunk.section || chunk.document_id}</strong>
                            <span>
                              {chunk.source_type} · score {chunk.score?.toFixed(2)}
                            </span>
                            <small>{chunk.text}</small>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              }
              listMax={560}
              listMin={220}
              storageKey="hf_admin_evidence_split"
              detail={
                activeChunk ? (
                  <article aria-label="Chunk detail" className="chunk-detail" role="tabpanel">
                    <header className="admin-clip">
                      <h2 title={activeChunk.section || activeChunk.document_id}>
                        {activeChunk.section || activeChunk.document_id}
                      </h2>
                      <p className="text-break">
                        {activeChunk.chunk_id} · {activeChunk.source_type}
                        {activeChunk.evidence_level && ` · ${activeChunk.evidence_level}`}
                      </p>
                    </header>
                    <div className="chunk-detail-body">
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
                        <a
                          className="source-link text-break"
                          href={activeChunk.source_link}
                          rel="noreferrer"
                          target="_blank"
                        >
                          <ExternalLink size={14} /> Open source
                        </a>
                      )}
                    </div>
                  </article>
                ) : (
                  <div className="admin-empty">Select a chunk to inspect full text.</div>
                )
              }
            />
          )}
        </div>
      )}
    </div>
  );
}
