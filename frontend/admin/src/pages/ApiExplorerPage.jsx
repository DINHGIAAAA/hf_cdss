import { useMemo, useState } from "react";
import { Check, Copy, LoaderCircle, Play, Search, Terminal } from "lucide-react";

import { auditApi, adminApi, kgApi, retrievalApi } from "../api/index.js";

const TOOLS = [
  {
    id: "dose-safety-warnings",
    label: "Active dose safety warnings",
    method: "GET",
    path: "/api/v1/admin/dose-safety-warnings/active",
    detail: "Approved warnings used by the dose checker.",
    run: () => adminApi.activeDoseSafetyWarnings(),
  },
  {
    id: "gdmt-policies",
    label: "Active GDMT policies",
    method: "GET",
    path: "/api/v1/admin/gdmt-policies/active",
    detail: "Approved policies used by /recommend.",
    run: () => adminApi.activeGdmtPolicies(),
  },
  {
    id: "interaction-rules",
    label: "Active interaction rules",
    method: "GET",
    path: "/api/v1/admin/interaction-rules/active",
    detail: "Approved rules used by the interaction checker.",
    run: () => adminApi.activeInteractionRules(),
  },
  {
    id: "dose-rules",
    label: "Active dose rules",
    method: "GET",
    path: "/api/v1/admin/dose-rules/active",
    detail: "Approved rules used by the dose calculator.",
    run: () => adminApi.activeDoseRules(),
  },
  {
    id: "rules",
    label: "Active rules",
    method: "GET",
    path: "/api/v1/admin/constraints/active",
    detail: "Published constraints used by the CDSS engine.",
    run: () => adminApi.activeRules(),
  },
  {
    id: "drug-classes",
    label: "Drug classes",
    method: "GET",
    path: "/api/v1/kg/drug-classes",
    detail: "Knowledge-graph drug class catalog.",
    run: () => kgApi.drugClasses(),
  },
  {
    id: "hfrec",
    label: "HFrEF recommendations",
    method: "GET",
    path: "/api/v1/kg/recommendations/HFrEF",
    detail: "Guideline recommendations for HFrEF.",
    run: () => kgApi.recommendations("HFrEF"),
  },
  {
    id: "retrieval",
    label: "Evidence search",
    method: "GET",
    path: "/api/v1/evidence/search",
    detail: "Semantic search over evidence chunks.",
    needsInput: true,
    inputLabel: "Query",
    inputDefault: "ACE inhibitor hyperkalemia",
    run: (value) => retrievalApi.search(value, 6),
  },
  {
    id: "interactions",
    label: "Drug interactions",
    method: "GET",
    path: "/api/v1/kg/interactions",
    detail: "Known interactions for a drug name.",
    needsInput: true,
    inputLabel: "Drug name",
    inputDefault: "warfarin",
    run: (value) => kgApi.interactions(value, 5),
  },
  {
    id: "audit",
    label: "Audit trail",
    method: "GET",
    path: "/api/v1/audit/{case_id}",
    detail: "Audit events for a case ID.",
    needsInput: true,
    inputLabel: "Case ID",
    inputDefault: "",
    run: (value) => auditApi.byCase(value || "demo-case"),
  },
];

export function ApiExplorerPage() {
  const [activeTool, setActiveTool] = useState(TOOLS[0].id);
  const [filter, setFilter] = useState("");
  const [inputValue, setInputValue] = useState(TOOLS[0].inputDefault || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [output, setOutput] = useState(null);
  const [elapsedMs, setElapsedMs] = useState(null);
  const [copied, setCopied] = useState(false);

  const tool = TOOLS.find((t) => t.id === activeTool) || TOOLS[0];
  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return TOOLS;
    return TOOLS.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.path.toLowerCase().includes(q) ||
        item.detail.toLowerCase().includes(q),
    );
  }, [filter]);

  async function runTool() {
    setLoading(true);
    setError("");
    setElapsedMs(null);
    const started = performance.now();
    try {
      const data = await tool.run(inputValue);
      setOutput(data);
      setElapsedMs(Math.round(performance.now() - started));
    } catch (err) {
      setError(err.message);
      setOutput(null);
      setElapsedMs(Math.round(performance.now() - started));
    } finally {
      setLoading(false);
    }
  }

  async function copyOutput() {
    if (!output) return;
    await navigator.clipboard.writeText(JSON.stringify(output, null, 2));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="admin-page api-explorer-page">
      <header className="admin-page-header">
        <div>
          <h1>API explorer</h1>
          <p>Try governance, KG, evidence, and audit routes from the dashboard.</p>
        </div>
      </header>

      <div className="api-explorer">
        <aside className="tool-panel">
          <label className="tool-filter">
            <Search aria-hidden size={16} />
            <input
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter endpoints"
              type="search"
              value={filter}
            />
          </label>

          <div className="tool-list" role="listbox" aria-label="API endpoints">
            {filtered.map((item) => (
              <button
                aria-selected={activeTool === item.id}
                className={activeTool === item.id ? "tool-item active" : "tool-item"}
                key={item.id}
                onClick={() => {
                  setActiveTool(item.id);
                  setInputValue(item.inputDefault || "");
                  setOutput(null);
                  setError("");
                  setElapsedMs(null);
                }}
                role="option"
                type="button"
              >
                <span className={`method-badge method-badge--${item.method.toLowerCase()}`}>
                  {item.method}
                </span>
                <span className="tool-item-body">
                  <strong>{item.label}</strong>
                  <code>{item.path}</code>
                </span>
              </button>
            ))}
            {filtered.length === 0 ? (
              <p className="tool-empty">No endpoints match “{filter}”.</p>
            ) : null}
          </div>
        </aside>

        <section className="tool-runner">
          <div className="tool-runner-head">
            <div>
              <h2>{tool.label}</h2>
              <p>{tool.detail}</p>
            </div>
          </div>

          <div className="request-bar" aria-label="Request">
            <span className={`method-badge method-badge--${tool.method.toLowerCase()}`}>
              {tool.method}
            </span>
            <span className="request-path">{tool.path}</span>
          </div>

          {tool.needsInput ? (
            <label className="tool-input">
              {tool.inputLabel}
              <input
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") runTool();
                }}
                type="text"
                value={inputValue}
              />
            </label>
          ) : null}

          <div className="tool-actions">
            <button className="primary-action" disabled={loading} onClick={runTool} type="button">
              {loading ? <LoaderCircle className="spin" size={16} aria-hidden /> : <Play size={16} aria-hidden />}
              {loading ? "Running…" : "Run request"}
            </button>
          </div>

          {error ? (
            <p className="inline-error" role="alert">
              {error}
            </p>
          ) : null}

          <div className="api-response">
            <div className="api-response-bar">
              <div className="api-response-meta">
                <Terminal size={15} aria-hidden />
                <span>Response</span>
                {error ? <span className="status-pill status-pill--error">Error</span> : null}
                {!error && output ? <span className="status-pill status-pill--ok">OK</span> : null}
                {elapsedMs != null ? <span className="api-timing">{elapsedMs} ms</span> : null}
              </div>
              <button
                className="ghost-action"
                disabled={!output}
                onClick={copyOutput}
                type="button"
              >
                {copied ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <pre aria-label="API response" className={`api-output${output || error ? "" : " api-output--empty"}`}>
              {output
                ? JSON.stringify(output, null, 2)
                : error
                  ? error
                  : "Run a request to see JSON here."}
            </pre>
          </div>
        </section>
      </div>
    </div>
  );
}
