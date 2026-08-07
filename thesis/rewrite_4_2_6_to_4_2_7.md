# CHAPTER 4: IMPLEMENTATION AND DEPLOYMENT

## 4.2. Knowledge Construction Pipeline

### 4.2.6. Extraction of Structured Clinical Artifacts

Extraction converts kept text into objects the runtime can evaluate. Several specialized builders cooperate. Constraint rule extraction produces conditional avoid and caution statements. Dose rule extraction captures starting doses, target doses, renal bands, and titration schedules. Interaction extraction builds drug-set pairs with severity and management text. GDMT policy extraction encodes four-pillar coverage expectations for HFrEF. Dose-safety warning extraction captures label maxima that should fire when a planned dose exceeds safe limits for the patient's renal band.

The hybrid strategy is regex first, LLM second. High-frequency SPL phrasing is cheap to match with patterns. When patterns are sparse, `scraper/semantic/rule_builder.py` calls the local Ollama chat API with a JSON schema validated by Pydantic. Invalid JSON is rejected before it enters the artifact stream. Prompt hashes feed the ingestion cache so identical sections do not re-spend tokens on every rerun.

**Prescriptive filter.** Both extraction paths—regex and LLM—apply the same prescriptive gate for `population_constraint` claims. Observational statements such as "safety and effectiveness in pediatric patients have not been established," "use in pregnancy has been reported," or study baseline descriptions are rejected at extract time regardless of which method found them. This gate exists because population-constraint claims serve GraphRAG explanation, not runtime safety enforcement, so soft observational language should not appear alongside hard-block or caution rules. The filter mirrors the `_matches_claim_type` logic used by regex extraction: it checks for directive cues (contraindicated, not recommended, avoid, do not, should not, must not) and rejects any claim that lacks them while containing observational phrasing. Without this gate on the LLM path, observational claims would survive extraction, inflate claim counts, and lower the measured precision of the knowledge base without contributing to clinical safety.

Named entity recognition and relation linking attach drugs, classes, labs, and conditions to each claim. Evidence linking stores chunk identifiers so a later recommendation card can show the passage that motivated a rule. Deduplication collapses near-identical extractions from overlapping label sections.

### 4.2.7. Classification and Governance Gates

Classification assigns deployability before rules reach clinicians. Safety tiers include `hard_block` for absolute contraindications, `usable_rules` for complete executable conditions, and `needs_condition_refinement` for drafts that parse but still need human clarification. Action types include avoid, consider with caution, consider, and continue. These labels map directly to recommendation card badges in the doctor dashboard.

Evidence-alignment validation runs after extraction. The validator checks two conditions: the drug named in the claim appears in the source evidence text, and numeric thresholds match. A drug that appears nowhere in the evidence—indicating a wrong-drug extraction or cross-reference confusion—is treated as a critical issue, not merely a warning, and the claim is rejected. Keyword-only alignment, where evidence contains relevant terms but lacks the specific drug or threshold named in the claim, is also rejected. This is stricter than surface matching: the validator confirms that the claim's clinical substance is present verbatim in the source, not just that the document is about the same topic.

The combined effect of prescriptive filtering at extraction and drug-threshold alignment at validation is that noise is removed before it reaches governance review. Rules marked for refinement sync into PostgreSQL for admin review rather than disappearing. Runtime loaders ignore unfinished drafts until a clinical lead promotes them. This gate is essential. Automated extraction is powerful, but heart-failure safety cannot depend on unreviewed model guesses.
