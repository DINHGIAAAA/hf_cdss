# CHAPTER 5: RESULTS AND EVALUATION

## 5.2 Knowledge Base Construction Results

### 5.2.4. Knowledge-Base Data Quality Audit

Volume counts alone do not prove that extracted knowledge is clinically usable. After the ingestion pipeline finished, we audited persisted artifacts with structural heuristics, an LLM semantic judge on stratified claim samples, and catalog-tier scans. The audit is documented in `evaluation/reports/accuracy_audit_20260728.md`. Auto-judge precision is a triage signal, not a cardiologist-certified gold standard.

Claims were re-extracted and are present in the workspace (`artifacts/claims/claims.jsonl`, 16,973 rows). Filtered outputs are `claims_filtered.jsonl` (6,296 rows after pass 8) and `claims_filtered_safety.jsonl` (4,440 rows without `guideline_recommendation`). Constraint and other governance catalogs are intended to live in the processed S3 bucket (`hf-cdss-processed`) and to be mirrored locally under `artifacts/` for evaluation. The quality tables below therefore separate **content quality of claims that are on disk** from **catalog-tier counts for governance JSONL files present in the local mirror at audit time**.

Local governance catalogs available for counting at audit time (2026-07-30, post raw-only migration):

| Catalog | Count | Usable | Needs refinement | Rejected |
|---------|------:|-------:|-----------------:|---------:|
| Claims (`claims.jsonl`) | 16,973 | — | — | — |
| Claims filtered (pass 8) | 6,296 | — | — | — |
| Claims filtered (safety-only) | 4,440 | — | — | — |
| Interaction rules | 1,766 | 1,081 (61%) | 661 (37%) | 24 (1%) |
| GDMT policies | 1,880 | 1,880 (100%) | 0 | 0 |
| Dose rules | 139 | 137 (99%) | 2 (1%) | 0 |
| Dose-safety warnings | 2,903 | 1,440 (50%) | 1,463 (50%) | 0 |
| Constraint rules (`artifacts/rules/*.jsonl`) | Not in local mirror | — | — | — |

Dose-safety warnings are now **100% from raw claims** (`claims_pipeline_dose_safety`); bundled baseline rows are **0** (previously 10/71 usable at 14%). Roughly half of dose-safety rows still need LLM trigger refinement (`refine_dose_safety_triggers`) before they become executable. Full audit: `evaluation/reports/data_quality_audit_20260730.md`.

Constraint rule files were not present under the local `artifacts/rules/` path used for this write-up, even though claims were. If constraint catalogs were re-extracted and uploaded to S3 after an earlier empty-bucket snapshot, their usable or refinement tier counts should be taken from a restored mirror (`sync_processed_from_s3`) rather than treated as permanently missing. The claim-quality findings below are independent of that restore step because `claims.jsonl` was already local.

#### Judge calibration and metric separation

We measured claim quality with a stratified LLM judge (`qwen2.5:7b`, balanced prompt, 10 claims per type, seed 42, timeout 300 s). The 1.5B judge previously reported 71.1% on filtered claims; that figure is optimistic. The 7B judge is stricter and is the default for thesis reporting.

Three metrics must not be conflated:

| Metric | Meaning | Latest result |
|--------|---------|---------------|
| Vignette recommendation accuracy (Section 5.3) | Structured CDSS cards vs cardiologist expectation | **94.0%** |
| Claim LLM precision (safety-only, pass 8) | Semantic quality of individual KG claims (7B proxy) | **73.8%** |
| Strict structural precision | Share passing all filter gates on a stratified sample | **100%** after pass 8 |

The ~20 percentage-point gap between claim precision (73.8%) and vignette accuracy (94.0%) is expected and does not indicate a contradiction. The two metrics measure different things at different altitudes. Claim precision evaluates whether each individual claim in the knowledge base—drug interactions, dose thresholds, population constraints—is semantically coherent and clinically meaningful as a standalone statement. Vignette accuracy evaluates whether the structured recommendation output (start/continue/avoid per drug class) matches cardiologist expectation for a given patient case. The sources of the gap are:

**Governed catalogs, not raw claims, drive recommendations.** The recommendation engine reads from approved PostgreSQL catalogs (constraint rules, interaction rules, GDMT policies) that have been reviewed, filtered, and validated through a separate pipeline phase. Raw claims on disk feed GraphRAG retrieval and explanation; they do not directly control structured status assignments. A noisy claim in `claims.jsonl` that the judge scores as imprecise may never appear in a citation or influence a recommendation.

**The prescriptive filter removes observational noise early.** Population-constraint claims of the form "safety and effectiveness have not been established" or "use in pregnancy has been reported" are dropped at extraction time, before they reach the knowledge base. The judge still evaluates remaining claims; residual imprecision at 73.8% comes from borderline cases in dose recommendation, renal constraint, and drug interaction types that survived filtering but the judge found semantically weak.

**The evidence-alignment validator removes wrong-drug claims.** Claims whose evidence text does not contain the named drug are rejected as critical issues. Before this gate, a claim attributing a contraindication to the wrong drug would appear in the knowledge base, lower the judge score, and potentially generate false citations. After the gate, such claims are absent from retrieval candidates.

**The recommendation engine is conservative.** Hard-block constraints override permissive retrieval text. A claim the judge rates as marginally imprecise may contribute a citation but not a status override. Cardiologists evaluate structured status fields, not citation text.

In short: the knowledge base contains a mixed-quality corpus of candidate claims; governed catalogs are a curated subset; recommendation accuracy measures catalog behavior on patient cases; and claim precision measures corpus quality. The gap reflects the safety architecture's intent, not a quality problem.

#### Staged filtering (passes 0–8)

We applied eight cumulative filter passes (`scraper/eval/filter_claims_for_quality.py`) and recorded structural quality after each step. **Table 5.0a** tracks corpus size and strict structural precision. **Table 5.0b** tracks LLM semantic precision across filter rounds. Reproducible JSON logs: `evaluation/reports/claim_filter_progression.json`, `auto_eval_20260729T094553Z.json`, `auto_eval_20260729T094630Z.json`.

**Table 5.0a. Claim quality after each filter pass**

| Pass | Claims left | Dropped | Retain % | Strict struct. prec. | Change (accuracy goal) |
|------|------------:|--------:|---------:|---------------------:|------------------------|
| 0 Baseline (raw) | 16,973 | 0 | 100.0% | 44.8% | Unfiltered extraction |
| 1 Type–evidence gate | 12,445 | 4,528 | 73.3% | 59.6% | Drop type–evidence mismatches |
| 2 Require drug on hard types | 12,084 | 361 | 71.2% | 56.7% | Hard types must carry a drug |
| 3 Drop off-scope drugs | 9,989 | 2,095 | 58.9% | 71.1% | Remove non-HF formulary agents |
| 4 Drop noise / weak spans | 9,933 | 56 | 58.5% | 72.6% | Remove boilerplate and cross-refs |
| 5 Drop trial / PK / device | 9,283 | 650 | 54.7% | 73.7% | RCT arms, NDC, device instructions |
| 6 Drop empty-drug ADR/interaction | 9,238 | 45 | 54.4% | 73.7% | ADR/interaction without drug |
| 7 Drop non-actionable ADR | 7,620 | 1,618 | 44.9% | 84.8% | ADR without clinical action verbs |
| **8 Drop weak dose / renal** | **6,296** | **1,324** | **37.1%** | **100.0%** | Dose/renal quality gates (pass 8) |

**Table 5.0b. LLM semantic precision across filter rounds** (qwen2.5:7b, balanced prompt)

| Corpus | Claims | Sample *n* | Overall LLM prec. | Hard-type prec. |
|--------|-------:|-----------:|--------------------:|----------------:|
| Raw (1.5b judge, historical) | 16,973 | 90 | 57.8% | 62.0% |
| Filtered pass 7 (all types) | 7,620 | 90 | 62.2% | 70.0% |
| Filtered pass 7 (safety-only) | 5,764 | 80 | 66.3% | 70.0% |
| **Filtered pass 8 (all types)** | **6,296** | **90** | **66.7%** | **70.0%** |
| **Filtered pass 8 (safety-only)** | **4,440** | **80** | **73.8%** | **70.0%** |

Safety-only excludes `guideline_recommendation`, the noisiest type under the 7B judge (10% on pass 8).

**Table 5.0c. Per-claim-type LLM precision (pass 8, *n* = 10 per type)**

| Claim type | Pass 7 (7B) | Pass 8 (all) | Pass 8 (safety) | Note |
|------------|------------:|-------------:|----------------:|------|
| Contraindication | 80% | 80% | 80% | Stable |
| Usage constraint | 80% | 80% | 80% | Stable |
| Adverse reaction | 80% | 70% | 70% | Sample variance |
| Drug interaction | 70% | 80% | 80% | Improved |
| Hyperkalemia risk | 70% | 70% | 70% | Stable |
| **Dose recommendation** | **50%** | **90%** | **90%** | Pass 8 + extractor gates |
| **Renal constraint** | **50%** | **80%** | **80%** | Pass 8 + extractor gates |
| Population constraint | 50% | 40% | 40% | PK/demographic noise remains |
| Guideline recommendation | — | 10% | *(excluded)* | Not used for safety KG |

Pass 8 improved dose precision from 50% to 90% and renal precision from 50% to 80%. Population constraints still need clinician gold labeling or extractor fixes.

#### Changes by phase (what improved accuracy)

**Phase A — Judge model and prompt**

| Step | Location | Change | Effect |
|------|----------|--------|--------|
| A1 | `scraper/eval/auto_judge.py` | Default judge `qwen2.5:7b`; timeout 300 s; `num_ctx` 1536 | Stricter than 1.5B |
| A2 | `scraper/prompts/claim_auto_judge.py` | Balanced prompt: explicit ACCEPT patterns for HF clinical rules; clear REJECT for noise | Reduced false rejects on valid lab/neonate rules |
| A3 | Comparison | 1.5B vs 7B on same corpus | 1.5B 71% optimistic; **7B used for thesis** |

**Phase B — Filter passes 1–7**

| Pass | Change | Accuracy impact |
|------|--------|----------------|
| 1 | `drop_type_mismatch` — evidence must match type cues | +15 pp strict structural |
| 2 | Hard types require `drug` | Fewer orphan rules |
| 3 | `OFF_SCOPE_DRUG_TOKENS` (~40 agents) | −17% corpus; cleaner scope |
| 4 | `heuristic_noise_score`, `is_weak_span` | Remove boilerplate |
| 5 | `TRIAL_PK_DEVICE_PATTERNS` | Remove RCT/PK/device text |
| 6 | Empty-drug ADR/interaction | −45 claims |
| 7 | Non-actionable ADR | −1,618 ADR rows; strict **84.8%** |

**Phase C — Pass 8 dose/renal (extractor + filter)**

| Location | Change | Accuracy impact |
|----------|--------|----------------|
| `scraper/validation/claim_type_gates.py` (new) | Shared gates: dose = mg/mcg + dosing context; renal = eGFR/CrCl threshold or renal + action | Foundation for pass 8 |
| `scraper/process/create_claims.py` | Regex `_matches_claim_type` uses gates; LLM path gated by `_filter_prescriptive_only` | Fewer bad dose/renal; observational claims dropped |
| `scraper/semantic/claim_extraction.py` | LLM `_build_claim` rejects early via gates | LLM path aligned with regex |
| `scraper/prompts/claim_extraction.py` | Rules 14–15 for dose mg and renal thresholds | Steers LLM extraction |
| `scraper/validation/evidence_claim_validation.py` | Drug mismatch elevated from warning to critical issue; aligned=False on drug absence | Wrong-drug claims rejected before knowledge base |
| `filter_claims_for_quality.py` pass 8 | `drop_weak_dose_renal` | Dose **50%→90%**, renal **50%→80%** |

Drug-interaction precision rose from 30% (raw) to 80% after filtering. Adverse-reaction precision rose from 20% (raw) to 70% on pass 8 safety. Two recent changes further tighten the pipeline. Drug-mismatch elevation treats claims whose evidence text does not contain the named drug as critical rejections rather than warnings, preventing wrong-drug extractions from entering the knowledge base. The prescriptive filter for `population_constraint` applies the same observational-rejection logic to both regex and LLM extraction paths, removing "safety not established" and "has been reported" statements before they reach the evidence-alignment validator.

Filtering improves the usable claim set for GraphRAG explanation without changing clinician vignette accuracy in Section 5.3. Runtime safety continues to rely on governed PostgreSQL catalogs and verification. Next steps are syncing the latest S3 constraint catalogs into the local mirror, clinician gold review for `population_constraint`, and clinical review of remaining dose-safety refinement items.
