# Dose rules bundle changelog

Governance catalog for structured HF dose calculators. Bundles are named `hf_dose_rules_v{N}.json`.
Runtime prefers **Postgres approved** rows; the active bundle file is the **fallback** when no approved rows exist.

## Rollout model

| Layer | Control |
|-------|---------|
| Fallback JSON | `HF_CDSS_DOSE_RULES_ACTIVE_BUNDLE_VERSION` (e.g. `v1`, `v2`) or `HF_CDSS_DOSE_RULES_BUNDLE_PATH` |
| Postgres | Admin approve/retire via `/admin/dose-rules`; invalidates TTL cache |
| API traceability | `RecommendationResponse.dose_rules_version` |

## v1 (`hf_dose_rules_v1`)

- Baseline GDMT titration, loop diuretic congestion range, DOAC calculators, warfarin INR.
- 17 executable rules covering beta-blockers, MRA, SGLT2i, ARNI, ACEi/ARB, loop diuretics, DOACs, warfarin.

## v2 (`hf_dose_rules_v2`)

- **Status:** scaffold — initially cloned from v1 for safe bundle-version rollout testing.
- **To promote clinical changes:**
  1. Edit `rules/hf_dose_rules_v2.json` (or run `python -m app.modules.dose_calculator.promote_bundle --from v1 --to v2`).
  2. Validate: `python -m app.modules.dose_calculator.validate_rules`.
  3. Seed Postgres (optional): `python -m app.modules.dose_calculator.migrate_to_db` with `HF_CDSS_DOSE_RULES_ACTIVE_BUNDLE_VERSION=v2`.
  4. Admin-approve synced pipeline rows, or approve seeded drafts.
  5. Switch fallback only after regression: `HF_CDSS_DOSE_RULES_ACTIVE_BUNDLE_VERSION=v2`.
  6. Roll back by setting version back to `v1` or retiring v2 Postgres rows.

## Validation

- JSON Schema: `schemas/hf_dose_rules_bundle.schema.json`
- Load-time validation: `rule_validation.validate_runtime_bundle` (strict by default)
- CI: `test_dose_rule_validation.py` + `validate_rules` module

## Migration checklist (v1 → v2)

- [ ] Diff v1 vs v2 rule bodies (`rule_id`, `calculation_type`, dose fields)
- [ ] Run dose calculator unit tests + medication safety integration tests
- [ ] Update scraper sync metadata `bundle_version: hf_dose_rules_v2`
- [ ] Approve in admin UI; confirm `dose_rules_version` in recommendation API
- [ ] Monitor readiness `/health/ready` → `dose_rules.status=ok`
