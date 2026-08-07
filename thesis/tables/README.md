# Thesis tables

Same pattern as [figures/README.md](../figures/README.md): **chapters carry the narrative numbering** (Table 3.x, 4.x, 5.x); appendices hold the full catalog and optional extended material.

## Appendix A (exists)

| Appendix | Chapter (primary placement) | Section | Standalone HTML |
|----------|----------------------------|---------|-----------------|
| **Table A.1** Main components & ports | **Table 3.1** | Ch.3 §3.2.2 (after Figure 3.1) | `chapters/table-3-1-components.html` |
| **Table A.2** Frontend routes | **Table 4.1** | Ch.4 §4.4 (after Figure 4.2) | `chapters/table-4-1-frontend-routes.html` |
| **Table 4.2** Normalization thresholds | Ch.4 §4.3.4 | — |
| **Tables 4.3–4.16** Test case matrices | Ch.4 §4.6 | — |

Supplemental (appendix-only today, no chapter number):

| Location | Content | Suggested chapter hook |
|----------|---------|-------------------------|
| Appendix A, under Figure A.3 | “Why S3 if PostgreSQL sync?” (4-row table) | Ch.4 §4.2.6 / §4.5.1 object storage |

Edit table cells in **both** the chapter `.md` and `Appendix_A_Figures_and_Diagrams.md` (or regenerate HTML wrappers after changes).

## Appendix B (not in repo yet)

There is no `Appendix_B_*.md` file in `thesis/` today. Chapter 5 already embeds the main results tables in the body:

| Table | Section | Keep in chapter? | Typical Appendix B role |
|-------|---------|------------------|------------------------|
| **5.0a–5.0c** | §5.2.4 claim filter / LLM precision | Yes (primary) | Optional duplicate as **Table B.1–B.3** for examiners who read appendices first |
| Catalog counts (interaction, GDMT, dose…) | §5.2.4 (unlabeled block) | Yes — consider caption **Table 5.0** | **Table B.4** extended audit mirror |
| Phase A/B/C change logs | §5.2.4 | Yes (methods detail) | **Table B.5–B.7** if moved out for length |
| **5.1–5.3** | §5.3 vignettes, alerts | Yes | Usually stay in Ch.5 only |

Recommended rule: **numbers reported in the argument stay in Chapter 5**; Appendix B = reproducibility (paths, seeds, hardware), gold-set schema, long per-type breakdowns, and duplicate copies of 5.0a–c if your faculty requires “all tables in appendices.”

## Chapter 5 tables (already in manuscript)

All of these live in `Chapter5_Results_and_Evaluation.md` only (not Appendix A):

- **Table 5.0a–5.0c** — claim filter progression and LLM precision (§5.2.4)
- **Table 5.1** — vignette recommendation metrics (§5.3.1)
- **Table 5.2** — accuracy by clinical focus (§5.3.1)
- **Table 5.3** — alert burden (§5.3.3)

Plus inline metric table (three rows: vignette vs claim vs structural precision) in §5.2.4 — treat as part of the narrative or label **Table 5.0** if you need a list-of-tables entry.

## Chapter 5 tables (already in manuscript)

All live in `Chapter5_Results_and_Evaluation.md`:

- **Table 5.0** — artifact/catalog snapshot (§5.2.4)
- **Table 5.0d** — three reporting metrics (must not conflate)
- **Table 5.0a–5.0c** — claim filter progression and LLM precision
- **Table 5.0e–5.0g** — engineering change logs (phases A–C)
- **Table 5.1–5.3** — vignettes, focus areas, alert burden
- **Table 5.4** — qualitative CDSS comparison (§5.5.1)

Each table has an introductory paragraph in the chapter body; numeric detail stays in the table, not repeated in prose.

## Styles

- `chapter-table-page.css` — standalone pages under `tables/chapters/`
- Chapter markdown uses GitHub-style pipe tables (Word/PDF via Pandoc or copy from HTML)
