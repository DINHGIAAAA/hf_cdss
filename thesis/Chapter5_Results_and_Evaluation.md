# CHAPTER 5: RESULTS AND EVALUATION

This chapter reports what the heart failure clinical decision support system achieved when we built it, ran it on realistic hardware, and measured it with cardiologist review and usability testing. The goal is to answer a practical question: does the hybrid design described in earlier chapters actually work well enough for supervised clinical use? We report results for the knowledge base pipeline, the chat recommendation service, the user interface, comparisons with other systems, common errors, safety behavior, and the limits of what these numbers can prove.

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

In plain terms, the filter kept almost all clinically relevant content while avoiding unnecessary model use. That balance is important for hospitals that must refresh knowledge bases when labels or guidelines change.

### 5.2.3 Rule Classification

After extraction, rules were classified by safety level and recommended action. Of 6,032 constraint-related artifacts, 53.9% were immediately usable, 35.2% needed condition refinement before deployment, and 11.1% were treated as hard blocks representing absolute contraindications.

By action type, 24.2% were classified as "avoid," 35.4% as "consider with caution," 27.8% as "consider," and 12.7% as "continue." The large share of cautionary rules helps explain why the system generates many alerts during evaluation. Hard block rules feed directly into fail-closed safety behavior and are never overridden by generated text.

The 35.2% refinement tier does not mean runtime failure. Those rules are held back from automated execution until clinical reviewers approve them. This governance step is deliberate: imperfect extractions should become review tasks, not silent prescribing logic.

### 5.2.4 Knowledge-Base Data Quality Audit

Volume counts alone do not prove that extracted knowledge is clinically usable. After the ingestion pipeline finished, we audited the persisted artifacts with structural heuristics, an LLM semantic judge on stratified claim samples, and catalog-tier scans. The audit is documented in `evaluation/reports/accuracy_audit_20260728.md`. Auto-judge precision is a triage signal, not a cardiologist-certified gold standard.

Claims were re-extracted and are present in the workspace (`artifacts/claims/claims.jsonl`, 16,973 rows). Constraint and other governance catalogs are intended to live in the processed S3 bucket (`hf-cdss-processed`) and to be mirrored locally under `artifacts/` for evaluation. The quality tables below therefore separate **content quality of claims that are on disk** from **catalog-tier counts for governance JSONL files present in the local mirror at audit time**.

Local governance catalogs available for counting at audit time:

| Catalog | Count | Usable | Needs refinement | Rejected |
|---------|------:|-------:|-----------------:|---------:|
| Claims (`claims.jsonl`) | 16,973 | — | — | — |
| Interaction rules | 1,766 | 1,081 (61%) | 661 (37%) | 24 (1%) |
| GDMT policies | 1,880 | 1,880 (100%) | 0 | 0 |
| Dose rules | 139 | 137 (99%) | 2 (1%) | 0 |
| Dose-safety warnings | 71 | 10 (14%) | 60 (85%) | 1 (1%) |
| Constraint rules (`artifacts/rules/*.jsonl`) | Not in local mirror at audit | — | — | — |

Constraint rule files were not present under the local `artifacts/rules/` path used for this write-up, even though claims were. If constraint catalogs were re-extracted and uploaded to S3 after an earlier empty-bucket snapshot, their usable or refinement tier counts should be taken from a restored mirror (`sync_processed_from_s3`) rather than treated as permanently missing. The claim-quality findings below are independent of that restore step because `claims.jsonl` was already local.

Claim semantic quality was estimated on a stratified sample with an LLM judge (`qwen2.5:1.5b`, 10 claims per type, *n* = 90). On the raw claim file, overall estimated precision was 57.8% and hard clinical types averaged 62.0%. Heuristic-only checks on a larger sample (*n* = 270) scored 98.5%, which is over-optimistic because heuristics mainly catch empty or noisy schema rather than clinical correctness.

| Claim type | Estimated precision (LLM judge, raw) | Accept / Reject | Priority |
|------------|-------------------------------------:|-----------------|----------|
| Contraindication | 100% | 10 / 0 | OK |
| Dose recommendation | 80% | 8 / 2 | Medium |
| Renal constraint | 80% | 8 / 2 | Medium |
| Guideline recommendation | 60% | 6 / 4 | Medium |
| Hyperkalemia risk | 60% | 6 / 4 | Medium |
| Usage constraint | 50% | 5 / 5 | High |
| Population constraint | 40% | 4 / 6 | High |
| Drug interaction | 30% | 3 / 7 | Critical |
| Adverse reaction | 20% | 2 / 8 | Critical |

We then applied staged filters and wrote `claims_filtered.jsonl`. Round 1 kept 11,204 claims and raised LLM precision to 67.8%. Round 2 added trial/PK/device noise removal and non-actionable ADR drops, retaining **8,248** claims (48.6% of baseline) with LLM precision **71.1%** and hard-type precision **74.0%**. An over-aggressive formulary-only experiment that left only 1,546 claims was discarded because LLM precision fell to 61.1%.

**Table 5.0a. Claim quality after each filter pass (round 2)**

| Pass | Claims left | Retain % | Strict structural precision | Notes |
|------|------------:|---------:|----------------------------:|-------|
| 0 Baseline (raw) | 16,973 | 100.0% | 54.8% | Type–evidence mismatches common |
| 1 Type–evidence gate | 12,445 | 73.3% | 72.6% | Dropped 4,528 mismatched claims |
| 2 Require drug on hard types | 12,084 | 71.2% | 76.3% | Dropped 361 hard claims without drug |
| 3 Drop off-scope drugs | 10,754 | 63.4% | 85.6% | Expanded peripheral-drug list |
| 4 Drop noise / weak spans | 10,697 | 63.0% | 87.8% | Residual schema noise |
| 5 Drop trial / PK / device text | 10,099 | 59.5% | 90.0% | RCT arms, NDC blocks, pen instructions |
| 6 Drop empty-drug ADR/interaction | 10,054 | 59.2% | 89.6% | Hard-to-bind GraphRAG rows |
| 7 Drop non-actionable ADR | 8,248 | 48.6% | 100.0% | Table-like ADR without action verbs |

**Table 5.0b. LLM semantic precision across filter rounds** (*n* = 90, same seed)

| Round | Claims | Overall LLM precision | Hard-types LLM | Change vs raw |
|-------|-------:|----------------------:|---------------:|--------------:|
| Raw | 16,973 | 57.8% | 62.0% | — |
| Round 1 (passes 1–4) | 11,204 | 67.8% | 72.0% | +10.0 pp |
| Round 2 (passes 1–7, current) | 8,248 | 71.1% | 74.0% | +13.3 pp |

Drug-interaction precision rose from 30% to 80%, and adverse-reaction precision from 20% to 50%. Filtering improves the usable claim set for GraphRAG without changing clinician vignette accuracy in Section 5.3. Full logs: `evaluation/reports/claim_filter_progression.md`.

Residual rejects are mostly non-HF specialty drugs (esmolol, ophthalmic beta blockers, potassium binders) and soft guideline caveats. Runtime safety continues to rely on governed PostgreSQL catalogs and verification.

These findings motivate the governance design already used at query time: deterministic catalogs and hard-block rules carry safety authority, while filtered GraphRAG claims support explanation. Next steps are syncing the latest S3 constraint catalogs into the local mirror and clinical review of remaining dose-safety refinement items.

## 5.3 CDSS Chat Service Results

### 5.3.1 Recommendation Accuracy

**Accuracy** here means how often the system's structured recommendation matched what two independent cardiologists expected from guideline-concordant care. We evaluated 50 sample clinical cases drawn from treatment guidelines (`golden_cases.jsonl`). Each case was submitted as free text and processed through the full pipeline: patient intake, deterministic reasoning, hybrid retrieval, verification, and answer generation. Scoring used structured recommendation fields (drug class, action status, and primary safety flags), not free-form answer prose.

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

**Sensitivity** slightly below **specificity** means the system errs toward caution: it is somewhat more likely to warn when warning is not strictly needed than to miss a case that needed attention. For medication safety, that bias is generally acceptable.

Table 5.2 breaks performance down by clinical focus area. Where a full precision–recall pair was not separately reported for every class, the table records the strongest available metric and a qualitative note from the review.

| Clinical focus | Primary metric | Result | Interpretation |
|----------------|----------------|-------:|----------------|
| ACE inhibitor / ARB / ARNI | Relative class performance | Best among GDMT classes | Strong catalog coverage and hard-block washout rules |
| Beta blocker | Relative class performance | Strong | Caution cases driven by heart rate and blood pressure |
| MRA | Recall | 89.3% | Lowest class recall; misses linked to missing labs or creatinine unit errors |
| SGLT2 inhibitor | Relative class performance | Strong when eGFR present | Weaker when renal labs missing |
| Drug interaction detection | F1 score | 97.1% | Strongest safety sub-task |
| Overall structured recommendation | Accuracy | 94.0% | Exceeds 90% target |

**F1 score** is a single number that balances precision and recall. An F1 of 97.1% for interactions means the system was highly reliable at finding true drug interaction problems while keeping false alarms relatively low. This strength came from both explicit interaction rules in PostgreSQL and retrieval of supporting evidence that verification agents could cross-check.

MRA recall at 89.3% means the system occasionally missed an MRA-related recommendation when one was expected. That pattern matched cases where laboratory values were incomplete or intake failed to normalize creatinine correctly.

These results support the core thesis claim: deterministic catalogs can carry safety authority, while retrieval and language models improve explanation without replacing structured decision logic. They should also be read together with Section 5.2.4: high vignette accuracy on structured cards does not imply that every raw extracted claim in the knowledge base is clinically precise.

### 5.3.2 System Performance and Latency

**Latency** means how long the user waits for a complete response. End-to-end latency was measured from the moment a chat message was sent until the streamed response finished.

The mean response time was 8.1 seconds. The median, called **P50**, was 7.4 seconds, meaning half of requests finished faster than that. **P95** was 12.6 seconds, meaning 95% of requests finished within that time. On average, the system met the under-10-second goal. The median also met the goal. Some slower cases still exceeded 10 seconds at the tail of the distribution.

Patient intake took a mean of 1.2 seconds. This confirms that regex-first intake avoids model calls on typical structured case presentations. GraphRAG retrieval averaged 0.8 seconds. Deterministic reasoning averaged 2.1 seconds. Verification averaged 0.5 seconds. LLM answer generation averaged 3.5 seconds and was the largest single contributor to total wait time.

Streaming delivery materially improved perceived speed. Clinicians often saw patient summary fields and recommendation cards within one to two seconds, even when the full answer took longer to finish. That early feedback made the system feel responsive during guided usability tasks.

### 5.3.3 Alert Rates and Alert Burden

**Alert burden** means how many safety alerts a clinician sees per patient. Before optimization, the system averaged 8.2 alerts per patient. After deduplication, tiered suppression, and consolidation of overlapping warnings, alert burden fell to 4.3 alerts per patient. That is a 47.6% reduction in alert volume.

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

Ease of use averaged 4.2. Clinical usefulness averaged 4.5, the highest score. Perceived recommendation accuracy averaged 4.1. User interface quality averaged 4.3. Response time averaged 4.0, the lowest score. Overall **satisfaction** averaged 4.22 out of 5.

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

Four curated scenarios all passed: ACE inhibitor plus ARNI contraindication, SGLT2 inhibitor initiation at eGFR below 20, hyperkalemia with MRA therapy, and beta blocker initiation in bradycardia. Verification agents additionally checked that generated answers did not contradict structured avoid statuses.

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

Knowledge construction metrics show that automated ingestion can populate governable catalogs at scale. Extraction succeeded on 94.2% of drugs, section filtering retained 95.0% of content with only 6.6% borderline model review, and 53.9% of extracted rules were immediately usable. At the same time, 35.2% of rules still need refinement and dose rule completion remains unfinished, so human clinical governance remains essential. Staged claim filtering raised LLM semantic precision from 57.8% to 67.8% while retaining 11,204 of 16,973 claims, and strict structural precision on the stratified sample rose from 69.6% to 100% across filter passes. Runtime safety still depends on governed catalogs and verification, not on raw claim volume alone.

Query-time metrics show that those catalogs, when combined with hybrid intake and retrieval, meet the thesis success criteria on median performance. Accuracy reached 94.0%, mean latency was 8.1 seconds with a median of 7.4 seconds, and interaction F1 was 97.1%. Usability results translate those engineering outcomes into clinician value: 4.22 out of 5 overall satisfaction and 4.5 out of 5 for clinical usefulness.

Error and alert analyses connect pipeline gaps to runtime symptoms in traceable ways. Vietnamese drug name gaps reduce medication recall. Creatinine unit ambiguity inflates renal false positives. Missing eGFR depresses MRA recall. Alert optimization reduced burden from 8.2 to 4.3 alerts per patient without removing hard blocks.

Mapping results to the thesis success criteria from Chapter 1, five of six targets were fully met. Recommendation accuracy exceeded 90%. Mean and median response times met the under-10-second goal. Hard contraindication scenarios passed all curated safety tests. User satisfaction exceeded 4.0 out of 5. Bilingual switching worked in under 2 seconds with no data loss. Knowledge pipeline completeness was only partially met because dose rules remained in progress and only 60 of 127 manifest drugs were fully integrated.

The evaluation supports deployment as a clinician-supervised GDMT gap identification and interaction checking assistant during ward rounds or outpatient visits, not as autonomous prescribing software. Prospective deployment should track override rates, intake completeness, time to decision, and correlation between missing laboratories and lower recall for MRA and SGLT2 inhibitor classes. Outcome studies remain the ultimate test beyond vignette accuracy.

All quantitative results in this chapter come from the Docker Compose stack and configuration documented in Chapter 4. Reproducing them requires the synchronized approved-rule snapshot, the listed Ollama models, the 50-case vignette suite, and the cardiologist scoring rubric aligned to structured recommendation fields. Latency figures reflect full stream completion; first structured events typically arrive within about two seconds on evaluation hardware. Independent replication should report both mean and percentile latency, structured accuracy separate from narrative review, and section filter tier breakdowns rather than headline accuracy alone.

Chapter 5 reported experimental configuration, knowledge construction metrics, chat service accuracy and latency, alert and usability results, comparative analysis, error analysis, safety evaluation, threats to validity, and clinical implications. Chapter 6 synthesizes contributions, limitations, and future work in relation to the thesis research questions.
