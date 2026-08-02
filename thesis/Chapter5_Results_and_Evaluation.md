# CHAPTER 5: RESULTS AND EVALUATION

Chapter 5 reports measured behavior of the heart failure clinical decision support system on evaluation hardware, with cardiologist review and usability testing. The central question is whether the hybrid design from Chapters 3 and 4 is adequate for supervised clinical use. Sections cover the knowledge pipeline, chat service, interface, comparisons, error patterns, safety checks, and limits on what the metrics can prove.

## 5.0 Predefined Success Criteria

Before implementation, the study defined targets against which Part II results would be judged. The study succeeds on its primary claims if the system meets the following criteria, assessed in the sections below.

Recommendation accuracy against guideline-aligned expert review should reach at least 90 percent on structured recommendation objects (drug class, action status, major safety flags), measured on curated vignettes reviewed by cardiologists. Mean end-to-end response time should remain under 10 seconds on reference hardware, measured from chat submission through SSE completion. For hard contraindications in curated safety cases, the system must not miss absolute avoid rules encoded as hard_block tiers; failure on any mandatory avoid scenario disqualifies success regardless of average accuracy. Cardiologist satisfaction on a five-point Likert scale should average at least 4.0, including clinical usefulness, trust in safety alerts, and bilingual usability. The interface must support Vietnamese and English without losing conversation context across language toggles. The knowledge pipeline should automate extraction for major GDMT drug classes into reviewable catalogs that clinical leads can govern without redeploying application code. These criteria combine accuracy, safety, latency, maintainability, and usability aligned to Osheroff-style workflow adequacy [17].

## 5.1 Experimental Environment

### 5.1.1 Hardware and Software Setup

All evaluation runs used a dedicated server with a 16-core CPU, 32 GB of RAM, a 500 GB solid-state drive, and an NVIDIA RTX 3080 graphics card with 10 GB of video memory. The operating system was Ubuntu 22.04 LTS. The application stack included Python 3.11, PostgreSQL 15 for governed clinical rules, Redis 7 for caching, Neo4j 5 for the knowledge graph, ChromaDB for vector search, LocalStack as an S3-compatible object store, and Ollama for local large language model inference.

The system used the same model pairing intended for production: BGE-M3 for embeddings and section filtering, Qwen2.5-7B-Instruct for clinician-facing answers, and Qwen2.5-1.5B for lightweight verification tasks. The backend ran under Docker Compose with FastAPI async workers, server-sent event streaming for chat responses, and hybrid GraphRAG retrieval that combined dense vector search, keyword search, and graph traversal before merging results.

This matters because the reported numbers reflect the full integrated system, not isolated module benchmarks. Latency was timed across the complete chat path. Accuracy was scored on structured recommendation objects, not on free-form answer text. Knowledge metrics came from full pipeline runs over the complete drug manifest rather than from small hand-picked samples.

### 5.1.2 Evaluation Data

The knowledge base combined FDA drug labels, heart failure clinical guidelines, and derived rule catalogs. The sources manifest registered 127 drugs. For full evaluation, 60 drugs were fully integrated through extraction, classification, and database sync. Eight heart failure guidelines were included. The system also held 6,032 constraint rules, 1,096 interaction rules, four GDMT policies, and 13 dose-safety warnings. Dose rule completion was still in progress at evaluation time, so dose planning was less complete than constraint and interaction coverage.

The gap between 127 registered drugs and 60 fully integrated drugs reflects pipeline coverage still in progress. Accuracy testing focused on the 60-drug subset where constraint and interaction catalogs were complete enough for reliable automated reasoning.

## 5.2 Knowledge Base Construction Results

### 5.2.1 Drug Label Extraction

The ingestion pipeline downloaded drug labels from DailyMed, parsed XML sections, filtered clinical content, split text into chunks, and extracted structured claims. Across the 60 integrated drugs, the pipeline extracted 4,136 sections, averaging about 69 sections per drug. Extraction succeeded on 94.2% of drugs, with an average processing time of about 45 seconds per drug.

Drug classes varied in label length. Beta blockers contributed the largest total section count because many agents were processed. ARNI labels tended to be longer per drug because of extensive warning language. SGLT2 inhibitor labels were shorter on average after filtering, consistent with newer label formats.

These results show that automated ingestion can populate a usable knowledge base at scale without manual transcription of every label section. Failures were mostly due to lookup mismatches for drug names not yet present in the acquisition registry, which foreshadowed later problems with Vietnamese brand names during chat intake.

### 5.2.2 Section Filtering

Not every section of a drug label is clinically useful. Some parts describe storage, packaging, or manufacturer details. The system therefore used a three-step filter: keyword matching first, semantic similarity second, and large language model review only for uncertain cases.

Across drug labels and guidelines, 5,381 sections entered filtering. The filter retained 95.0% of sections. About 65.5% were accepted by keyword rules alone, 22.9% by embedding similarity, and only 6.6% needed borderline LLM review. Just 5.0% were dropped as non-clinical.

This design was intentionally cost-aware. A naive approach that sent every section to an LLM would have required roughly 5,381 model calls per ingestion cycle. The observed pipeline needed only 354 borderline reviews, a reduction of more than 93%. Guideline documents needed more borderline review than FDA labels because guideline headings and wording vary more across publishers.

The filter kept almost all clinically relevant content while avoiding unnecessary model use, which matters when hospitals refresh knowledge bases after label or guideline updates.

### 5.2.3 Rule Classification

After extraction, rules were classified by safety level and recommended action. Of 6,032 constraint-related artifacts, 53.9% were immediately usable, 35.2% needed condition refinement before deployment, and 11.1% were treated as hard blocks representing absolute contraindications.

By action type, 24.2% were classified as "avoid," 35.4% as "consider with caution," 27.8% as "consider," and 12.7% as "continue." The large share of cautionary rules helps explain why the system generates many alerts during evaluation. Hard block rules feed directly into fail-closed safety behavior and are never overridden by generated text.

The 35.2% refinement tier does not mean runtime failure. Those rules are held back from automated execution until clinical reviewers approve them. This governance step is deliberate: imperfect extractions should become review tasks, not silent prescribing logic.

### 5.2.4 Knowledge-Base Data Quality Audit

Volume counts alone do not prove that extracted knowledge is clinically usable. After the ingestion pipeline finished, we audited persisted artifacts with structural heuristics, an LLM semantic judge on stratified claim samples, and catalog-tier scans. The audit is documented in `evaluation/reports/accuracy_audit_20260728.md`. Auto-judge precision is a triage signal, not a cardiologist-certified gold standard.

Claims were re-extracted and are present in the workspace (`artifacts/claims/claims.jsonl`, 16,973 rows). Filtered outputs are `claims_filtered.jsonl` (6,296 rows after pass 8) and `claims_filtered_safety.jsonl` (4,440 rows without `guideline_recommendation`). Constraint and other governance catalogs are intended to live in the processed S3 bucket (`hf-cdss-processed`) and to be mirrored locally under `artifacts/` for evaluation. The quality tables below therefore separate content quality of claims that are on disk from catalog-tier counts for governance JSONL files present in the local mirror at audit time.

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

Dose-safety warnings are now 100% from raw claims (`claims_pipeline_dose_safety`); bundled baseline rows are 0 (previously 10/71 usable at 14%). Roughly half of dose-safety rows still need LLM trigger refinement (`refine_dose_safety_triggers`) before they become executable. Full audit: `evaluation/reports/data_quality_audit_20260730.md`.

Constraint rule files were not present under the local `artifacts/rules/` path used for this write-up, even though claims were. If constraint catalogs were re-extracted and uploaded to S3 after an earlier empty-bucket snapshot, their usable or refinement tier counts should be taken from a restored mirror (`sync_processed_from_s3`) rather than treated as permanently missing. The claim-quality findings below are independent of that restore step because `claims.jsonl` was already local.

#### Judge calibration and metric separation

We measured claim quality with a stratified LLM judge (`qwen2.5:7b`, balanced prompt, 10 claims per type, seed 42, timeout 300 s). The 1.5B judge previously reported 71.1% on filtered claims; that figure is optimistic. The 7B judge is stricter and is the default for thesis reporting.

Three metrics must not be conflated:

| Metric | Meaning | Latest result |
|--------|---------|---------------|
| Vignette recommendation accuracy (Section 5.3) | Structured CDSS cards vs cardiologist expectation | 94.0% |
| Claim LLM precision (safety-only, pass 8) | Semantic quality of individual KG claims (7B proxy) | 73.8% |
| Strict structural precision | Share passing all filter gates on a stratified sample | 100% after pass 8 |

High vignette accuracy does not imply every raw extracted claim is clinically precise. Runtime safety depends on governed PostgreSQL catalogs and verification; filtered claims mainly support GraphRAG explanation.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-5-1-eval-metrics-split.html" title="Figure 5.1 Evaluation metrics"></iframe>
  <figcaption><strong>Figure 5.1.</strong> Separation of vignette recommendation accuracy, claim LLM precision, and strict structural precision (Section 5.2.4).</figcaption>
</figure>

#### Staged filtering (passes 0–8)

We applied eight cumulative filter passes (`scraper/eval/filter_claims_for_quality.py`) and recorded structural quality after each step. **Table 5.0a** tracks corpus size and strict structural precision. **Table 5.0b** tracks LLM semantic precision across filter rounds. Reproducible JSON logs: `evaluation/reports/claim_filter_progression.json`, `auto_eval_20260729T094553Z.json`, `auto_eval_20260729T094630Z.json`.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-5-2-claim-filter-progression.html" title="Figure 5.2 Claim filter progression"></iframe>
  <figcaption><strong>Figure 5.2.</strong> Claim corpus reduction and quality gates across filter passes 0–8 (Section 5.2.4).</figcaption>
</figure>

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
| 8 Drop weak dose / renal | 6,296 | 1,324 | 37.1% | 100.0% | Dose/renal quality gates (pass 8) |

**Table 5.0b. LLM semantic precision across filter rounds** (qwen2.5:7b, balanced prompt)

| Corpus | Claims | Sample *n* | Overall LLM prec. | Hard-type prec. |
|--------|-------:|-----------:|--------------------:|----------------:|
| Raw (1.5b judge, historical) | 16,973 | 90 | 57.8% | 62.0% |
| Filtered pass 7 (all types) | 7,620 | 90 | 62.2% | 70.0% |
| Filtered pass 7 (safety-only) | 5,764 | 80 | 66.3% | 70.0% |
| Filtered pass 8 (all types) | **6,296** | **90** | **66.7%** | **70.0%** |
| **Filtered pass 8 (safety-only)** | **4,440** | **80** | **73.8%** | **70.0% |

Safety-only excludes `guideline_recommendation`, the noisiest type under the 7B judge (10% on pass 8).

**Table 5.0c. Per-claim-type LLM precision (pass 8, *n* = 10 per type)**

| Claim type | Pass 7 (7B) | Pass 8 (all) | Pass 8 (safety) | Note |
|------------|------------:|-------------:|----------------:|------|
| Contraindication | 80% | 80% | 80% | Stable |
| Usage constraint | 80% | 80% | 80% | Stable |
| Adverse reaction | 80% | 70% | 70% | Sample variance |
| Drug interaction | 70% | 80% | 80% | Improved |
| Hyperkalemia risk | 70% | 70% | 70% | Stable |
| Dose recommendation | 50% | 90% | 90% | Pass 8 + extractor gates |
| Renal constraint | 50% | 80% | 80% | Pass 8 + extractor gates |
| Population constraint | 50% | 40% | 40% | PK/demographic noise remains |
| Guideline recommendation | — | 10% | *(excluded)* | Not used for safety KG |

Pass 8 improved dose precision from 50% to 90% and renal precision from 50% to 80%. Population constraints still need clinician gold labeling or extractor fixes.

#### Changes by phase (what improved accuracy)

Phase A: judge model and prompt

| Step | Location | Change | Effect |
|------|----------|--------|--------|
| A1 | `scraper/eval/auto_judge.py` | Default judge `qwen2.5:7b`; timeout 300 s; `num_ctx` 1536 | Stricter than 1.5B |
| A2 | `scraper/prompts/claim_auto_judge.py` | Balanced prompt: explicit ACCEPT patterns for HF clinical rules; clear REJECT for noise | Reduced false rejects on valid lab/neonate rules |
| A3 | Comparison | 1.5B vs 7B on same corpus | 1.5B 71% optimistic; 7B used for thesis |

Phase B: filter passes 1–7

| Pass | Change | Accuracy impact |
|------|--------|-----------------|
| 1 | `drop_type_mismatch`: evidence must match type cues | +15 pp strict structural |
| 2 | Hard types require `drug` | Fewer orphan rules |
| 3 | `OFF_SCOPE_DRUG_TOKENS` (~40 agents) | −17% corpus; cleaner scope |
| 4 | `heuristic_noise_score`, `is_weak_span` | Remove boilerplate |
| 5 | `TRIAL_PK_DEVICE_PATTERNS` | Remove RCT/PK/device text |
| 6 | Empty-drug ADR/interaction | −45 claims |
| 7 | Non-actionable ADR | −1,618 ADR rows; strict 84.8% |

Phase C: pass 8 dose/renal (extractor + filter)

| Location | Change | Accuracy impact |
|----------|--------|-----------------|
| `scraper/validation/claim_type_gates.py` (new) | Shared gates: dose = mg/mcg + dosing context; renal = eGFR/CrCl threshold or renal + action | Foundation for pass 8 |
| `scraper/process/create_claims.py` | Regex `_matches_claim_type` uses gates | Fewer bad dose/renal at extract time |
| `scraper/semantic/claim_extraction.py` | LLM `_build_claim` rejects early via gates | LLM path aligned with regex |
| `scraper/prompts/claim_extraction.py` | Rules 14–15 for dose mg and renal thresholds | Steers LLM extraction |
| `filter_claims_for_quality.py` pass 8 | `drop_weak_dose_renal` | Dose 50%→90%, renal 50%→80% |

Drug-interaction precision rose from 30% (raw) to 80% after filtering. Adverse-reaction precision rose from 20% (raw) to 70% on pass 8 safety. Filtering improves the usable claim set for GraphRAG without changing clinician vignette accuracy in Section 5.3.

Residual rejects are mostly non-HF specialty drugs, soft guideline caveats, and population PK demographics. Runtime safety continues to rely on governed PostgreSQL catalogs and verification. Next steps are syncing the latest S3 constraint catalogs into the local mirror, clinician gold review for `population_constraint`, and clinical review of remaining dose-safety refinement items.

## 5.3 CDSS Chat Service Results

### 5.3.1 Recommendation Accuracy

Accuracy here means how often the system's structured recommendation matched what two independent cardiologists expected from guideline-concordant care. We evaluated 50 sample clinical cases drawn from treatment guidelines (`golden_cases.jsonl`). Each case was submitted as free text and processed through the full pipeline: patient intake, deterministic reasoning, hybrid retrieval, verification, and answer generation. Scoring used structured recommendation fields (drug class, action status, and primary safety flags), not free-form answer prose.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-5-3-vignette-eval.html" title="Figure 5.3 Vignette evaluation"></iframe>
  <figcaption><strong>Figure 5.3.</strong> Golden vignette path from free-text cases to cardiologist-scored structured recommendation accuracy (Section 5.3.1).</figcaption>
</figure>

Table 5.1 summarizes the overall recommendation metrics.

| Metric | Definition | Result |
|--------|------------|--------|
| Cases evaluated | Cardiologist-reviewed vignettes | 50 |
| Overall accuracy | Structured recommendation matched expert expectation | 94.0% |
| 95% confidence interval | Uncertainty range from sample size | 89.2% – 98.8% |
| Sensitivity | True warnings/recommendations correctly identified | 92.5% |
| Specificity | Cases correctly left without unnecessary action | 95.2% |
| Project target | Minimum overall accuracy | ≥ 90% |
| Target met? | Accuracy compared with target | Yes |

A confidence interval is a range that expresses uncertainty from sample size. With 50 cases, the true accuracy likely falls somewhere in that range. The result exceeded the project's 90% target.

Sensitivity slightly below specificity means the system errs toward caution: it is somewhat more likely to warn when warning is not strictly needed than to miss a case that needed attention. For medication safety, that bias is generally acceptable.

Table 5.2 breaks performance down by clinical focus area. Where a full precision–recall pair was not separately reported for every class, the table records the strongest available metric and a qualitative note from the review.

| Clinical focus | Primary metric | Result | Interpretation |
|----------------|----------------|-------:|----------------|
| ACE inhibitor / ARB / ARNI | Relative class performance | Best among GDMT classes | Strong catalog coverage and hard-block washout rules |
| Beta blocker | Relative class performance | Strong | Caution cases driven by heart rate and blood pressure |
| MRA | Recall | 89.3% | Lowest class recall; misses linked to missing labs or creatinine unit errors |
| SGLT2 inhibitor | Relative class performance | Strong when eGFR present | Weaker when renal labs missing |
| Drug interaction detection | F1 score | 97.1% | Strongest safety sub-task |
| Overall structured recommendation | Accuracy | 94.0% | Exceeds 90% target |

F1 score is a single number that balances precision and recall. An F1 of 97.1% for interactions means the system was highly reliable at finding true drug interaction problems while keeping false alarms relatively low. This strength came from both explicit interaction rules in PostgreSQL and retrieval of supporting evidence that verification agents could cross-check.

MRA recall at 89.3% means the system occasionally missed an MRA-related recommendation when one was expected. That pattern matched cases where laboratory values were incomplete or intake failed to normalize creatinine correctly.

These results support the core thesis claim: deterministic catalogs can carry safety authority, while retrieval and language models improve explanation without replacing structured decision logic. They should also be read together with Section 5.2.4: high vignette accuracy on structured cards does not imply that every raw extracted claim in the knowledge base is clinically precise.

### 5.3.2 System Performance and Latency

Latency means how long the user waits for a complete response. End-to-end latency was measured from the moment a chat message was sent until the streamed response finished.

The mean response time was 8.1 seconds. The median (P50) was 7.4 seconds, meaning half of requests finished faster than that. P95 was 12.6 seconds, meaning 95% of requests finished within that time. On average, the system met the under-10-second goal. The median also met the goal. Some slower cases still exceeded 10 seconds at the tail of the distribution.

Patient intake took a mean of 1.2 seconds. This confirms that regex-first intake avoids model calls on typical structured case presentations. GraphRAG retrieval averaged 0.8 seconds. Deterministic reasoning averaged 2.1 seconds. Verification averaged 0.5 seconds. LLM answer generation averaged 3.5 seconds and was the largest single contributor to total wait time.

Streaming delivery materially improved perceived speed. Clinicians often saw patient summary fields and recommendation cards within one to two seconds, even when the full answer took longer to finish. That early feedback made the system feel responsive during guided usability tasks.

### 5.3.3 Alert Rates and Alert Burden

Alert burden means how many safety alerts a clinician sees per patient. Before optimization, the system averaged 8.2 alerts per patient. After deduplication, tiered suppression, and consolidation of overlapping warnings, alert burden fell to 4.3 alerts per patient. That is a 47.6% reduction in alert volume.

Table 5.3 summarizes alert burden and false-positive rates after review.

| Alert metric | Before optimization | After optimization |
|--------------|--------------------:|-------------------:|
| Mean alerts per patient | 8.2 | 4.3 |
| Relative reduction | — | 47.6% |
| Overall false-positive rate | — | 9.2% |
| Drug-interaction false-positive rate | — | 8.5% |
| Renal-contraindication false-positive rate | — | 12.6% |

A false positive alert warns about a problem that reviewers judged not to be a real clinical concern in context. Drug interaction alerts were the most common trigger type and also had the lowest false-positive rate. Renal contraindication alerts had a higher false-positive rate, often because creatinine or eGFR information was incomplete or ambiguous in free-text intake.

These numbers sit in tension with safety sensitivity of 92.5%. A system tuned too aggressively to reduce alerts risks missing serious contraindications. The evaluation suggests the current operating point favors patient safety over minimal alert count, while still showing that alert fatigue can be reduced without removing hard blocks.

## 5.4 User Interface Results

### 5.4.1 Simplified Display

The interface translates technical drug class names and status codes into plain language appropriate for the selected locale. For example, "ACE inhibitor" with status "consider with caution" can be shown in English as "blood pressure medication" with "use with caution," or in Vietnamese with equivalent patient-friendly wording. This mapping is produced deterministically by the card summarizer, not by the main language model, so the on-screen status always matches the structured recommendation object.

Survey participants said this simplified display improved scan speed during rounds. Clinicians could read GDMT rows quickly while still opening structured evidence and numeric vitals in adjacent panels. Deterministic wording also avoids dangerous variability, such as rendering an "avoid" status with softer language.

### 5.4.2 Language Switching

The interface supports switching between Vietnamese and English while preserving conversation context. Simplified card text is regenerated for the new locale without rerunning full retrieval or deterministic reasoning. All test users rated language switching as easy to use. Switching completed in under 2 seconds, and no data loss was observed.

This confirms that localization is mostly a presentation concern in the current design. Expensive clinical inference and inexpensive language display are intentionally separated.

### 5.4.3 User Satisfaction

Twenty-five cardiologists completed a structured usability survey after guided tasks covering GDMT gap review, interaction checking, language toggling, and streaming chat. Scores used a 1-to-5 scale, where 5 means strongly agree or very satisfied.

Ease of use averaged 4.2. Clinical usefulness averaged 4.5, the highest score. Perceived recommendation accuracy averaged 4.1. User interface quality averaged 4.3. Response time averaged 4.0, the lowest score. Overall satisfaction averaged 4.22 out of 5.

Clinicians valued GDMT gap identification and interaction support even when they occasionally disagreed with a class-level suggestion. That pattern is common in decision support research: workflow help often matters as much as perfect autonomous correctness. Response time scored lower than other criteria, which aligns with the measured latency profile, but streaming partial results partially offset the wait.

## 5.5 Comparative Evaluation

### 5.5.1 Comparison with Other CDSS Systems

We compared the proposed system with published characteristics of Mediwis and Watson for Oncology along dimensions relevant to heart failure workflow deployment. This comparison is qualitative because public benchmarks do not always use identical tasks or latency definitions.

| Criterion | Proposed System | Mediwis | Watson for Oncology |
|-----------|-----------------|---------|---------------------|
| Domain focus | Heart failure | Multiple domains | Oncology |
| Knowledge sources | FDA labels + guidelines | Guidelines only | Guidelines + literature |
| LLM integration | Yes, with GraphRAG | No | Yes |
| Languages | Vietnamese and English | English only | English only |
| Real-time chat | Yes | No | Limited |
| Dosing support | Yes | No | No |
| Typical response time | Under 10 seconds median | Not reported | 30 to 90 seconds |

Relative to these systems, the proposed heart failure CDSS offers deeper domain specialization, hybrid retrieval with local model inference, bilingual presentation, interactive chat, and integrated dosing support. Its median response time is substantially lower than reported Watson latencies for comparable interactive use cases. Mediwis lacks real-time chat and LLM-based explanation. Watson offers broader literature coverage in oncology but does not provide the same heart failure GDMT specialization, bilingual card simplification, or sub-10-second median latency in this setting.

These comparisons should be read carefully. They describe architectural fit and published capabilities, not head-to-head accuracy on identical patient cases.

### 5.5.2 System Strengths

The evaluation highlighted several strengths tied directly to design choices. Deep heart failure focus enabled GDMT pillar evaluation and class-specific safety catalogs. Hybrid GraphRAG retrieval contributed to strong interaction performance and reliable ACE inhibitor, ARB, and ARNI recommendations. Cost-aware gating during ingestion and intake kept model use low while retaining 95% section coverage and 1.2-second mean intake time. Native Vietnamese support addressed a documented gap in English-only products. Verification agents and hard block tiers preserved fail-closed safety even when retrieved text sounded permissive. Streaming delivery and plain-language cards translated engineering metrics into clinician-perceived value, reflected in 4.22 out of 5 overall satisfaction.

### 5.5.3 Current System Limitations

Several limitations constrain how far these results generalize. Only 60 of 127 registered drugs were fully integrated in the accuracy cohort. Many medications commonly used in Vietnam, especially local brand names, were not yet reliably recognized. The system lacked HL7 or FHIR integration, so patient data had to be typed manually into chat rather than pulled from hospital systems. There was no mobile application; access was web-based only. LLM narrative text can still contain errors even when structured recommendations are correct, so human review remains necessary. Finally, evaluation was retrospective on curated vignettes rather than a prospective trial measuring patient outcomes.

## 5.6 Error Analysis and Improvements

### 5.6.1 Common Errors

Three error patterns appeared repeatedly during evaluation.

First, drug name extraction failed for some Vietnamese drug names because acquisition strings and intake lexicons were biased toward international nonproprietary names and United States brand labels. When a local brand could not be mapped to the same identifier used in rule catalogs, medications were omitted or misclassified. That reduced interaction completeness and GDMT coverage even though interaction F1 remained high on detected pairs.

Second, unit conversion errors occurred when creatinine was reported without explicit units. Regex intake captured the number but sometimes assigned the wrong unit, which propagated into incorrect eGFR estimates and renal alert false positives.

Third, missing laboratory values, especially eGFR, lowered recall for MRA and SGLT2 inhibitor recommendations. When creatinine, age, and sex were available, the system could estimate eGFR deterministically and flag it as derived rather than measured. When even those inputs were missing, eligibility rules lacked prerequisites.

Errors were less frequent in interaction checking and ACE inhibitor or ARB pathways where hard block rules compensate for some intake gaps. That confirms the value of layered safety design when natural language intake is imperfect.

### 5.6.2 Improvement Plan

Near-term priorities target root causes rather than symptoms. Vietnamese synonym integration into acquisition and intake lexicons should close the most frequent medication omission class. FHIR integration should populate creatinine, potassium, eGFR, and active medications from hospital systems, reducing reliance on free-text completeness. Medium-term work includes a mobile client and a dedicated drug interaction API for external systems. Longer-term work may include domain fine-tuning to reduce borderline intake and section-filter model calls, while keeping hard block enforcement deterministic regardless of model improvements.

## 5.7 Safety Evaluation

### 5.7.1 Safety Testing

Safety testing examined high-risk scenarios where incorrect advice could cause direct harm. Each case ran through the full recommendation and verification pipeline. Pass criteria required the structured recommendation to show "avoid" or an appropriate warning, regardless of how the language model phrased the explanation.

Four curated scenarios all passed: ACE inhibitor plus ARNI contraindication, SGLT2 inhibitor initiation at eGFR below 20, hyperkalemia with MRA therapy, and beta blocker initiation in bradycardia. Verification agents also checked that generated answers did not contradict structured avoid statuses.

These tests validate the architectural separation between deterministic safety classification and generative explanation. Safety logic lives in governed catalogs and reasoning services, not in model prose alone.

### 5.7.2 Alert Fatigue Analysis

Alert optimization used tiered classification, deduplication of overlapping warnings, and suppression of redundant interaction alerts when a parent avoid status already implied stopping a drug. These techniques reduced alerts per patient from 8.2 to 4.3 and lowered override rate from 72% to 45%.

The remaining alert burden is still meaningful. Deployment should include education so clinicians can distinguish hard blocks requiring immediate action from cautionary monitoring prompts that may be acknowledged and deferred. Further tuning of renal precaution thresholds will likely improve once structured laboratory feeds reduce eGFR uncertainty.

## 5.8 Threats to Validity

Evaluation conclusions must be read with explicit validity boundaries.

Internal validity is limited by sample size. Fifty cases are enough to show the system exceeded the 90% accuracy target, but per-class metrics such as MRA recall can move noticeably with a single misclassified case. Two cardiologist reviewers may share similar training backgrounds. Latency was measured on a dedicated GPU server and may differ on lower-resource hospital hardware.

External validity is limited because vignettes drawn from guidelines may be clearer than messy real-world notes. The 60-drug integrated subset underrepresents broader polypharmacy outside modeled classes. Vietnamese evaluation focused on interface switching and limited intake cases rather than a full local formulary. No prospective outcomes such as readmission or GDMT uptitration were measured.

Construct validity matters because accuracy was scored on structured JSON fields, not on every token of generated narrative or on complete dose precision while dose rules remained incomplete. Satisfaction scores measure perceived usefulness, not objective error rates. Section retention measures preprocessing coverage, not guaranteed correctness of every extracted rule.

Conclusion validity is affected because ablation reasoning in this chapter is qualitative. We did not rerun the system with individual components removed in controlled experiments. Comparative evaluation uses published feature descriptions rather than identical-case benchmarking.

These limits do not invalidate the core findings. They define the conditions under which claims apply: clinician-supervised decision support on evaluated hardware, with structured cards treated as authoritative over chat prose.

## 5.9 Discussion

Taken together, the results describe a coherent performance profile shaped by the hybrid architecture's division of labor.

Knowledge construction metrics show that automated ingestion can populate governable catalogs at scale. Extraction succeeded on 94.2% of drugs, section filtering retained 95.0% of content with only 6.6% borderline model review, and 53.9% of extracted rules were immediately usable. At the same time, 35.2% of rules still need refinement and dose rule completion remains unfinished, so human clinical governance remains essential. Staged claim filtering (passes 0–8) raised safety-only LLM semantic precision from 57.8% (raw, 1.5B judge) to 73.8% (pass 8, 7B judge) while retaining 4,440 safety claims; strict structural precision on the stratified sample reached 100% after pass 8, with dose and renal types improving from 50% to 90% and 80% respectively. Runtime safety still depends on governed catalogs and verification, not on raw claim volume alone.

Query-time metrics show that those catalogs, when combined with hybrid intake and retrieval, meet the thesis success criteria on median performance. Accuracy reached 94.0%, mean latency was 8.1 seconds with a median of 7.4 seconds, and interaction F1 was 97.1%. Usability results translate those engineering outcomes into clinician value: 4.22 out of 5 overall satisfaction and 4.5 out of 5 for clinical usefulness.

Error and alert analyses connect pipeline gaps to runtime symptoms in traceable ways. Vietnamese drug name gaps reduce medication recall. Creatinine unit ambiguity inflates renal false positives. Missing eGFR depresses MRA recall. Alert optimization reduced burden from 8.2 to 4.3 alerts per patient without removing hard blocks.

Mapping results to the predefined success criteria in Section 5.0, five of six targets were fully met. Recommendation accuracy exceeded 90%. Mean and median response times met the under-10-second goal. Hard contraindication scenarios passed all curated safety tests. User satisfaction exceeded 4.0 out of 5. Bilingual switching worked in under 2 seconds with no data loss. Knowledge pipeline completeness was only partially met because dose rules remained in progress and only 60 of 127 manifest drugs were fully integrated.

The evaluation supports deployment as a clinician-supervised GDMT gap identification and interaction checking assistant during ward rounds or outpatient visits, not as autonomous prescribing software. Prospective deployment should track override rates, intake completeness, time to decision, and correlation between missing laboratories and lower recall for MRA and SGLT2 inhibitor classes. Outcome studies remain the ultimate test beyond vignette accuracy.

All quantitative results in this chapter come from the Docker Compose stack and configuration documented in Chapter 4. Reproducing them requires the synchronized approved-rule snapshot, the listed Ollama models, the 50-case vignette suite, and the cardiologist scoring rubric aligned to structured recommendation fields. Latency figures reflect full stream completion; first structured events typically arrive within about two seconds on evaluation hardware. Independent replication should report both mean and percentile latency, structured accuracy separate from narrative review, and section filter tier breakdowns rather than headline accuracy alone.

Chapter 5 reported experimental configuration, knowledge construction metrics, chat service accuracy and latency, alert and usability results, comparative analysis, error analysis, safety evaluation, threats to validity, and clinical implications. Chapter 6 synthesizes contributions, limitations, and future work in relation to the thesis research questions.
