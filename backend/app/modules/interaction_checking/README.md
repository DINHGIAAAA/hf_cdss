# Interaction Checking

Checks drug-drug interaction warnings for the CDSS recommend / interaction APIs.

## Runtime source of truth

**Postgres `approved` interaction rules** synced from the ingestion pipeline (Admin governance).

There is no bundled JSON fallback. When Postgres is empty or unavailable, the matcher returns no rules until catalogs are synced.

## Ingestion pipeline (FDA XML + optional guideline LLM)

```text
raw/drug_labels/{id}/{id}_label.xml
        │
        ▼
python -m scraper.process.extract_fda_xml_interaction_claims
  [--llm-normalize / --no-llm-normalize]
        │  artifacts/.../structured_interaction_claims_fda.jsonl
        ▼
python -m scraper.process.extract_structured_interaction_claims
  [--source all|fda|chunks]
        │  merges FDA claims + LLM guideline chunk claims
        ▼
python -m scraper.process.generate_interaction_rules
python -m scraper.process.classify_interaction_rules
python -m scraper.process.sync_governance_catalog --catalog interaction_rules
        │  Postgres status=draft
        ▼
Admin UI → Approve / Reject → runtime RuleCache
```

Orchestration shortcut (includes FDA pre-step):

```bash
python -m scraper.orchestration.governance_catalog_steps --catalog interaction_rules
```

### Extractor location

- Deterministic SPL parse: `app.modules.interaction_checking.xml_interaction_extractor`
- Partner normalize (alias / class phrase): `partner_normalize.py`
- Optional LLM remap for unmatched partners: `scraper.semantic.interaction_llm_normalize`

### Evidence refs

- FDA-derived: `fda_label:{pipeline_id}:drug_interactions`

## Matcher classes

`matcher.py` expands `class:*` tokens (ACEI/ARB/ARNI/MRA/RAASi, NSAID, anticoagulants,
antiplatelets, SGLT2i, beta blockers, non-DHP CCB, QT-prolonging, statin, insulin, …).

## Admin

Filter drafts by **Source** (`extraction_method` contains `fda_xml` / `llm_structured`).
Detail panel shows clinical source quotes from `clinical_sources`.
Bulk approve without explicit ids defaults to `safety_tier=usable_rules`.
