import { useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  ClipboardList,
  LoaderCircle,
  MessageSquareQuote,
  Search,
  Stethoscope,
  UserRound,
} from "lucide-react";

import { auditApi } from "../api/index.js";
import {
  eventMeta,
  extractAnswer,
  extractPatientSnapshot,
  extractQuestion,
  formatTimestamp,
  truncate,
} from "../lib/chatAuditDisplay.js";

const PAGE_SIZE = 20;

function AuditRow({ item, expanded, onToggle }) {
  const payload = item.payload || {};
  const question = extractQuestion(payload);
  const answer = extractAnswer(payload);
  const chips = extractPatientSnapshot(payload.patient);
  const meta = eventMeta(item.event_type);
  const plan = payload.question_plan;

  return (
    <article className={`chat-audit-row${expanded ? " expanded" : ""}`}>
      <button
        aria-expanded={expanded}
        className="chat-audit-row-header"
        onClick={onToggle}
        type="button"
      >
        <span className="chat-audit-expand-icon" aria-hidden="true">
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </span>

        <div className="chat-audit-row-main">
          <div className="chat-audit-row-top">
            <span className={`chat-audit-badge tone-${meta.tone}`}>{meta.label}</span>
            <time dateTime={item.created_at}>{formatTimestamp(item.created_at)}</time>
            <code className="chat-audit-case-id" title="Case / conversation id">
              {item.case_id}
            </code>
          </div>
          <p className="chat-audit-question">{question}</p>
          {answer ? <p className="chat-audit-answer-preview">{truncate(answer, 220)}</p> : null}
          {chips.length > 0 && (
            <ul className="chat-audit-chips" role="list">
              {chips.map((chip) => (
                <li key={`${chip.key}-${chip.value}`}>
                  <span>{chip.key}</span> {chip.value}
                </li>
              ))}
            </ul>
          )}
        </div>
      </button>

      {expanded && (
        <div className="chat-audit-detail">
          <section className="chat-audit-panel">
            <header>
              <MessageSquareQuote size={16} />
              <h3>Clinician question</h3>
            </header>
            <p>{question}</p>
          </section>

          {chips.length > 0 && (
            <section className="chat-audit-panel">
              <header>
                <UserRound size={16} />
                <h3>Patient snapshot at detection</h3>
              </header>
              <dl className="chat-audit-kv-grid">
                {chips.map((chip) => (
                  <div key={`detail-${chip.key}`}>
                    <dt>{chip.key}</dt>
                    <dd>{chip.value}</dd>
                  </div>
                ))}
              </dl>
              {payload.patient && (
                <details className="chat-audit-json-details">
                  <summary>Full patient JSON</summary>
                  <pre>{JSON.stringify(payload.patient, null, 2)}</pre>
                </details>
              )}
            </section>
          )}

          {plan?.questions?.length > 0 && (
            <section className="chat-audit-panel">
              <header>
                <ClipboardList size={16} />
                <h3>Question plan</h3>
              </header>
              {plan.reasoning ? <p className="chat-audit-plan-reason">{plan.reasoning}</p> : null}
              <ol className="chat-audit-plan-list">
                {plan.questions.map((q, index) => (
                  <li key={`${q.text}-${index}`}>
                    <strong>Q{index + 1}.</strong> {q.text}
                    {q.required_field_ids?.length ? (
                      <span className="chat-audit-plan-fields">
                        Needs: {q.required_field_ids.join(", ")}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ol>
            </section>
          )}

          {payload.clinical_state && (
            <section className="chat-audit-panel">
              <header>
                <Stethoscope size={16} />
                <h3>Clinical state</h3>
              </header>
              <dl className="chat-audit-kv-grid">
                {payload.clinical_state.intent ? (
                  <div>
                    <dt>Intent</dt>
                    <dd>{payload.clinical_state.intent}</dd>
                  </div>
                ) : null}
                {payload.clinical_state.focus_drug ? (
                  <div>
                    <dt>Focus drug</dt>
                    <dd>{payload.clinical_state.focus_drug}</dd>
                  </div>
                ) : null}
                {payload.clinical_state.hf_type ? (
                  <div>
                    <dt>HF type</dt>
                    <dd>{payload.clinical_state.hf_type}</dd>
                  </div>
                ) : null}
              </dl>
            </section>
          )}

          {answer ? (
            <section className="chat-audit-panel chat-audit-panel-answer">
              <header>
                <MessageSquareQuote size={16} />
                <h3>Chatbot answer</h3>
                {payload.assistant?.model ? (
                  <span className="chat-audit-model">{payload.assistant.model}</span>
                ) : null}
              </header>
              <div className="chat-audit-answer-body">{answer}</div>
            </section>
          ) : null}

          {payload.missing_check?.missing_fields?.length ? (
            <section className="chat-audit-panel tone-warning">
              <header>
                <h3>Missing fields</h3>
              </header>
              <ul>
                {payload.missing_check.missing_fields.map((field) => (
                  <li key={field.field_id || field.label}>{field.label || field.field_id}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {payload.conflicts?.length ? (
            <section className="chat-audit-panel tone-danger">
              <header>
                <h3>Value conflicts</h3>
              </header>
              <ul>
                {payload.conflicts.map((conflict, index) => (
                  <li key={conflict.field_id || index}>
                    {conflict.field_id}: {conflict.existing_value} → {conflict.incoming_value}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      )}
    </article>
  );
}

export function ChatAuditPage() {
  const [query, setQuery] = useState("");
  const [caseFilter, setCaseFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [offset, setOffset] = useState(0);
  const [expandedId, setExpandedId] = useState(null);

  const load = useCallback(async (nextOffset = 0) => {
    setLoading(true);
    setError("");
    try {
      const data = await auditApi.listChat({
        q: query.trim() || undefined,
        caseId: caseFilter.trim() || undefined,
        limit: PAGE_SIZE,
        offset: nextOffset,
      });
      setResult(data);
      setOffset(nextOffset);
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [query, caseFilter]);

  useEffect(() => {
    load(0);
  }, [load]);

  function handleSearch(event) {
    event.preventDefault();
    setExpandedId(null);
    load(0);
  }

  const items = result?.items || [];
  const total = result?.total ?? 0;
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <div className="admin-page chat-audit-page">
      <header className="admin-page-header">
        <div>
          <h1>Chat audit log</h1>
          <p>
            Review clinician questions, patient context at detection time, and chatbot responses.
          </p>
        </div>
      </header>

      <form className="chat-audit-filters" onSubmit={handleSearch}>
        <div className="search-bar chat-audit-search">
          <Search size={18} />
          <input
            aria-label="Search questions or answers"
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search question, answer, or clinical intent…"
            type="search"
            value={query}
          />
        </div>
        <div className="chat-audit-case-filter">
          <label htmlFor="case-filter">Case ID</label>
          <input
            id="case-filter"
            onChange={(e) => setCaseFilter(e.target.value)}
            placeholder="Filter by case / conversation"
            type="search"
            value={caseFilter}
          />
        </div>
        <button className="primary-action" disabled={loading} type="submit">
          {loading ? <LoaderCircle className="spin" size={16} /> : <Search size={16} />}
          Search
        </button>
      </form>

      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}

      {result?.status && result.status !== "ok" && (
        <p className="admin-banner warning" role="status">
          Audit store: {result.status}
        </p>
      )}

      <div className="chat-audit-summary">
        <strong>{total}</strong> chat events
        {total > 0 ? (
          <span>
            {" "}
            · showing {pageStart}–{pageEnd}
          </span>
        ) : null}
      </div>

      {!loading && items.length === 0 && !error && (
        <div className="admin-empty" role="status">
          <h2>No chat audit events</h2>
          <p>Events appear after clinicians use the clinical chat.</p>
        </div>
      )}

      <div className="chat-audit-list" role="list">
        {items.map((item) => (
          <AuditRow
            expanded={expandedId === item.id}
            item={item}
            key={item.id}
            onToggle={() => setExpandedId((current) => (current === item.id ? null : item.id))}
          />
        ))}
      </div>

      {total > PAGE_SIZE && (
        <nav aria-label="Audit log pagination" className="chat-audit-pagination">
          <button
            className="secondary-action"
            disabled={!hasPrev || loading}
            onClick={() => load(offset - PAGE_SIZE)}
            type="button"
          >
            Previous
          </button>
          <span>
            Page {Math.floor(offset / PAGE_SIZE) + 1} of {Math.ceil(total / PAGE_SIZE)}
          </span>
          <button
            className="secondary-action"
            disabled={!hasNext || loading}
            onClick={() => load(offset + PAGE_SIZE)}
            type="button"
          >
            Next
          </button>
        </nav>
      )}
    </div>
  );
}
