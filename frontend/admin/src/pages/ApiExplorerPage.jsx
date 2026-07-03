import { useState } from "react";
import { LoaderCircle, Play, Search } from "lucide-react";

import { auditApi, adminApi, kgApi, retrievalApi } from "../api/index.js";

const TOOLS = [
  {
    id: "gdmt-policies",
    label: "Active GDMT policies",
    description: "GET /api/v1/admin/gdmt-policies/active — approved policies used by /recommend.",
    run: () => adminApi.activeGdmtPolicies(),
  },
  {
    id: "interaction-rules",
    label: "Active interaction rules",
    description: "GET /api/v1/admin/interaction-rules/active — approved rules used by the interaction checker.",
    run: () => adminApi.activeInteractionRules(),
  },
  {
    id: "dose-rules",
    label: "Active dose rules",
    description: "GET /api/v1/admin/dose-rules/active — approved rules used by the dose calculator.",
    run: () => adminApi.activeDoseRules(),
  },
  {
    id: "rules",
    label: "Active rules",
    description: "GET /api/v1/admin/constraints/active — published rules used by the CDSS engine (admin only).",
    run: () => adminApi.activeRules(),
  },
  {
    id: "drug-classes",
    label: "Drug classes",
    description: "GET /api/v1/kg/drug-classes",
    run: () => kgApi.drugClasses(),
  },
  {
    id: "hfrec",
    label: "HFrEF recommendations",
    description: "GET /api/v1/kg/recommendations/HFrEF",
    run: () => kgApi.recommendations("HFrEF"),
  },
  {
    id: "retrieval",
    label: "Evidence search",
    description: "GET /api/v1/evidence/search",
    needsInput: true,
    inputLabel: "Query",
    inputDefault: "ACE inhibitor hyperkalemia",
    run: (value) => retrievalApi.search(value, 6),
  },
  {
    id: "interactions",
    label: "Drug interactions",
    description: "GET /api/v1/kg/interactions",
    needsInput: true,
    inputLabel: "Drug name",
    inputDefault: "warfarin",
    run: (value) => kgApi.interactions(value, 5),
  },
  {
    id: "audit",
    label: "Audit trail",
    description: "GET /api/v1/audit/{case_id}",
    needsInput: true,
    inputLabel: "Case ID",
    inputDefault: "",
    run: (value) => auditApi.byCase(value || "demo-case"),
  },
];

export function ApiExplorerPage() {
  const [activeTool, setActiveTool] = useState(TOOLS[0].id);
  const [inputValue, setInputValue] = useState(TOOLS[3].inputDefault);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [output, setOutput] = useState(null);

  const tool = TOOLS.find((t) => t.id === activeTool) || TOOLS[0];

  async function runTool() {
    setLoading(true);
    setError("");
    try {
      const data = await tool.run(inputValue);
      setOutput(data);
    } catch (err) {
      setError(err.message);
      setOutput(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-header">
        <div>
          <h1>API explorer</h1>
          <p>Exercise backend routes for rules, knowledge graph, retrieval, and audit without leaving the dashboard.</p>
        </div>
      </header>

      <div className="api-explorer">
        <aside className="tool-list">
          {TOOLS.map((item) => (
            <button
              className={activeTool === item.id ? "active" : ""}
              key={item.id}
              onClick={() => {
                setActiveTool(item.id);
                setInputValue(item.inputDefault || "");
                setOutput(null);
                setError("");
              }}
              type="button"
            >
              <strong>{item.label}</strong>
              <small>{item.description}</small>
            </button>
          ))}
        </aside>

        <section className="tool-runner">
          <h2>{tool.label}</h2>
          <p>{tool.description}</p>

          {tool.needsInput && (
            <label className="tool-input">
              {tool.inputLabel}
              <input
                onChange={(e) => setInputValue(e.target.value)}
                type="text"
                value={inputValue}
              />
            </label>
          )}

          <button className="primary-action" disabled={loading} onClick={runTool} type="button">
            {loading ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}
            Run request
          </button>

          {error && <p className="inline-error" role="alert">{error}</p>}

          <pre aria-label="API response" className="api-output">
            {output ? JSON.stringify(output, null, 2) : "Response will appear here."}
          </pre>
        </section>
      </div>
    </div>
  );
}
