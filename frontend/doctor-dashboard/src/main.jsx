import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, AlertTriangle, CheckCircle2 } from "lucide-react";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function App() {
  const [health, setHealth] = useState("checking");

  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((response) => response.json())
      .then((data) => setHealth(data.status))
      .catch(() => setHealth("offline"));
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Heart Failure CDSS</h1>
          <p>Doctor dashboard skeleton</p>
        </div>
        <div className={`status status-${health}`}>
          {health === "ok" ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
          <span>API {health}</span>
        </div>
      </header>

      <section className="workspace">
        <div className="panel">
          <div className="panel-title">
            <Activity size={20} />
            <h2>Patient Case</h2>
          </div>
          <dl className="case-grid">
            <div><dt>LVEF</dt><dd>30%</dd></div>
            <div><dt>eGFR</dt><dd>28</dd></div>
            <div><dt>K+</dt><dd>5.4</dd></div>
            <div><dt>SBP</dt><dd>92</dd></div>
          </dl>
        </div>

        <div className="panel">
          <h2>Recommendation Preview</h2>
          <p className="muted">Use this area for Recommend, Consider, Caution, Avoid results with evidence and audit trail.</p>
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);

