# Gold claim annotation guide

## Goal

Build a clinician-reviewed gold set so we can measure **precision / recall / F1 by `claim_type`** for extraction quality. Target for safety-critical types (contraindication, renal_constraint, hyperkalemia_risk, drug_interaction hard blocks): **precision ≥ 0.95** on the approved gold subset.

## Record shape

See `gold/schema.json`. Each row is one judgment about a source span.

| Field | Required | Notes |
|-------|----------|--------|
| `gold_id` | yes | Stable id, e.g. `gold_ci_entresto_01` |
| `label` | yes | `valid_claim` \| `invalid_extraction` \| `should_extract` |
| `claim_type` | if valid / should_extract | One of pipeline claim types |
| `drug` | usually | Snake_case drug key or `null` |
| `evidence` | yes | Exact or near-exact source span |
| `document_id` | yes | Registry / label id |
| `source_type` | yes | `drug_label` \| `guideline` |
| `safety_tier` | yes | `hard_block` \| `review` \| `informational` |
| `status` | yes | `draft` \| `reviewed` \| `approved` |
| `annotator` | yes | Initials or `seed` |
| `notes` | no | Why labeled this way |

### Labels

- **`valid_claim`**: Pipeline *should* produce a claim of this type/drug from this evidence (used for recall + precision matching).
- **`invalid_extraction`**: Text looks like a claim but **must not** become a clinical rule (noise, authorship, keywords list). Used for precision traps.
- **`should_extract`**: Same as valid for scoring; use when gold was written before a pipeline claim_id existed.

## How to annotate

1. Prefer FDA label / guideline language you can cite.
2. Keep `evidence` short (one sentence / one directive).
3. Set `safety_tier=hard_block` only for true stop/CI/severe interaction/dose ceiling.
4. Mark `status=approved` only after a clinician review.
5. Do not invent drugs or conditions not supported by the span.

## Expanding the set

```powershell
# Stratified candidates from current claims (for human review)
py -m scraper.eval.sample_gold_candidates --per-type 15 --output evaluation/candidates/claims_review_queue.jsonl

# After editing gold, score current artifacts
py -m scraper.eval.evaluate_claims_against_gold --gold evaluation/gold/claims_gold.jsonl --predictions data/heart_failure/artifacts/claims/claims.jsonl
```

Aim for ≥50 **approved** rows per safety-critical type before trusting a ≥95% claim.
