# Dose rules bundle changelog

Governance catalog for structured HF dose calculators. Bundles are named `hf_dose_rules_v{N}.json`.
Runtime prefers **Postgres approved** rows; the active bundle file is the **fallback** when no approved rows exist.

## Rollout model

| Layer | Control |
|-------|---------|
| Fallback JSON | `HF_CDSS_DOSE_RULES_ACTIVE_BUNDLE_VERSION` (e.g. `v1`) or `HF_CDSS_DOSE_RULES_BUNDLE_PATH` |
| Postgres | Admin approve/retire via `/admin/dose-rules`; invalidates TTL cache |
| API traceability | `RecommendationResponse.dose_rules_version` |

## v1 (`hf_dose_rules_v1`)

- Baseline GDMT titration, loop diuretic congestion range, DOAC calculators, warfarin INR.
- 17 executable rules covering beta-blockers, MRA, SGLT2i, ARNI, ACEi/ARB, loop diuretics, DOACs, warfarin.

## Validation

- JSON Schema: `schemas/hf_dose_rules_bundle.schema.json`
- Load-time validation: `rule_validation.validate_runtime_bundle` (strict by default)
- CI: `test_dose_rule_validation.py` + `test_bundled_rule_fallbacks.py`
