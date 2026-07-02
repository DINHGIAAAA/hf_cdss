import { ExternalLink, FileText, ShieldAlert } from "lucide-react";
import { patientSummary, readable, sourceLink, statusClass, titleCase } from "../utils";

// ─── Evidence Card ────────────────────────────────────────────────────────────

function EvidenceCard({ chunk }) {
  const link = sourceLink(chunk);
  return (
    <article className="evidence-card">
      <div className="evidence-head">
        <div>
          <strong>{titleCase(chunk.document_id)}</strong>
          <span>{chunk.section || chunk.evidence_level || chunk.source_type}</span>
        </div>
        <span className="score">{Math.round((chunk.quality_score ?? chunk.score ?? 0) * 100)}%</span>
      </div>
      <p>{(chunk.text || "").replace(/\s+/g, " ").slice(0, 280)}</p>
      <div className="evidence-foot">
        {chunk.chunk_id && <span>Chunk {chunk.chunk_id}</span>}
        {chunk.page && <span>Page {chunk.page}</span>}
        {chunk.metadata?.source_locator && <span>{chunk.metadata.source_locator}</span>}
        {chunk.metadata?.publisher && <span>{chunk.metadata.publisher}</span>}
        {link && (
          <a href={link} rel="noreferrer" target="_blank">
            Open source <ExternalLink size={14} />
          </a>
        )}
      </div>
    </article>
  );
}

// ─── Recommendation Card ──────────────────────────────────────────────────────

function RecommendationCard({ item, evidenceChunks = [] }) {
  const linkedChunks = evidenceChunks.filter((chunk) => item.evidence?.includes(chunk.chunk_id));

  return (
    <article className="recommendation-card">
      <div className="recommendation-title">
        <strong>{item.drug_class}</strong>
        <span className={statusClass(item.status)}>{titleCase(item.status)}</span>
      </div>
      <p>{item.rationale}</p>
      {linkedChunks.length > 0 && (
        <div className="clinical-block">
          <b>Linked evidence</b>
          <ul>
            {linkedChunks.slice(0, 2).map((chunk) => (
              <li key={chunk.chunk_id}>
                {titleCase(chunk.document_id)} — {chunk.section || chunk.source_type}
              </li>
            ))}
          </ul>
        </div>
      )}
      {item.action_items?.length > 0 && (
        <div className="clinical-block">
          <b>Next clinical step</b>
          <ul>
            {item.action_items.slice(0, 2).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {item.monitoring?.length > 0 && (
        <div className="clinical-block">
          <b>Monitor</b>
          <ul>
            {item.monitoring.slice(0, 2).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

// ─── Patient Vitals Section ───────────────────────────────────────────────────

function PatientSection({ summary, attachments }) {
  return (
    <section>
      <h2>Patient</h2>
      <div className="fact-grid">
        {[
          ["LVEF", summary.lvef, "%"],
          ["eGFR", summary.egfr, ""],
          ["K+", summary.potassium, " mmol/L"],
          ["SBP", summary.systolicBp, " mmHg"],
          ["HR", summary.heartRate, " bpm"],
          ["Weight", summary.weightKg, " kg"],
          ["Age", summary.age, " yr"],
        ].map(([label, val, unit]) => (
          <div className="fact-item" key={label}>
            <span className="fact-label">{label}</span>
            <strong className="fact-value">
              {val !== null && val !== undefined ? `${val}${unit}` : "missing"}
            </strong>
          </div>
        ))}
      </div>

      {summary.conditions.length > 0 && (
        <p className="panel-meta">
          <b>Conditions:</b> {summary.conditions.join(", ")}
        </p>
      )}
      {summary.medications.length > 0 && (
        <p className="panel-meta">
          <b>Meds:</b> {summary.medications.join(", ")}
        </p>
      )}

      {attachments?.length > 0 && (
        <div className="attachment-list">
          {attachments.map((file) => (
            <article key={`${file.file_name}-${file.mime_type}`}>
              <FileText size={15} />
              <div>
                <strong>{file.file_name}</strong>
                <span>{file.extracted_text ? `${file.extracted_text.length} chars` : file.note}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

// ─── Main Panel ───────────────────────────────────────────────────────────────

export function ClinicalPanel({ active, error, open }) {
  const summary = patientSummary(active?.draft?.patient || active?.patient);

  return (
    <aside className={`clinical-panel${open ? "" : " panel--collapsed"}`}>
      {error && <p className="error-text">{error}</p>}

      {summary ? (
        <>
          <PatientSection summary={summary} attachments={active?.attachments} />

          {active?.recommendation && (
            <section>
              <h2>Recommendation</h2>
              <div className={`decision ${statusClass(active.recommendation.overall_status)}`}>
                <ShieldAlert size={17} />
                <strong>{titleCase(active.recommendation.overall_status)}</strong>
              </div>
              <div className="recommendation-list">
                {active.recommendation.recommendations.map((item) => (
                  <RecommendationCard
                    evidenceChunks={active.verification?.context?.evidence_chunks || []}
                    item={item}
                    key={item.drug_class}
                  />
                ))}
              </div>
            </section>
          )}

          {active?.verification?.context?.evidence_chunks?.length > 0 && (
            <section>
              <h2>Evidence</h2>
              <div className="evidence-list">
                {active.verification.context.evidence_chunks.slice(0, 4).map((chunk) => (
                  <EvidenceCard chunk={chunk} key={chunk.chunk_id} />
                ))}
              </div>
            </section>
          )}
        </>
      ) : (
        <p className="empty-state">Patient context and evidence will appear here.</p>
      )}
    </aside>
  );
}
