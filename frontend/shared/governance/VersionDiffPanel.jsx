import { useEffect, useState } from "react";
import { GitCompare, LoaderCircle } from "lucide-react";

import { formatDiffValue } from "./catalogConfig.js";

const BASELINE_OPTIONS = [
  { value: "approved", label: "vs approved (live)" },
  { value: "previous", label: "vs previous version" },
];

function changeClass(changeType) {
  if (changeType === "added") return "gov-diff-added";
  if (changeType === "removed") return "gov-diff-removed";
  return "gov-diff-modified";
}

export function VersionDiffPanel({ ruleId, fetchDiff, versions = [] }) {
  const [against, setAgainst] = useState("approved");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [diff, setDiff] = useState(null);

  useEffect(() => {
    if (!ruleId || !fetchDiff) return;
    setLoading(true);
    setError("");
    fetchDiff(ruleId, against)
      .then(setDiff)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [ruleId, against, fetchDiff]);

  const versionOptions = versions
    .filter((item) => String(item.id) !== String(ruleId))
    .map((item) => ({
      value: String(item.id),
      label: `vs v${item.version} (${item.status})`,
    }));

  return (
    <section className="gov-diff-panel">
      <header className="gov-diff-header">
        <h3>
          <GitCompare size={16} /> Version diff
        </h3>
        <select
          aria-label="Diff baseline"
          className="gov-diff-select"
          onChange={(event) => setAgainst(event.target.value)}
          value={against}
        >
          {BASELINE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
          {versionOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </header>

      {loading && (
        <p className="gov-diff-status" aria-busy="true">
          <LoaderCircle className="spin" size={16} /> Loading diff...
        </p>
      )}
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      {!loading && !error && diff && (
        <>
          <p className="gov-diff-meta">
            Current v{diff.current?.version} ({diff.current?.status})
            {diff.baseline
              ? ` · Baseline v${diff.baseline.version} (${diff.baseline.status})`
              : " · No baseline found"}
          </p>
          {diff.changes?.length ? (
            <ul className="gov-diff-list">
              {diff.changes.map((change) => (
                <li className={changeClass(change.change_type)} key={change.path}>
                  <strong>{change.path}</strong>
                  <span className="gov-diff-badge">{change.change_type}</span>
                  <div className="gov-diff-values">
                    <div>
                      <small>Before</small>
                      <pre>{formatDiffValue(change.before)}</pre>
                    </div>
                    <div>
                      <small>After</small>
                      <pre>{formatDiffValue(change.after)}</pre>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="gov-diff-status">No field changes compared to baseline.</p>
          )}
        </>
      )}
    </section>
  );
}
