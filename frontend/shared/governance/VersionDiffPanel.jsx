import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Expand, GitCompare, LoaderCircle, X } from "lucide-react";

import { expandDiffChanges, compactReviewFieldLabel, valueToEntries } from "./diffDisplay.js";
import { diffClinicalIdentityWarning, normalizeReviewDiffValue } from "./clinicalReviewDisplay.js";
import "./governance-ui.css";

const BASELINE_OPTIONS = [
  { value: "approved", label: "vs approved (live)" },
  { value: "previous", label: "vs previous version" },
];

function changeClass(changeType) {
  if (changeType === "added") return "gov-diff-added";
  if (changeType === "removed") return "gov-diff-removed";
  return "gov-diff-modified";
}

function countByType(changes = []) {
  return changes.reduce(
    (acc, change) => {
      acc[change.change_type] = (acc[change.change_type] || 0) + 1;
      return acc;
    },
    { added: 0, removed: 0, modified: 0 },
  );
}

function ValueText({ text }) {
  const value = String(text ?? "");
  if (/^https?:\/\//i.test(value)) {
    return (
      <a className="gov-diff-value-link" href={value} rel="noreferrer" target="_blank">
        Open label source
      </a>
    );
  }
  return <span className="gov-diff-value-text">{value}</span>;
}

function DiffValueView({ value, path }) {
  const normalized = normalizeReviewDiffValue(path, value);
  const entries = valueToEntries(normalized);
  if (!entries.length || (entries.length === 1 && entries[0].text === "—")) {
    return <span className="gov-diff-value-text gov-diff-value-text--empty">—</span>;
  }
  return (
    <div className="gov-diff-value">
      {entries.map((entry, index) => (
        <div className="gov-diff-value-row" key={`${entry.label || "value"}-${index}`}>
          {entry.label ? <span className="gov-diff-value-label">{entry.label}</span> : null}
          {entry.chips?.length ? (
            <div className="gov-diff-chips">
              {entry.chips.map((chip) => (
                <span className="gov-diff-chip-label" key={chip}>
                  {chip}
                </span>
              ))}
            </div>
          ) : (
            <ValueText text={entry.text} />
          )}
        </div>
      ))}
    </div>
  );
}

function BaselineSelect({ against, onChange, versions, ruleId, id }) {
  const versionOptions = versions
    .filter((item) => String(item.id) !== String(ruleId))
    .map((item) => ({
      value: String(item.id),
      label: `vs v${item.version} (${item.status})`,
    }));

  return (
    <select
      aria-label="Diff baseline"
      className="gov-diff-select"
      id={id}
      onChange={(event) => onChange(event.target.value)}
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
  );
}

function ChangeSummary({ changes }) {
  const counts = countByType(changes);
  return (
    <div className="gov-diff-summary" aria-label="Change summary">
      <span className="gov-diff-chip gov-diff-chip--modified">{counts.modified} modified</span>
      <span className="gov-diff-chip gov-diff-chip--added">{counts.added} added</span>
      <span className="gov-diff-chip gov-diff-chip--removed">{counts.removed} removed</span>
    </div>
  );
}

function DiffRows({ changes }) {
  const expanded = expandDiffChanges(changes);
  if (!expanded.length) {
    return <p className="gov-diff-status">No field changes compared to baseline.</p>;
  }

  return (
    <div className="gov-diff-table-wrap gov-diff-table-wrap--cards">
      <ul className="gov-diff-compare-list">
        {expanded.map((change) => (
          <li
            className={`gov-diff-compare-row ${changeClass(change.change_type)}`}
            key={change.path}
          >
            <div className="gov-diff-compare-field">
              <strong>{compactReviewFieldLabel(change.path)}</strong>
              <span className="gov-diff-badge">{change.change_type}</span>
            </div>
            <div className="gov-diff-compare-cols">
              <div className="gov-diff-col gov-diff-col--before">
                <span className="gov-diff-col-label">Before</span>
                <DiffValueView path={change.path} value={change.before} />
              </div>
              <div className="gov-diff-col gov-diff-col--after">
                <span className="gov-diff-col-label">After (current)</span>
                <DiffValueView path={change.path} value={change.after} />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function VersionDiffDialog({
  open,
  onClose,
  against,
  onAgainstChange,
  versions,
  ruleId,
  diff,
  loading,
  error,
  titleId,
}) {
  const closeRef = useRef(null);
  const dialogRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement;
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  const currentLabel = diff
    ? `Current v${diff.current?.version ?? "?"} (${diff.current?.status ?? "—"})`
    : "Current";
  const baselineLabel = diff?.baseline
    ? `Baseline v${diff.baseline.version} (${diff.baseline.status})`
    : "Baseline (none)";

  const identityWarning = diff ? diffClinicalIdentityWarning(diff.changes || []) : null;

  return createPortal(
    <div
      className="gov-diff-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="presentation"
    >
      <div
        aria-labelledby={titleId}
        aria-modal="true"
        className="gov-diff-dialog"
        ref={dialogRef}
        role="dialog"
      >
        <header className="gov-diff-dialog-header">
          <div>
            <h2 id={titleId}>
              <GitCompare aria-hidden size={20} /> Version review
            </h2>
            <p className="gov-diff-dialog-subtitle">
              Side-by-side comparison of clinical content and source references. Technical ids and
              pipeline hashes are hidden.
            </p>
            <p className="gov-diff-help">
              Green and orange columns show values on the baseline version versus the version you are
              reviewing. Use the baseline menu to compare against the live approved rule or an earlier
              draft.
            </p>
          </div>
          <div className="gov-diff-dialog-controls">
            <label className="gov-diff-label" htmlFor={`${titleId}-baseline`}>
              Compare against
              <BaselineSelect
                against={against}
                id={`${titleId}-baseline`}
                onChange={onAgainstChange}
                ruleId={ruleId}
                versions={versions}
              />
            </label>
            <button
              aria-label="Close version review"
              className="icon-btn gov-diff-close"
              onClick={onClose}
              ref={closeRef}
              type="button"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        <div className="gov-diff-dialog-body">
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
              <div className="gov-diff-dialog-meta">
                <div className="gov-diff-version-pill">{baselineLabel}</div>
                <div className="gov-diff-version-pill gov-diff-version-pill--current">{currentLabel}</div>
                <ChangeSummary changes={expandDiffChanges(diff.changes)} />
              </div>
              {!diff.baseline && (
                <p className="gov-diff-status" role="status">
                  No baseline found for this comparison — all fields below show as added on the
                  current version.
                </p>
              )}
              {identityWarning ? (
                <p className="gov-diff-clinical-warning" role="status">
                  {identityWarning.message}
                </p>
              ) : null}
              <DiffRows changes={diff.changes} />
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function VersionDiffPanel({ ruleId, fetchDiff, versions = [] }) {
  const titleId = useId();
  const [against, setAgainst] = useState("approved");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [diff, setDiff] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const requestSeq = useRef(0);

  // Switching rules resets baseline/diff but keeps the sheet open so the list
  // Review buttons stay usable for jumping between items.
  useEffect(() => {
    setAgainst("approved");
    setDiff(null);
    setError("");
  }, [ruleId]);

  useEffect(() => {
    if (!ruleId || !fetchDiff) return undefined;
    const seq = ++requestSeq.current;
    setLoading(true);
    setError("");
    fetchDiff(ruleId, against)
      .then((payload) => {
        if (requestSeq.current !== seq) return;
        setDiff(payload);
      })
      .catch((err) => {
        if (requestSeq.current !== seq) return;
        setError(err.message);
      })
      .finally(() => {
        if (requestSeq.current !== seq) return;
        setLoading(false);
      });
    return undefined;
  }, [ruleId, against, fetchDiff]);

  const changeCount = expandDiffChanges(diff?.changes || []).length;

  return (
    <section className="gov-diff-panel">
      <header className="gov-diff-header">
        <h3>
          <GitCompare size={16} /> Version diff
        </h3>
        <BaselineSelect
          against={against}
          onChange={setAgainst}
          ruleId={ruleId}
          versions={versions}
        />
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
          <ChangeSummary changes={expandDiffChanges(diff.changes)} />
          <p className="gov-diff-teaser">
            {changeCount
              ? `${changeCount} field${changeCount === 1 ? "" : "s"} differ. Open full review for a wide side-by-side view.`
              : "No field changes compared to baseline."}
          </p>
          <button
            className="secondary-action gov-diff-open-btn"
            onClick={() => setDialogOpen(true)}
            type="button"
          >
            <Expand size={16} /> Open full review
          </button>
        </>
      )}

      <VersionDiffDialog
        against={against}
        diff={diff}
        error={error}
        loading={loading}
        onAgainstChange={setAgainst}
        onClose={() => setDialogOpen(false)}
        open={dialogOpen}
        ruleId={ruleId}
        titleId={titleId}
        versions={versions}
      />
    </section>
  );
}
