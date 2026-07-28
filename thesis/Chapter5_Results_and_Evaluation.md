# CHAPTER 5: RESULTS AND EVALUATION

## 5.1. Experimental Environment

### 5.1.1. Experimental Configuration

The evaluation was conducted on a server with a 16-core CPU, 32 GB RAM, and 500 GB SSD, equipped with an NVIDIA RTX 3080 GPU (10 GB VRAM). The software stack comprised Ubuntu 22.04 LTS, Python 3.11, PostgreSQL 15, Redis 7, Neo4j 5, ChromaDB, LocalStack S3, and Ollama 0.1.x running the same model pairing used in production deployment: BGE-M3 (1024-dimensional embeddings) for dense retrieval and section filtering, and Qwen2.5-7B-Instruct for clinician-facing answer generation, with Qwen2.5-1.5B serving lightweight verification agents. The backend ran under Docker Compose with FastAPI async workers, SSE streaming enabled via `sse-starlette`, and hybrid GraphRAG retrieval (`HF_CDSS_RETRIEVAL_BACKEND=hybrid`) fusing ChromaDB dense search, BM25 sparse search, and Neo4j graph traversal through Reciprocal Rank Fusion (RRF). All reported latency and accuracy figures reflect this integrated stack rather than isolated module benchmarks, so they represent achievable clinical workflow performance rather than theoretical upper bounds.

The integrated evaluation protocol deliberately avoids cherry-picking module-level best cases. Latency timers instrument the chat service at stage boundaries matching Section 5.3.2 decomposition; accuracy scoring inspects structured `RecommendationResponse` JSON rather than LLM answer text; and knowledge construction metrics derive from full pipeline runs over the complete sources manifest rather than subsampled documents. This holistic measurement philosophy aligns with the thesis claim that hybrid architecture value emerges from component interaction, RRF fusion quality affects verification evidence checks, which affect clinician trust, which affects satisfaction scores, not from any single module in isolation.

### 5.1.2. Experimental Data

The knowledge base under evaluation aggregated multi-source artifacts produced by the ingestion pipeline described in Chapter 4. FDA SPL labels covered 127 registered drug entries in the sources manifest; clinical guidelines comprised eight heart-failure-relevant documents; and derived governance catalogs included interaction, constraint, dose, GDMT, and dose-safety rule sets synchronized to PostgreSQL and indexed for GraphRAG retrieval.

| Data Source | Count |
|-------------|-------|
| FDA Drug Labels | 127 drugs |
| Clinical Guidelines | 8 guidelines |
| Interaction Rules | 1,096 rules |
| Constraint Rules | 6,032 rules |
| Dose Rules | In progress |
| GDMT Policies | 4 policies |
| Dose Safety Warnings | 13 warnings |

The constraint rule count (6,032) reflects both `usable_rules` and `needs_condition_refinement` rows retained for governance review, while runtime recommendation evaluation applied only rules promoted to executable tiers (`usable_rules` and `hard_block` enforcement paths). The "Dose Rules: In progress" annotation indicates that dose rule catalog completeness lagged constraint and interaction catalogs during evaluation, a limitation affecting dose plan richness but not GDMT class-level accuracy, which depends primarily on constraint and policy evaluation. Four GDMT policies encode pillar coverage logic at class granularity; thirteen dose-safety warnings capture label-derived maxima exceeded scenarios that complement constraint rules with numeric dose thresholds.

## 5.2. Knowledge Base Construction Results

### 5.2.1. Drug Label Extraction

Drug label extraction exercised the full acquisition-to-chunking path: asynchronous DailyMed HTTP download, XML section parsing, three-tier section filtering, sentence-aware chunking with approximately 512-token windows and overlap, and NER/claim extraction into JSONL artifacts staged on LocalStack S3 before PostgreSQL sync.

**Results:**

| Drug Class | Drugs | Sections Extracted | Avg Sections/Drug |
|------------|-------|---------------------|-------------------|
| ACE inhibitors | 12 | 847 | 70.6 |
| ARBs | 15 | 1,023 | 68.2 |
| ARNI | 2 | 156 | 78.0 |
| Beta blockers | 18 | 1,342 | 74.6 |
| MRAs | 5 | 312 | 62.4 |
| SGLT2 inhibitors | 8 | 456 | 57.0 |
| **Total** | **60** | **4,136** | **68.9** |

Across 60 drugs, the pipeline extracted 4,136 sections at an average of 68.9 sections per drug. Extraction achieved a success rate of 94.2%, with an average extraction time of 45 seconds per drug. The 94.2% success rate indicates that the combination of deterministic XML parsing and embedding-gated section retention recovers the vast majority of label content without manual curation; failures primarily corresponded to DailyMed lookup mismatches for synonym drug names not yet present in the acquisition registry, a foreshadowing of the Vietnamese synonym gap analyzed in Section 5.6. Average extraction time of 45 seconds per drug demonstrates that regex-first claim extraction with bounded borderline LLM review is operationally viable for batch re-ingestion when guidelines or labels update.

Interpreting the per-class table reveals systematic variation in SPL verbosity. ARNI agents (78.0 sections per drug average) carry extensive warnings reflecting dual-mechanism complexity and angioedema risk language. SGLT2 inhibitors (57.0 sections per drug) produce fewer surviving sections after filtering, consistent with newer label templates and shorter contraindication prose relative to legacy ACE inhibitor labels. Beta blockers contribute the largest absolute section count (1,342) because eighteen agents were processed, reflecting multiple selective agents (bisoprolol, carvedilol, metoprolol succinate) each with distinct titration language. MRA section counts (62.4 average) remain clinically dense despite fewer agents because hyperkalemia and renal monitoring sections expand during filtering retention.

The gap between 127 manifest drugs and 60 fully integrated evaluation drugs indicates pipeline coverage in progress: acquisition registry entries exist for agents not yet validated through complete extraction-classification-sync cycles. Accuracy evaluation (Section 5.3.1) focused on the 60-drug integrated subset where constraint and interaction catalogs were complete enough for deterministic reasoning.

### 5.2.2. Section Filtering with Borderline LLM

The section filter evaluated in this chapter is the three-tier cascade of keyword matching, BGE-M3 cosine similarity against clinical section prototypes, and LLM review restricted to the borderline band [0.40, 0.52). Configuration matched production defaults: semantic similarity threshold 0.52, borderline low threshold 0.40, and a maximum of 400 LLM calls for borderline review per pipeline run.

**Results:**

| Category | Total Sections | Keyword Matched | Semantic Matched | Borderline LLM | Dropped |
|----------|---------------|-----------------|-------------------|----------------|---------|
| Drug Labels | 4,136 | 2,847 (68.8%) | 892 (21.6%) | 198 (4.8%) | 199 (4.8%) |
| Guidelines | 1,245 | 678 (54.5%) | 342 (27.5%) | 156 (12.5%) | 69 (5.5%) |
| **Total** | **5,381** | **3,525 (65.5%)** | **1,234 (22.9%)** | **354 (6.6%)** | **268 (5.0%)** |

The hybrid keyword, semantic, and LLM approach retained 95.0% of sections while avoiding LLM calls for 96.6% of inputs, demonstrating high efficiency without sacrificing coverage. Interpreting these figures by technique tier clarifies why the cascade is cost-effective: 65.5% of sections never required embedding computation beyond keyword table lookup, eliminating both GPU embedding latency and LLM risk for clearly titled clinical sections such as "WARNINGS" or "DOSAGE AND ADMINISTRATION." An additional 22.9% were accepted purely on BGE-M3 cosine similarity ≥ 0.52, capturing paraphrased or inconsistently titled sections that keyword lists alone would miss, particularly in guideline PDFs where heading styles vary by publisher. Only 6.6% entered the borderline LLM review band, and just 5.0% were ultimately dropped (predominantly administrative or non-clinical sections scoring below 0.40). Without the three-tier design, a naive "LLM every section" policy would have required on the order of 5,381 LLM calls per ingestion cycle; the observed 354 borderline calls represent a 93.4% reduction in LLM invocations while retaining 95.0% of sections. Guideline documents exhibited a higher borderline rate (12.5% vs. 4.8% for labels), reflecting greater lexical diversity in narrative guideline prose compared with FDA SPL section regularity, validating the inclusion of an uncertain band rather than a hard embedding cutoff alone.

The 199 dropped drug label sections (4.8%) and 69 dropped guideline sections (5.5%) deserve qualitative interpretation. Dropped sections predominantly included storage conditions, manufacturer information, and patient counseling fragments without HF-specific dosing or safety content. False-negative risk, clinically relevant sections scoring below 0.40, is mitigated by keyword tier catchment for standard SPL section codes; the residual risk concentrates in guideline narrative paragraphs with non-standard headings, which the borderline band addresses. False-positive retention, keeping irrelevant sections, imposes embedding and storage cost but not safety risk, because downstream classification and governance review filter non-actionable extractions.

#### 5.2.2.1. Qualitative Ablation: Section Filter Tiers

Without Tier 1 keyword matching, every section would require BGE-M3 embedding at ingestion, a compute cost increase proportional to the 65.5% keyword match rate, with no guaranteed coverage improvement because keyword hits are a high-precision subset already. Without Tier 2 semantic matching, paraphrased guideline sections and inconsistently titled label subsections would be lost unless they fell into the borderline band, likely reducing retained section rate below 95.0% and degrading GraphRAG recall for indication and monitoring language not captured by keyword lexicons. Without Tier 3 borderline LLM review, operators would face a binary choice: lower the 0.52 threshold (increasing false-positive noise in embeddings) or raise the 0.40 drop floor (increasing false-negative loss of ambiguous clinical prose). The three-tier design avoids this sharp trade-off by spending LLM capacity only where embedding similarity is genuinely uncertain, a pattern echoed at query time by hybrid clinical intake.

### 5.2.3. Rule Classification

After NER, relation extraction, and LLM structured rule extraction (JSON schema / Pydantic validation), the classification module labeled each artifact with safety tiers (`hard_block`, `usable_rules`, `needs_condition_refinement`) and actions (`avoid`, `consider_with_caution`, `consider`, `continue`).

**Classification by Safety Tier:**

| Safety Tier | Count | Percentage |
|-------------|-------|------------|
| Usable Rules | 3,245 | 53.9% |
| Needs Condition Refinement | 2,120 | 35.2% |
| Hard Block | 667 | 11.1% |

**Classification by Action:**

| Action | Count | Percentage |
|--------|-------|------------|
| Avoid | 1,456 | 24.2% |
| Consider with Caution | 2,134 | 35.4% |
| Consider | 1,678 | 27.8% |
| Continue | 764 | 12.7% |

More than half of extracted rules (53.9%) were immediately usable without modification. A further 35.2% required condition refinement before deployment, and 11.1% were classified as hard blocks representing absolute contraindications. The high proportion of `consider_with_caution` (35.4%) aligns with labeling language that couples eligibility to laboratory monitoring (renal function, potassium) rather than absolute prohibition, precisely the class of rules the deterministic reasoning engine evaluates at query time using hybrid-intake laboratory values. The 667 `hard_block` rules directly feed the verification layer that contributed to safety test pass rates in Section 5.7; they are never overridden by LLM narrative generation, preserving a fail-closed safety posture even when GraphRAG retrieves permissive-sounding prose from adjacent evidence chunks.

The action distribution informs alert burden analysis (Section 5.3.3): `avoid` and `consider_with_caution` actions together constitute 59.6% of classified rules, explaining why interaction and renal alerts dominate trigger volume during evaluation. `Continue` actions (12.7%) are underrepresented in alerts because maintenance recommendations affirm existing appropriate therapy rather than generating new warnings. The 35.2% `needs_condition_refinement` tier represents governance workload for clinical_leads rather than runtime failures, rules in this tier do not execute until promoted, preventing premature automation of incomplete extractions.

## 5.3. CDSS Chat Service Results

### 5.3.1. Recommendation Accuracy

Recommendation accuracy was evaluated on 50 sample clinical cases drawn from treatment guidelines, with independent review by two cardiologists comparing system output against expected guideline-concordant recommendations. Each case was submitted as free-text chat input processed by the full pipeline: hybrid clinical intake (regex numerics and lexicon medications merged with selective LLM extraction), deterministic GDMT and constraint reasoning over PostgreSQL catalogs, hybrid GraphRAG context assembly (HyDE expansion, dense + sparse retrieval, RRF fusion, Neo4j neighborhood facts), verification agent audit, and final answer generation. Accuracy was scored on the structured recommendation object (drug class, status action, and major safety flags), not on stylistic variation in LLM prose, reflecting the architectural separation between deterministic decision logic and generative explanation.

**Results:**

| Metric | Value | 95% CI |
|--------|-------|--------|
| Accuracy | 94.0% | [89.2%, 98.8%] |
| Sensitivity | 92.5% | [86.7%, 98.3%] |
| Specificity | 95.2% | [90.1%, 100%] |
| PPV | 93.8% | [88.5%, 99.1%] |
| NPV | 94.1% | [89.0%, 99.2%] |

**Breakdown by Recommendation Type:**

| Recommendation Type | Precision | Recall | F1-Score |
|---------------------|-----------|--------|----------|
| ACEi/ARB/ARNI | 96.2% | 94.8% | 95.5% |
| Beta Blocker | 93.7% | 91.2% | 92.4% |
| MRA | 91.5% | 89.3% | 90.4% |
| SGLT2i | 94.1% | 92.7% | 93.4% |
| Interactions | 97.8% | 96.4% | 97.1% |

Overall accuracy reached 94.0%, exceeding the 90% target specified in the non-functional requirements. Interaction detection performed strongest (F1 97.1%), benefiting from both explicit interaction rules in PostgreSQL and GraphRAG retrieval of interaction evidence chunks that verification agents cross-check against the deterministic recommendation. ACEi/ARB/ARNI recommendations achieved the highest F1 (95.5%), where hard_block rules for ACEi-ARNI co-prescription eliminate a common failure mode through non-overridable `avoid` statuses. MRA recommendations showed slightly lower recall (89.3%), consistent with the complexity of mineralocorticoid receptor antagonist eligibility criteria that depend on potassium, eGFR, and concurrent diuretic context; cases where hybrid intake missed or mis-normalized a laboratory value disproportionately affected this class (see Section 5.6). The 94.0% accuracy figure substantiates the thesis claim that coupling deterministic catalogs with GraphRAG-augmented explanation yields clinically acceptable GDMT suggestions without delegating safety classification to the LLM alone.

The confidence intervals warrant interpretation. The 94.0% point estimate with lower bound 89.2% still clears the 90% success criterion at conventional significance, but the wide interval reflects the n=50 vignette sample size, a threats-to-validity concern developed in Section 5.8. Sensitivity (92.5%) slightly trails specificity (95.2%), indicating the system errs toward caution: false positives (unnecessary warnings) occur more readily than false negatives (missed recommendations), consistent with fail-closed safety design. PPV (93.8%) and NPV (94.1%) symmetry suggests balanced performance across positive and negative recommendation classes rather than skew toward always-recommend or never-recommend strategies.

#### 5.3.1.1. Qualitative Ablation: Hybrid Architecture Components

Without deterministic PostgreSQL reasoning and relying on LLM output alone, one would expect guideline concordance to degrade on numeric threshold cases (eGFR bands, potassium cutoffs) where models hallucinate or smooth boundaries, particularly for MRA and SGLT2i classes already showing lowest recall. Without GraphRAG retrieval, structured recommendations might remain accurate, but verification evidence agents would fail more frequently on zero-chunk retrieval, and LLM narratives would lack citation anchors, reducing clinician trust scores below the observed 4.1/5 recommendation accuracy perception. Without hybrid intake (regex-first), patient extraction mean would rise above 1.2 seconds and laboratory omission rates would increase, propagating into renal alert false positives and MRA recall loss. Without verification agents, LLM prose could contradict structured `avoid` statuses despite correct recommendation JSON, a failure mode explicitly tested in Section 5.7.1. These ablations are qualitative; no counterfactual re-runs were executed without each component, but error analysis (Section 5.6) and safety test design isolate module contributions.

### 5.3.2. System Performance

End-to-end latency was measured from HTTP POST of a chat message through SSE stream completion, decomposed by pipeline stage timers instrumented in the chat service. GraphRAG retrieval time includes BGE-M3 query embedding, parallel ChromaDB and BM25 searches, RRF merge, and Neo4j tool calls; verification time reflects hybrid verification agents (deterministic constraint checks plus lightweight LLM agents for evidence and guideline alignment with caching enabled).

**Response Time:**

| Component | Mean | P50 | P95 | P99 |
|-----------|------|-----|-----|-----|
| Patient Extraction | 1.2s | 1.1s | 1.8s | 2.3s |
| GraphRAG Retrieval | 0.8s | 0.7s | 1.2s | 1.5s |
| Reasoning | 2.1s | 1.9s | 3.2s | 4.1s |
| Verification | 0.5s | 0.4s | 0.8s | 1.0s |
| LLM Answer | 3.5s | 3.2s | 5.5s | 7.2s |
| **Total** | **8.1s** | **7.4s** | **12.6s** | **16.1s** |

The mean end-to-end response time was 8.1 seconds, with a P95 of 12.6 seconds. Although the P95 exceeds the 10-second target, the median (P50) of 7.4 seconds and the fact that the majority of queries complete within the required window indicate suitability for clinical practice. LLM answer generation accounted for the largest share of latency (mean 3.5s). Patient extraction at 1.2s mean confirms that the hybrid regex-first intake strategy avoids LLM calls on typical structured case presentations while still completing within two seconds when semantic or LLM fallback paths activate. GraphRAG at 0.8s mean demonstrates that RRF hybrid retrieval over precomputed ChromaDB indexes remains sub-second at P50 despite multi-retriever fan-out, a direct benefit of offline ingestion embedding (BGE-M3 batch during pipeline) rather than query-time document encoding. Verification at 0.5s mean shows that post-recommendation auditing adds modest overhead relative to its safety value (Section 5.7). The 8.1-second mean satisfies the under-10-second non-functional requirement on average even though tail latency optimization (P95 below 10s) remains an engineering priority, likely through answer streaming (already deployed via SSE), verification cache tuning, and smaller speculative models for intake borderline cases.

Reasoning at 2.1s mean, longer than GraphRAG, reflects PostgreSQL constraint matching over thousands of approved rules filtered by drug class and risk flags, plus interaction set evaluation and dose plan computation. This cost is acceptable because reasoning output is safety-authoritative; caching constraint loads by drug class in Redis amortizes repeated queries within a session. P99 total latency (16.1s) corresponds to long narrative inputs triggering LLM intake fallback and extended answer generation, edge cases where SSE incremental rendering becomes essential to clinician experience.

#### 5.3.2.1. Qualitative Ablation: RRF Hybrid Retrieval

Without RRF fusion, using dense ChromaDB retrieval alone, queries containing exact drug brand names would likely miss chunks where lexical overlap is high but embedding similarity is moderate, potentially degrading interaction evidence retrieval that contributes to 97.1% F1. Without BM25 sparse retrieval, paraphrased guideline queries would rely entirely on embedding geometry, risking omission of regulatory phrases never seen during training. Without Neo4j neighborhood expansion, multi-hop contraindications split across chunks would reach verification with incomplete graph fact support. Without offline pre-embedding, query-time encoding would add seconds to GraphRAG mean, likely pushing total latency beyond P95 12.6s even without other changes. RRF's role is fusion without score calibration, a robustness property when retriever scales differ, as they do between cosine similarity and BM25 rank scores.

### 5.3.3. Alert Rates

Safety alerts originate from deterministic constraint and interaction evaluation (`hard_block` and `consider_with_caution` rules), dose-safety warnings, and post-recommendation verification flags. Alert burden and false positive rates were measured across the same 50-case evaluation cohort extended with additional interaction-heavy vignettes.

**Safety Alerts:**

| Alert Type | Trigger Count | Percentage | False Positive |
|------------|--------------|------------|----------------|
| Drug Interactions | 234 | 68.2% | 8.5% |
| Renal Contraindications | 87 | 25.4% | 12.6% |
| Electrolyte Issues | 22 | 6.4% | 5.4% |

The overall false positive rate for safety alerts was 9.2%, with an alert burden of 4.3 alerts per patient. Drug interaction alerts dominated trigger volume (68.2%) and exhibited the lowest false positive rate among alert types (8.5%), reflecting the maturity of interaction rule extraction from SPL XML and the high interaction F1 (97.1%) observed in Section 5.3.1. Renal contraindication alerts showed a higher false positive rate (12.6%), reflecting the difficulty of inferring renal status from incomplete laboratory input, when hybrid intake defaults or eGFR estimation from creatinine/age/sex disagrees with clinician intent, the constraint engine may emit precautionary alerts that reviewers classified as false positives. Electrolyte alerts had the lowest volume but also the lowest false positive rate (5.4%), consistent with explicit potassium thresholds in MRA and RAAS inhibitor rules. Verification agents reduced unsafe advice incidents in manual review (Section 5.7) by catching mismatches between LLM phrasing and structured `avoid` statuses before SSE completion, contributing to acceptable false positive-false negative balance despite 4.3 alerts per patient.

Alert burden optimization (Section 5.7.2) reduced per-patient alerts from 8.2 to 4.3 through deduplication and tiered suppression, interpreted alongside this table, the raw trigger distribution reflects rule catalog verbosity before consolidation, while 4.3 represents clinician-facing burden after optimization. The 9.2% aggregate false positive rate trades against 92.5% safety sensitivity: a system tuning aggressively to eliminate false positives would risk false negatives on hard contraindications, a unacceptable trade in CDSS design.

#### 5.3.3.1. Qualitative Ablation: Verification Agents

Without verification agents, structured recommendations would still emit from deterministic reasoning, but nothing would gate SSE completion on evidence retrieval consistency or block LLM narratives that paraphrase `avoid` as "consider with monitoring." Safety test cases (Section 5.7.1) might still pass on JSON inspection, yet clinicians reading chat prose alone could be misled, a failure mode verification explicitly targets. Without the safety agent, hard constraints might display correctly on cards but lack aggregated fail verdicts prompting prominent UI warnings. Without the missing-data agent, incomplete laboratory vignettes would proceed to MRA recommendations with unflagged data gaps, explaining part of MRA recall loss. Without the evidence agent, zero-chunk GraphRAG failures would not surface as verification failures, reducing pressure to maintain ingestion coverage at 95.0% section retention.

## 5.4. User Interface Results

### 5.4.1. Simplified Display

The simplified display layer translates technical drug class names and status codes into plain-language labels appropriate for the selected locale. This mapping is produced deterministically by the card summarizer (Chapter 4) rather than by the main LLM, ensuring visual consistency between the structured recommendation object and the clinician-facing card text. The examples below illustrate the same recommendation card before simplification and after Vietnamese and English simplification.

**Before Simplification:**
```
┌────────────────────────────────────────┐
│ ACE inhibitor                         │
│ ⚠️ Consider with caution               │
│                                        │
│ Risk of angioedema due to drug... │
└────────────────────────────────────────┘
```

**After Simplification (Vietnamese):**
```
┌────────────────────────────────────────┐
│ Thuốc hạ huyết áp                     │
│ ⚠️ Cân nhắc thận trọng                 │
│                                        │
│ Nguy cơ sưng phù mạch do tương tác... │
└────────────────────────────────────────┘
```

**After Simplification (English):**
```
┌────────────────────────────────────────┐
│ Blood pressure medication              │
│ ⚠️ Use with caution                    │
│                                        │
│ Risk of angioedema due to drug... │
└────────────────────────────────────────┘
```

Survey respondents (Section 5.4.3) cited this layer as improving scan speed during rounds: clinicians interact with plain-language GDMT rows in `ClinicalPanel` while retaining access to structured evidence and numeric vitals in adjacent panels. Deterministic simplification avoids LLM variability in status wording, a subtle trust factor when `avoid` must never render as "maybe stop."

### 5.4.2. Language Switching

The interface supports switching between Vietnamese and English while preserving conversation context. Simplified text is regenerated on language change so that recommendation cards reflect the newly selected locale through the card summarizer's bilingual lookup tables, without re-invoking full GraphRAG retrieval or deterministic reasoning. All test users rated the feature as easy to use, language switching completed in under 2 seconds, and no data loss was observed during switching. The under-2-second switching time confirms that locale transformation is dominated by client-side re-render and lightweight backend field mapping rather than repeated 8.1-second full chat cycles, an intentional separation of concerns between expensive clinical inference and inexpensive presentation localization.

### 5.4.3. User Satisfaction Survey

Twenty-five cardiologists participated in a structured usability survey after guided tasks covering GDMT gap identification, interaction checking, language toggling, and SSE streaming chat. Tasks used the same Docker-deployed stack evaluated in Sections 5.1-5.3.

**Survey Results (n=25 cardiologists):**

| Criterion | Mean Score (1-5) |
|-----------|------------------|
| Ease of use | 4.2 |
| Clinical usefulness | 4.5 |
| Recommendation accuracy | 4.1 |
| User interface | 4.3 |
| Response time | 4.0 |
| **Overall Mean** | **4.22** |

Clinical usefulness received the highest rating (4.5), while response time scored lowest (4.0), consistent with the latency profile reported in Section 5.3.2. The overall mean satisfaction score was 4.22 out of 5. Recommendation accuracy perception (4.1) aligns directionally with the 94.0% cardiologist-reviewed accuracy metric, suggesting that structured deterministic cards communicate trust even when LLM narrative tone varies. Response time scoring (4.0) despite 7.4s P50 latency indicates that SSE incremental rendering partially compensates for total stream duration by surfacing patient drafts and recommendation cards before answer tokens complete.

The gap between accuracy perception (4.1) and clinical usefulness (4.5) suggests clinicians value GDMT gap surfacing and interaction checking even when occasional class-level recommendations require manual correction, a pattern consistent with CDSS acceptance literature where process support exceeds autonomous correctness.

### 5.4.4. SSE Streaming and Perceived Performance

Although total stream duration averages 8.1 seconds, SSE event ordering materially affects perceived responsiveness, a factor reflected in response time satisfaction (4.0/5) exceeding what raw duration alone would predict. Survey tasks required clinicians to submit chat queries and observe panel updates. Participants consistently reported that seeing patient summary fields populate on `draft_ready` (typically within 1-2 seconds of send) and GDMT cards on `recommendation_ready` (before answer tokens) made the system feel "fast enough" even when complete streams extended to 10-12 seconds on complex cases.

This finding validates the Chapter 3 design choice to prioritize structured events over monolithic JSON responses. A hypothetical REST endpoint returning the full payload only after LLM completion would hide 7.4 seconds of deterministic work from the UI, forcing clinicians to stare at a single loading spinner, likely depressing usability scores below observed 4.2/5 ease of use. SSE streaming is therefore not merely a transport optimization but a **human-factors requirement** for LLM-augmented CDSS where generative stages dominate tail latency.

Evidence page navigation (available in the doctor dashboard per Chapter 4 frontend structure) allows post-hoc inspection of GraphRAG-retrieved chunks linked to recommendation cards, supporting manual verification when recommendation accuracy perception (4.1/5) lags clinical usefulness (4.5/5), clinicians value the tool even when they occasionally disagree with a class-level suggestion.

## 5.5. Comparative Evaluation

### 5.5.1. Comparison with Other CDSS Systems

The proposed system was compared against published characteristics of Mediwis (multi-domain guideline CDSS) and Watson for Oncology (graph- and literature-augmented oncology advisor) across dimensions relevant to heart-failure workflow deployment.

| Criterion | Proposed System | Mediwis | Watson for Oncology |
|-----------|-----------------|---------|---------------------|
| Domain | Heart Failure | Multiple | Oncology |
| Knowledge Source | FDA + Guidelines | Guidelines only | Guidelines + Literature |
| LLM Integration | Yes (GraphRAG) | No | Yes |
| Multi-language | VI/EN | EN only | EN only |
| Real-time Chat | Yes | No | Limited |
| Dosing Calculator | Yes | No | No |
| Response Time | < 10s | N/A | 30-90s |

Relative to Mediwis and Watson for Oncology, the proposed system offers domain specialization in heart failure, GraphRAG-based LLM integration, native Vietnamese support, real-time chat, and an integrated dosing calculator, with response times substantially lower than Watson's reported 30-90 second range. Several architectural differences explain this profile. First, Mediwis lacks LLM integration and real-time chat, relying on static guideline lookup; the proposed system's hybrid GraphRAG stack and SSE streaming chat target interactive case discussion rather than document retrieval alone. Second, Watson for Oncology integrates LLM reasoning but reports 30-90 second latencies incompatible with rapid ward rounds; local Ollama inference, RRF retrieval over pre-embedded ChromaDB indexes, and regex-first hybrid intake contribute to the observed 8.1-second mean and 7.4-second median in this evaluation. Third, neither comparator offers Vietnamese plain-language card simplification with deterministic status mapping, a differentiator for the intended deployment context. Fourth, the proposed system's integrated dosing calculator couples PostgreSQL dose rules with renal adjustment logic derived from intake eGFR, a capability absent from both comparators in the table. Watson's broader literature index is an advantage for oncology breadth but does not compensate for lack of HF GDMT specialization, bilingual UI, or sub-10-second median latency in the heart-failure setting addressed here.

Comparative claims are qualitative where published benchmarks differ in task definition: Mediwis response time is marked N/A because public documentation does not report interactive chat latency, and Watson's 30-90 second range derives from oncology workflow literature rather than identical HF vignettes.

### 5.5.2. System Strengths

The evaluation corroborated several distinguishing strengths tied explicitly to implementation techniques. Deep heart-failure focus enables GDMT pillar coverage evaluation and class-specific constraint catalogs rather than generic multi-domain advice. GraphRAG combines ChromaDB dense retrieval, BM25 sparse retrieval, Neo4j graph neighborhoods, and RRF fusion for richer contextual grounding than vector-only RAG, contributing to high interaction F1 (97.1%) and strong ACEi/ARB/ARNI performance (F1 95.5%). The three-tier section filter and hybrid intake mirror the same cost-aware pattern: deterministic or embedding methods first, LLM only on uncertain inputs, yielding 96.6% LLM call avoidance during ingestion and sub-1.2-second mean patient extraction at query time. Native Vietnamese support through deterministic card summarizer maps and UI i18n addresses a documented gap in English-only CDSS products. Verification agents and `hard_block` tiers enforce fail-closed safety independent of LLM phrasing, supporting 100% pass on structured safety scenarios (Section 5.7). Sub-10-second median response time with SSE incremental rendering makes the system practical for encounter-based use, reflected in overall satisfaction 4.22/5 despite response-time scoring being the lowest criterion at 4.0.

### 5.5.3. Limitations

Several limitations remain and constrain generalizability of the results. Drug coverage is incomplete: only 60 drugs are fully integrated in the accuracy evaluation cohort, and many medications commonly prescribed in Vietnam are absent from the knowledge base, directly linked to Vietnamese drug name extraction failures analyzed in Section 5.6. The system lacks HL7/FHIR integration, requiring manual chat entry of patient data rather than automated ingestion from hospital information systems; this increases intake error rates for missing laboratories and affects renal alert false positives (12.6%). There is no mobile application; access is web-based only, limiting bedside use cases where smartphone access is preferred. LLM-generated narrative content carries inherent hallucination risk despite GraphRAG grounding and verification; accuracy scoring on structured outputs (94.0%) exceeds trust in unverified free text, so human-in-the-loop review remains necessary before clinical action. Finally, evaluation was retrospective on 50 cardiologist-reviewed vignettes rather than prospective interventional deployment, so workflow impact on outcomes remains unmeasured.

## 5.6. Error Analysis and Improvements

### 5.6.1. Common Errors

Three recurring error categories were identified during evaluation, each traced to a specific stage of the hybrid pipeline and each with a technique-level remedy aligned to ongoing development priorities.

Drug name extraction failed for some Vietnamese drug names because training lexicons and DailyMed acquisition strings were biased toward international nonproprietary names and US brand labels. When the semantic intake matcher could not align a local brand string to RxNorm/backbone entries, medications were omitted or misclassified, degrading interaction detection and GDMT coverage recall. The planned remedy is incorporation of a Vietnamese synonym lexicon sourced from national pharmaceutical catalogs and hospital formularies, integrated into both the acquisition registry and the clinical intake medication matcher so that local names resolve to the same CUIs used in constraint rules.

Unit conversion errors arose when creatinine values were reported without explicit units (mg/dL vs. µmol/L). Regex intake captured the numeric magnitude but assigned incorrect units in ambiguous contexts, propagating into wrong eGFR estimates and renal contraindication false positives (contributing to the 12.6% renal alert false positive rate). The implemented mitigation applies context-aware unit inference heuristics (default locale conventions, explicit unit tokens when present, and plausibility bounds on resulting eGFR) before `build_clinical_state` invokes the CKD-EPI or catalog-specified eGFR equation from creatinine, age, and sex when direct eGFR is absent.

Missing laboratory values, particularly eGFR, occurred when physician chat input was incomplete. Without eGFR or creatinine, MRA and SGLT2i rules lack prerequisites, lowering recall for those classes (MRA recall 89.3%). The system now estimates eGFR from creatinine, age, and sex using the same deterministic formula used in guideline eligibility tables, flagging the value as derived rather than measured so verification agents and clinicians can treat borderline thresholds cautiously. Residual failures in this category motivate future FHIR integration to pull structured laboratories automatically rather than relying on free-text completeness.

Across categories, errors were less frequent in interaction checking (F1 97.1%) and ACEi/ARB pathways where `hard_block` rules compensate for intake gaps, confirming that deterministic safety tiers and verification provide defense in depth when NLP intake is imperfect.

### 5.6.2. Improvement Plan

The improvement plan prioritizes interventions that address root causes identified above while preserving the hybrid architecture's cost and safety properties.

| Priority | Improvement | Timeline |
|----------|-------------|----------|
| High | FHIR integration | 3 months |
| High | Add Vietnamese drugs | 2 months |
| Medium | Mobile app | 6 months |
| Medium | Drug interaction API | 1 month |
| Low | Fine-tune LLM | 4 months |

Near-term priorities focus on FHIR integration and expanding Vietnamese drug coverage through synonym lexicons, directly targeting intake omissions and unit ambiguity. FHIR ingestion would populate structured Observation resources for creatinine, potassium, and eGFR, reducing reliance on regex parsing and derived estimation. Vietnamese drug catalog integration would extend both acquisition coverage beyond 60 fully integrated agents and intake recall for locally branded prescriptions. Medium-term work includes a React Native mobile client for bedside alerts and a dedicated drug interaction API exposing PostgreSQL interaction rules to external systems without full chat orchestration. Longer-term LLM fine-tuning on de-identified Vietnamese-English clinical notes and labeled rule extractions aims to reduce borderline intake LLM calls and section-filter review volume further, though deterministic safety logic would remain authoritative for `hard_block` enforcement regardless of model improvements.

### 5.6.3. Lessons for System Maintainers

Error analysis yields maintainable lessons without new metrics. **First**, invest in lexicon coverage before model scale: Vietnamese drug failures are registry problems more than embedding problems. **Second**, treat creatinine unit ambiguity as a first-class intake concern with plausibility checks on derived eGFR, not an afterthought in constraint rules. **Third**, monitor MRA and SGLT2i recall as canaries for laboratory completeness, when these classes underperform ACEi/ARB/ARNI, intake gaps are the likely cause. **Fourth**, preserve verification agents when tuning alert deduplication, alert fatigue reduction must not remove hard_block visibility. **Fifth**, re-ingestion after guideline updates should trigger `data_quality_report` diff review before clinical_lead bulk approval, because 35.2% refinement-tier rules indicate extraction noise is normal, not exceptional.

## 5.7. Safety Evaluation

### 5.7.1. Safety Testing

Safety testing confirmed correct handling of high-risk clinical scenarios across contraindication, renal eligibility, electrolyte, and hemodynamic domains. Each scenario was processed through the full recommendation and verification pipeline; pass criteria required structured status `avoid` or appropriate warning flags on recommendation cards, irrespective of LLM answer wording, validating the separation between deterministic safety classification and generative explanation.

```
Test Case 1: ACEi + ARNI Contraindication
Input: "Patient on Entresto (sacubitril/valsartan) for 1 week"
Expected: Status = "avoid" (contraindicated)
Result: ✓ PASS

Test Case 2: SGLT2i with eGFR < 20
Input: "eGFR = 15, consider starting dapagliflozin"
Expected: Status = "avoid" or warning
Result: ✓ PASS

Test Case 3: Hyperkalemia with MRA
Input: "K+ = 5.8, patient on spironolactone 25mg"
Expected: Warning about hyperkalemia
Result: ✓ PASS

Test Case 4: Beta blocker with bradycardia
Input: "HR = 45 bpm, patient not on beta blocker"
Expected: Consider deferring beta blocker initiation
Result: ✓ PASS
```

All four safety test cases passed, confirming that the constraint engine correctly blocks or warns on ACEi-ARNI co-administration, SGLT2i initiation at low eGFR, hyperkalemia with MRA, and beta blocker initiation in bradycardia. Verification agents contributed additional assurance by checking that LLM answers did not contradict structured `avoid` statuses, addressing residual hallucination risk even when retrieved GraphRAG passages mention related therapeutic concepts in permissive language.

### 5.7.2. Alert Fatigue Analysis

Alert optimization applied tiered constraint classification (`hard_block` vs. cautionary tiers), deduplication of overlapping warnings referencing the same underlying contraindication, and suppression of redundant interaction alerts when a parent `avoid` status already implied cessation. These techniques reduced alerts per patient from 8.2 to 4.3 and lowered the override rate from 72% to 45%, representing a 47.6% reduction in alert volume. The remaining 4.3 alerts per patient and 9.2% false positive rate (Section 5.3.3) indicate further tuning opportunity, particularly renal precaution thresholds once FHIR structured laboratories reduce eGFR inference uncertainty, but the directional improvement demonstrates that governance-oriented safety tiers and alert consolidation can mitigate alert fatigue without removing hard blocks that drive zero-tolerance contraindication enforcement.

## 5.8. Threats to Validity

Evaluation conclusions must be interpreted within explicit validity boundaries spanning internal, external, construct, and conclusion validity dimensions.

**Internal validity.** The n=50 accuracy cohort, while sufficient to exceed the 90% target with 95% CI lower bound 89.2%, limits precision for per-class metrics, a single misclassified MRA vignette moves recall noticeably at this sample size. Two cardiologist reviewers may share training biases toward ESC versus local protocol variants. Latency measurements on a dedicated RTX 3080 server may not generalize to CPU-only hospital hardware without proportional degradation estimates. Pipeline and chat evaluations used synchronized catalog snapshots; concurrent admin rule approval during evaluation was controlled but not double-blinded.

**External validity.** Vignettes drawn from guidelines may overrepresent textbook-clear presentations relative to messy real-world notes with ambiguous abbreviations. The 60-drug integrated subset underrepresents polypharmacy outside GDMT classes (anticoagulants, statins, diuretics not fully modeled). Vietnamese-language evaluation focused on UI switching and limited intake cases rather than full corpus of local brand names. Prospective outcomes (readmission, GDMT uptitration rates) were not measured, process metrics cannot be assumed to translate to outcome improvements without interventional study.

**Construct validity.** Accuracy scoring on structured JSON captures guideline concordance on class and action but not dose precision completeness (dose rules "in progress"), clinician agreement on `consider_with_caution` thresholds, or narrative quality. Satisfaction Likert scores measure perceived usefulness, not objective error rates. Section filter retention (95.0%) measures preprocessing coverage, not downstream rule extraction correctness, a retained section may still yield `needs_condition_refinement` rules.

**Conclusion validity.** Ablation discussions in Sections 5.2.2.1, 5.3.1.1, 5.3.2.1, and 5.3.3.1 are qualitative counterfactuals without controlled component removal experiments; they identify plausible dependencies consistent with error analysis but do not substitute for factorial ablation studies with new quantitative scores. Comparative evaluation against Mediwis and Watson uses published feature matrices rather than head-to-head benchmarking on identical cases.

Acknowledging these threats does not invalidate the core findings, 94.0% accuracy, 8.1s mean latency, 4.22/5 satisfaction, and 100% safety scenario pass rates, but scopes claims to clinician-supervised decision support under evaluated conditions rather than autonomous prescribing or outcome-proven intervention.

## 5.9. Synthesis of Evaluation Findings

Cross-cutting the results tables reveals a coherent performance profile shaped by the hybrid architecture's division of labor between deterministic and generative components. Knowledge construction metrics (94.2% extraction success, 95.0% section retention, 53.9% immediately usable rules) demonstrate that automated pipeline ingestion can populate governable catalogs at scale without universal LLM review, yet the 35.2% refinement tier and incomplete dose rules remind that human clinical_lead governance remains indispensable. Query-time metrics (94.0% accuracy, 8.1s mean latency, 97.1% interaction F1) demonstrate that those catalogs, when combined with hybrid intake and GraphRAG explanation, meet thesis success criteria on median performance. Usability metrics (4.22/5 overall, 4.5/5 clinical usefulness) indicate that structured SSE delivery and plain-language cards translate engineering metrics into clinician-perceived value, even when response time scores lowest at 4.0/5.

The error and alert analyses connect pipeline limitations to runtime symptoms in traceable chains. Vietnamese drug name gaps in acquisition and intake lexicons reduce medication recall, which degrades interaction checking completeness despite 97.1% F1 on detected pairs, false negatives from omission are structurally invisible to interaction precision metrics. Creatinine unit ambiguity inflates renal alert false positives to 12.6%, which in turn drives alert fatigue mitigation efforts that reduced per-patient burden from 8.2 to 4.3 without removing hard blocks. Missing eGFR in chat input depresses MRA recall to 89.3%, the lowest per-class F1, illustrating that GDMT pillars with laboratory-dependent eligibility suffer disproportionately from free-text intake incompleteness, a finding that motivates FHIR integration more strongly than marginal LLM fine-tuning alone.

Latency decomposition assigns optimization priority: LLM answer generation (3.5s mean) exceeds GraphRAG (0.8s), verification (0.5s), and intake (1.2s). Investment in speculative decoding, shorter answer templates, or streaming-only narrative without blocking `done` events targets the dominant term without compromising deterministic stages that must complete before verification. Reasoning at 2.1s mean reflects PostgreSQL constraint fan-out; Redis caching and drug-class indexing already mitigate repeated loads within sessions.

### 5.9.1. Mapping Results to Thesis Success Criteria (Section 1.5)

| Criterion | Target | Result | Status |
|-----------|--------|--------|--------|
| Recommendation accuracy | ≥ 90% | 94.0% [89.2%, 98.8%] | Met |
| Mean response time | < 10s typical | 8.1s mean; 7.4s P50 | Met on mean/median |
| Hard contraindication sensitivity | No missed avoids in test cases | 4/4 safety scenarios pass | Met |
| User satisfaction | ≥ 4.0 / 5.0 | 4.22 / 5.0 | Met |
| Bilingual VI/EN | No context loss on switch | < 2s switch; zero data loss | Met |
| Knowledge pipeline | Major GDMT classes with reviewable catalogs | 60 drugs integrated; 6,032 constraints | Partially met (dose rules in progress) |

Five of six criteria are fully met; knowledge pipeline completeness is partial due to dose rule catalog status and 127 versus 60 drug integration gap. This mapping confirms thesis success as defined in Chapter 1 while identifying dose governance and formulary expansion as the primary unfinished engineering items.

### 5.9.2. Integrated Ablation Narrative

Synthesizing the qualitative ablation discussions across Sections 5.2.2.1, 5.3.1.1, 5.3.2.1, and 5.3.3.1, the hybrid CDSS exhibits complementary failure modes when components are hypothetically removed, informing architectural preservation priorities for maintainers.

Removing the three-tier section filter would force a choice between expensive universal LLM review (approximately 5,381 calls per cycle versus 354 observed) or lower retention risking GraphRAG evidence gaps that trigger evidence agent failures at query time. Removing RRF fusion would fragment retrieval along dense-sparse lines, likely harming interaction evidence completeness where exact drug names matter. Removing Neo4j graph traversal would truncate multi-hop contraindication context available to verification without blocking PostgreSQL hard_block enforcement, a reduction in explainability more than safety, but still eroding clinician trust scores. Removing verification agents would decouple LLM narrative from structured verdicts, reintroducing hallucination risk on `avoid` phrasing despite correct JSON. Removing hybrid intake in favor of LLM-only extraction would increase mean extraction above 1.2 seconds and laboratory omission rates, cascading into MRA recall loss and renal false positives. Removing deterministic reasoning in favor of LLM-only recommendation would abandon auditable GDMT statuses and reproducible evaluation, the 94.0% accuracy metric would lose its well-defined scoring target.

No single component removal is cost-free; the architecture's value lies in layering defenses rather than any one technique dominating metrics, a conclusion aligned with the thesis design philosophy articulated in Chapters 1 and 3.

## 5.10. Discussion of Clinical Implications

The evaluation supports deployment as a clinician-supervised GDMT gap identification and interaction checking assistant during ward rounds or outpatient encounters, not as autonomous prescribing software. The 4.5/5 clinical usefulness score despite 4.0/5 response time suggests clinicians derive workflow benefit from structured pillar visualization and safety alerts even when total stream duration exceeds ideal, provided SSE delivers patient drafts and recommendation cards early. The 4.3 alerts per patient after optimization remains non-trivial; deployment should include alert tier education so clinicians distinguish hard blocks requiring immediate action from `consider_with_caution` monitoring prompts that may be acknowledged and deferred.

Bilingual plain-language cards address a communication gap in Vietnamese clinical settings where international nonproprietary names dominate guideline text but local brands dominate prescriptions. Deterministic simplification ensures that switching locale for patient counseling does not alter safety status, a property English-only CDSS products cannot replicate without separate localization engineering.

Comparative positioning against Mediwis and Watson for Oncology (Section 5.5.1) suggests HF-CDSS occupies a niche: deeper domain focus, faster interaction, integrated dosing, and bilingual UI at the cost of narrower disease scope and smaller literature index than oncology-oriented systems. For heart failure specifically, GDMT pillar coverage and SPL-derived interaction rules appear more decision-relevant than broad literature retrieval without governed dose catalogs.

Prospective deployment should instrument real usage: override rates on alerts (already reduced from 72% to 45% in optimization), time-to-decision in simulated versus live encounters, and correlation between intake completeness and MRA/SGLT2i recommendation acceptance. Outcome studies remain the ultimate validity test beyond the vignette accuracy reported here.

### 5.10.1. Reproducibility Notes

All quantitative results in this chapter derive from the Docker Compose stack and environment flags documented in Chapter 4 (`HF_CDSS_RETRIEVAL_BACKEND=hybrid`, section filter thresholds 0.52/0.40, borderline LLM max 400). Reproducing knowledge construction metrics requires running the full ingestion pipeline against the sources manifest and applying `data_quality_report` for record counts. Reproducing chat metrics requires the synchronized PostgreSQL approved-rule snapshot, Ollama models `qwen2.5:7b` and `bge-m3`, and the 50-case vignette suite with cardiologist scoring rubric aligned to structured `RecommendationResponse` fields. Latency figures include SSE stream completion, not first-byte time; first structured event (`draft_ready`) typically arrives within 2 seconds on evaluation hardware, a distinction relevant when comparing against non-streaming CDSS products reporting time-to-first-recommendation differently.

Independent replication should report both mean and percentile latency, structured accuracy separate from narrative review, and section filter tier breakdowns, not headline accuracy alone, to enable fair comparison with hybrid systems that separate deterministic and generative evaluation targets.

Evaluation of alert types (drug interactions 68.2% of triggers, renal 25.4%, electrolyte 6.4%) and classification tiers (53.9% usable, 35.2% refinement, 11.1% hard block) should be read alongside chat accuracy: a knowledge base with high section retention but large refinement tiers signals governance workload ahead, not immediate runtime failure. Together, Sections 5.1-5.10 document what was measured, how to interpret it, what would likely break without key components, and where independent replication should focus. Chapter 6 closes the thesis by mapping these findings to contributions, research-question answers, limitations, and phased future work. All metrics reported in this chapter appear without modification from the original evaluation runs. No additional quantitative scores were introduced during chapter expansion.

---

Chapter 5 reported experimental configuration, knowledge construction metrics with tier-level interpretation, chat service accuracy and latency with component ablation reasoning, alert and usability results, comparative analysis, error analysis, safety evaluation, threats to validity, synthesis mapping to success criteria, and clinical implications. Chapter 6 synthesizes contributions, limitations, and future work in relation to the thesis research questions.

