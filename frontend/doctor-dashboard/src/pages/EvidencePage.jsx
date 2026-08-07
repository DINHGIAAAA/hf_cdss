import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ExternalLink, FileSearch, LoaderCircle, Search } from "lucide-react";

import { adminApi } from "../api/index.js";
import { ResizableSplit } from "../components/ResizableSplit.jsx";
import { useDebouncedValue } from "../hooks/useDebouncedValue.js";
import {
  evidenceDocumentTitle,
  evidenceMatchPercent,
  evidenceReadableFacts,
  evidenceSectionLabel,
  evidenceSourceTypeLabel,
  repairEvidenceText,
} from "@/lib/evidenceDisplay";

const MIN_QUERY_LENGTH = 2;
const SEARCH_DEBOUNCE_MS = 350;

const FACT_LABELS = {
  type: "Type",
  page: "Page",
  publisher: "Publisher",
  year: "Year",
};

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
  const activeFacts = activeChunk ? evidenceReadableFacts(activeChunk) : [];
  const activeMatch = activeChunk ? evidenceMatchPercent(activeChunk) : null;

  return (
    <div className="admin-page admin-page--evidence">
      <header className="admin-page-header">
        <div>
          <h1>Evidence</h1>
          <p>Search guideline and drug-label passages that support clinical recommendations.</p>
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
            ? `${chunks.length} passages found in ${sourceLabel}.`
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
          <p>Results update as you type. Passages show source, page, and publisher — not technical IDs.</p>
        </div>
      )}

      {result && (
        <div aria-busy={loading} aria-live="polite" className="evidence-layout" id={resultsLiveId}>
          <section aria-label="Search summary" className="evidence-meta admin-clip">
            <p className="text-break">
              <strong>{chunks.length}</strong> passages · {sourceLabel}
            </p>
          </section>

          {chunks.length === 0 ? (
            <div className="admin-empty" role="status">
              No passages returned for &ldquo;{result.query}&rdquo; in {sourceLabel}.
            </div>
          ) : (
            <ResizableSplit
              ariaLabel="Resize passage list and detail"
              className="evidence-split"
              initial={320}
              list={
                <div aria-label="Evidence passages" role="tablist">
                  <ul className="chunk-list" role="presentation">
                    {chunks.map((chunk) => {
                      const selected = activeChunk?.chunk_id === chunk.chunk_id;
                      const match = evidenceMatchPercent(chunk);
                      return (
                        <li key={chunk.chunk_id} role="presentation">
                          <button
                            aria-selected={selected}
                            className={selected ? "active" : ""}
                            onClick={() => setActiveChunkId(chunk.chunk_id)}
                            role="tab"
                            title={evidenceDocumentTitle(chunk)}
                            type="button"
                          >
                            <strong>{evidenceDocumentTitle(chunk)}</strong>
                            <span>
                              {[
                                evidenceSourceTypeLabel(chunk),
                                match != null ? `${match}% match` : null,
                              ]
                                .filter(Boolean)
                                .join(" · ")}
                            </span>
                            <small>{repairEvidenceText(chunk.text)}</small>
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
                  <article aria-label="Passage detail" className="chunk-detail" role="tabpanel">
                    <header className="admin-clip">
                      <h2 title={evidenceDocumentTitle(activeChunk)}>
                        {evidenceDocumentTitle(activeChunk)}
                      </h2>
                      <p className="text-break">
                        {[evidenceSectionLabel(activeChunk), evidenceSourceTypeLabel(activeChunk)]
                          .filter(Boolean)
                          .join(" · ") || "Clinical source"}
                        {activeMatch != null ? ` · ${activeMatch}% match` : ""}
                      </p>
                    </header>
                    <div className="chunk-detail-body">
                      <p className="chunk-text">{repairEvidenceText(activeChunk.text)}</p>
                      {activeFacts.length ? (
                        <ul className="evidence-fact-chips">
                          {activeFacts.map((fact) => (
                            <li key={fact.key}>
                              <span>{FACT_LABELS[fact.key] || fact.key}</span> {fact.value}
                            </li>
                          ))}
                        </ul>
                      ) : null}
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
                  <div className="admin-empty">Select a passage to read the full text.</div>
                )
              }
            />
          )}
        </div>
      )}
    </div>
  );
}
