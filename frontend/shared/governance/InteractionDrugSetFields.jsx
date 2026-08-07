import { DetailFieldList } from "./DetailFieldList.jsx";
import { humanizeKey } from "./displayNames.js";
import { drugSetNeedsReview, isSuspiciousDrugSetToken } from "./interactionDrugSet.js";

function formatSetValue(tokens = []) {
  const list = Array.isArray(tokens) ? tokens : [];
  if (!list.length) return "—";
  return list.map((token) => {
    if (isSuspiciousDrugSetToken(token)) {
      return "Partner unresolved (see quote below)";
    }
    return humanizeKey(token);
  });
}

export function InteractionDrugSetFields({ drugSetA = [], drugSetB = [] }) {
  const needsReview = drugSetNeedsReview(drugSetA) || drugSetNeedsReview(drugSetB);

  return (
    <>
      {needsReview ? (
        <p className="gov-diff-clinical-warning" role="status">
          Drug set B (or A) is not a real drug name — the extractor slugged label prose into the
          partner field. Use the clinical quote and section to identify the interacting drug; re-run
          ingestion or edit after partner normalization.
        </p>
      ) : null}
      <DetailFieldList
        fields={[
          { label: "Drug set A (subject)", value: formatSetValue(drugSetA) },
          { label: "Drug set B (partner)", value: formatSetValue(drugSetB) },
        ]}
      />
    </>
  );
}
