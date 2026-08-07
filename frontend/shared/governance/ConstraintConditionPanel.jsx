import { DetailFieldList } from "./DetailFieldList.jsx";

/**
 * Empty / present condition panel for constraint review.
 */
export function ConstraintConditionPanel({ rule, fields, needsCondition }) {
  const risks = Array.isArray(rule?.risk_names) ? rule.risk_names.filter(Boolean) : [];
  const tier = rule?.metadata?.safety_tier ? String(rule.metadata.safety_tier) : null;

  return (
    <section aria-label="Condition" className="detail-section condition-panel">
      <h3>Condition</h3>
      {fields.length ? (
        <DetailFieldList fields={fields} />
      ) : (
        <div className="condition-empty">
          <p className="detail-empty">
            {needsCondition
              ? "This rule has no machine-checkable IF condition yet (for example eGFR < 30 or pregnancy). The pipeline flagged it for refinement so it is not treated as a hard gate for every patient on this drug."
              : "This rule does not define a structured condition. It may be informational only, or the condition was not extracted."}
          </p>
          {tier ? (
            <p className="condition-empty-meta">
              Safety tier: <code>{tier}</code>
            </p>
          ) : null}
          {risks.length ? (
            <p className="condition-empty-meta">
              Related risks (not a structured condition): {risks.join(", ")}
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}
