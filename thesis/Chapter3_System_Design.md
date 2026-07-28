# CHAPTER 3: SYSTEM DESIGN

## 3.1. System Requirements

### 3.1.1. Functional Requirements

Based on the problem analysis and research objectives articulated in Chapter 1, the heart failure Clinical Decision Support System (CDSS) must satisfy a set of functional requirements that collectively address the four GDMT pillars, the cognitive burden of interaction checking, individualized dosing, and bilingual clinical communication. Each requirement maps to one or more modules described in Section 3.3; the narrative below states intent and design rationale, while identifiers (FR-1 through FR-6) support traceability to test cases in Chapters 4 and 5. The requirements were derived from ESC and AHA/ACC/HFSA guideline structures, FDA Structured Product Label (SPL) section semantics, and observed failure modes of purely generative LLM chatbots in clinical settings—namely hallucinated doses, omitted contraindications, and inability to audit recommendation provenance.

**FR-1: Patient Profile Analysis.** The system shall recognize and analyze patient information from chat messages, extract key clinical parameters such as ejection fraction (EF), estimated glomerular filtration rate (eGFR), potassium, and blood pressure, and build a structured patient profile suitable for downstream reasoning. Extraction combines deterministic pattern matching for numeric labs and vitals, lexicon-based medication and condition detection, negation handling, unit normalization, and selective LLM semantic parsing when regex confidence is insufficient; measured values from regex extraction take precedence over LLM inference during merge.

The rationale for FR-1 rests on the observation that heart-failure decision support cannot operate on unstructured prose alone. GDMT eligibility, renal dose adjustment, and electrolyte safety all depend on typed numeric fields with known units. A physician may write "65-year-old male, EF 30%, eGFR 45, K+ 4.2, on bisoprolol 5mg" in a single sentence mixing demographics, phenotyping, laboratories, and medications. The hybrid intake architecture described in Section 3.3.1 was chosen because regex extraction achieves sub-second latency on such structured vignettes (mean 1.2 seconds in evaluation, Section 5.3.2), while LLM fallback handles narrative cases with negation ("denies ACEi allergy") or implicit values ("creatinine 1.4" without explicit eGFR). The merge policy `_prefer_measured` encodes a clinical epistemology: instrument-reported values outrank model inference. Without this requirement, downstream constraint rules would evaluate against hallucinated laboratories, inflating false positives for renal contraindications (observed at 12.6% in Section 5.3.3) and depressing MRA recall when potassium is omitted.

**FR-2: GDMT Treatment Recommendations.** The system shall assess the patient's current Guideline-Directed Medical Therapy (GDMT) implementation level, propose medication additions or changes based on treatment guidelines, and explain recommendation rationale with supporting evidence. A policy engine evaluates class coverage (ACEi/ARB/ARNI, beta blocker, MRA, SGLT2i), identifies gaps, matches PostgreSQL-backed constraint rules, and attaches evidence references retrieved via GraphRAG.

FR-2 addresses the central clinical problem: fewer than 2% of eligible HFrEF patients receive all four GDMT classes at target doses in real-world practice. The reasoning service (Section 3.3.3) implements this requirement deterministically—no LLM inside the critical path—because guideline concordance must be auditable and reproducible. GraphRAG supplies explanatory evidence and citation anchors for the LLM narrative layer but does not override class-level `avoid`, `consider`, or `continue` statuses. The four-pillar decomposition mirrors ESC 2021/2022 and AHA/ACC/HFSA guideline organization, enabling per-class precision metrics (ACEi/ARB/ARNI F1 95.5%, MRA F1 90.4%, Section 5.3.1) and targeted error analysis when a single pillar underperforms.

**FR-3: Drug Interaction Checking.** The system shall detect dangerous drug interactions, warn about absolute contraindications, and suggest alternatives or dose adjustments when clinically appropriate. Interaction rules stored in PostgreSQL express drug-set pairs with severity and management text; the interaction checking service evaluates the patient's normalized medication list against approved interaction rules and merges results with constraint-engine outputs.

Interaction checking is cognitively demanding even for specialists: ACEi co-administration with ARNI within the mandated washout window, triple RAAS blockade, and potentiating hyperkalemia combinations require cross-referencing multiple drug classes and timing context. FR-3 mandates that interaction detection remain rule-driven rather than LLM-inferred, contributing to the highest F1 score in evaluation (97.1%, Section 5.3.1). Drug-set normalization maps free-text medication names to substance keys via the intake lexicon, ensuring that "Entresto" and "sacubitril/valsartan" resolve to the same ARNI identifier for interaction evaluation.

**FR-4: Medication Dose Calculation.** The system shall calculate starting and target doses based on patient characteristics, adjust doses according to renal function, and track dose titration progress over time. Dose plans are derived from JSONB-encoded dose rules (starting dose, target dose, renal adjustment predicates, titration schedules) loaded from the governance catalog and FDA label-derived tables.

Dosing individualization is a distinct competency from binary contraindication checking. Beta blockers such as bisoprolol require week-by-week titration schedules conditional on heart rate and blood pressure tolerance; SGLT2 inhibitors and MRAs require renal band adjustments. FR-4 separates dose computation into a dedicated module (Section 3.3.4) whose JSONB rule schema avoids schema migrations for each new titration pattern—a governance trade-off favoring clinical agility over rigid relational normalization.

**FR-5: Safety Alerts.** The system shall generate alerts based on renal function (eGFR), serum potassium levels, and heart rate and blood pressure, ensuring that safety-critical conditions are surfaced before recommendations are finalized. Hard constraints block or flag avoidance actions; soft constraints emit warnings with monitoring instructions. Risk flags (renal impairment, hyperkalemia, hypotension, bradycardia, missing critical labs) feed both alerting and constraint matching.

FR-5 implements a fail-closed posture for life-threatening conditions while tolerating cautionary alerts that require clinician judgment. The distinction between hard constraints (`avoid`, non-overridable) and soft constraints (`consider_with_caution`, monitoring plans) directly supports alert fatigue mitigation: evaluation reduced alerts per patient from 8.2 to 4.3 through tiered classification and deduplication (Section 5.7.2), without removing zero-tolerance contraindication enforcement. Safety alerts must precede LLM narrative generation in the SSE event ordering (Section 3.5.1), implementing Osheroff's Five Rights principle that critical information arrives through the right channel at the right time.

**FR-6: Multilingual Interface.** The system shall support Vietnamese and English, allowing users to switch languages without losing conversation context. Intake normalization handles Vietnamese diacritics and bilingual lexicon terms; plain-language recommendation summaries are generated in the requested locale.

Vietnamese deployment context motivates FR-6: many CDSS products evaluated in Section 5.5.1 are English-only, yet local brand names and clinician–patient communication occur in Vietnamese. Bilingual support splits into intake normalization (Unicode NFKD diacritic stripping, Vietnamese medication aliases) and presentation localization (deterministic card summarizer maps, Section 3.3.6). Language switching completes in under 2 seconds with zero data loss (Section 5.4.2) because locale transformation re-renders simplified fields without re-invoking GraphRAG or reasoning—a deliberate separation of expensive inference from inexpensive presentation.

#### 3.1.1.1. Requirements Traceability Matrix

| Requirement | Primary Module(s) | Evaluation Metric (Ch. 5) |
|-------------|-------------------|---------------------------|
| FR-1 | Patient Profile Extraction (3.3.1) | Patient extraction latency (1.2s mean); intake error analysis (5.6) |
| FR-2 | Reasoning Service (3.3.3), GraphRAG (3.3.2) | Recommendation accuracy 94.0%; per-class F1 |
| FR-3 | Reasoning Service, Interaction Rules DB | Interaction F1 97.1% |
| FR-4 | Dose Calculation (3.3.4) | Dose safety test cases (5.7.1) |
| FR-5 | Safety Constraint Engine (3.3.5), Verification (3.3.6) | Safety sensitivity 92.5%; alert burden 4.3/patient |
| FR-6 | Card Summarizer, LanguageProvider (Ch. 4) | Language switch <2s; satisfaction 4.22/5 |

### 3.1.2. Non-Functional Requirements

**NFR-1: Performance.** Recommendation response time shall remain below 10 seconds for 95% of queries under reference deployment hardware, and the system shall support at least 50 concurrent users. GraphRAG retrieval, rule-engine evaluation, and verification agents run with bounded top-\(k\) pools; Redis caching reduces repeated constraint loads; SSE streaming begins emitting partial results before final LLM tokens complete.

Performance requirements reflect clinical workflow constraints: ward rounds and outpatient encounters tolerate brief pauses but not minute-long waits characteristic of some oncology CDSS products (30–90 seconds for Watson for Oncology, Section 5.5.1). The 10-second P95 target acknowledges that LLM answer generation dominates latency (mean 3.5 seconds, Section 5.3.2); SSE streaming mitigates perceived delay by surfacing `draft_ready` and `recommendation_ready` events before answer tokens complete. Bounded top-\(k\) retrieval pools and Redis constraint caching prevent GraphRAG fan-out from scaling linearly with catalog size (6,032 constraint rules, Section 5.1.2).

**NFR-2: Accuracy.** Treatment recommendation accuracy shall be at least 90% per ESC guidelines as measured by structured evaluation suites, and the system shall not miss alerts for dangerous interactions encoded in approved rules. Accuracy is assessed offline against labeled cases; runtime behavior prioritizes sensitivity on hard constraints over aggressive automation.

The 90% accuracy floor aligns with the thesis success criteria (Section 1.5). Evaluation achieved 94.0% with 95% CI [89.2%, 98.8%] on structured recommendation objects, not LLM prose—a distinction critical to NFR-2 interpretation. Hard-constraint sensitivity prioritization means the system may emit precautionary renal alerts (12.6% false positive rate) rather than silently approve MRA initiation when eGFR is uncertain; this trade-off favors patient safety over alert minimalism.

**NFR-3: Security.** Patient data shall be encrypted in transit and at rest, and the system shall comply with applicable healthcare security regulations. JWT authentication, RBAC authorization, TLS 1.3 termination, and audit logging of chat and recommendation events satisfy this requirement.

Healthcare CDSS systems process sensitive clinical narratives that may identify patients even when formal identifiers are omitted. NFR-3 mandates defense in depth: transport encryption, role-gated admin workflows for rule approval, and audit trails for governance review. Section 3.7.4 extends this requirement with a brief threat model.

**NFR-4: Scalability.** The architecture shall be modular and extensible to other disease domains, with straightforward mechanisms for updating the knowledge base as guidelines evolve. JSONL artifacts, PostgreSQL governance tables, Chroma collections, and Neo4j imports version independently; admin APIs support approve/retire workflows without code deployment.

Modularity supports the `--from-step kg_base` pipeline re-sync entry point (Chapter 4): operators can refresh embeddings and graph indexes without re-downloading DailyMed labels when only governance catalogs change. JSONB dose rules and constraint metadata accommodate new titration patterns without Alembic migrations—a scalability choice favoring clinical content velocity over relational purity.

#### 3.1.2.1. Non-Functional Requirements Rationale Summary

The non-functional requirements collectively encode a design philosophy: deterministic safety and GDMT logic remain authoritative; LLM components operate in cost-aware, auditable roles; and the system must be governable by clinical leads without redeploying application code. Performance and accuracy targets were chosen to be achievable on modest hospital hardware (RTX 3080, 32 GB RAM, Section 5.1.1) rather than cloud-only GPU clusters, supporting on-premise deployment in resource-constrained settings.

## 3.2. Overall Architecture

### 3.2.1. Three-Tier Architecture

The system is designed using a three-tier architecture separating presentation, application logic, and persistence. The presentation tier renders clinician and administrator interfaces; the application tier orchestrates intake, reasoning, retrieval, verification, and streaming generation; the data tier stores rules, embeddings, graph relationships, and conversation state.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │  Doctor Dashboard │  │  Admin Portal   │  │  API Explorer      │  │
│  │  (React + Vite)  │  │  (React)        │  │  (Development)     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    FastAPI Backend                             │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │   │
│  │  │ Chat Service │ │ Reasoning   │ │ Knowledge Graph Engine │ │   │
│  │  │ (Streaming) │ │ Service    │ │ (GraphRAG)              │ │   │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘ │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │   │
│  │  │ Verification │ │ Dose Calc  │ │ Constraint Engine       │ │   │
│  │  │ Service     │ │ Service    │ │ (Safety Rules)          │ │   │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ PostgreSQL  │ │   Redis     │ │  ChromaDB   │ │ File Storage│   │
│  │ (Rules DB) │ │  (Cache)    │ │ (Embeddings)│ │  (JSONL)   │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

The presentation layer hosts the doctor dashboard, admin portal, and API explorer. React clients subscribe to SSE streams from the chat service, updating the clinical panel when structured events arrive. The application layer encapsulates chat streaming, deterministic reasoning, GraphRAG retrieval, multi-agent verification, dose calculation, and safety constraint enforcement; FastAPI's async endpoints allow GraphRAG prefetch concurrently with synchronous rule-engine evaluation on a thread pool, preventing admin requests from starving during long chat turns. The data layer persists governance rules in PostgreSQL, caches session and draft state in Redis, stores BGE-M3 embeddings in ChromaDB, maintains versioned JSONL artifacts on disk, and optionally syncs from object storage; Neo4j (when enabled in deployment) holds imported entity–relationship graphs for neighborhood retrieval.

The three-tier separation was chosen over microservices decomposition because deployment simplicity (single backend container, Section 4.5) outweighs independent scaling benefits at the evaluation scale (50 concurrent users, NFR-1). Module boundaries within the monolith (`app/modules/`) preserve testability and future extraction if GraphRAG or ingestion workloads require dedicated services. The data tier deliberately multiplexes storage technologies—relational for governance, vector for semantic retrieval, graph for multi-hop facts, object storage for reproducible pipeline artifacts—because no single datastore satisfies all access patterns efficiently.

### 3.2.2. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERACTION FLOW                             │
└─────────────────────────────────────────────────────────────────────────────┘

User Message
     │
     ▼
┌─────────────────┐
│ Patient Profile │  1. Extract from message
│    Builder      │  2. Parse clinical state
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ GraphRAG Engine │  3. Build context from Knowledge Graph
│   (Retrieval)   │  4. Find relevant constraints/drugs
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Reasoning     │  5. Apply GDMT guidelines
│    Service      │  6. Evaluate patient conditions
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Verification    │  7. Cross-reference evidence
│    Agent        │  8. Validate recommendations
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Dose Safety     │  9. Check drug interactions
│   Checker       │  10. Validate dosing
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Recommendation │  11. Generate response
│    Generator     │  12. Add plain language summaries
└────────┬────────┘
         │
         ▼
   Chat Response
   (Streaming)
```

When a physician submits a message, the patient profile builder runs hybrid intake (regex numeric extraction, lexicon NER for drugs and conditions, negation detection, unit normalization, selective LLM merge) and emits a `draft_ready` SSE event. A missing-field checker may short-circuit the pipeline with clarification prompts. Otherwise GraphRAG prefetch starts asynchronously while the reasoning service evaluates GDMT policies, constraint rules, dose safety, and interactions synchronously. Verification agents consume the recommendation plus prefetched GraphRAG context, producing structured verdicts streamed as `verification_ready`. The LLM answer generator streams token deltas (`answer_delta`) grounded in recommendation and verification payloads, ending with `done`. This ordering ensures clinicians see structured safety outcomes before narrative prose completes.

The data flow diagram emphasizes a fork-join pattern: GraphRAG retrieval and deterministic reasoning proceed in parallel after intake completes, converging at verification. This parallelism contributes to the sub-second GraphRAG mean (0.8s, Section 5.3.2) despite multi-retriever fan-out. Dose safety checking appears both within the reasoning service (interaction and constraint evaluation) and as a post-reasoning validation step in the diagram to reflect the separate `dose_safety` module that flags planned doses exceeding label maxima for the patient's renal band.

### 3.2.3. Knowledge Graph Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        KNOWLEDGE GRAPH STRUCTURE                            │
└─────────────────────────────────────────────────────────────────────────────┘

                          ┌──────────────────┐
                          │   HEART_FAILURE   │
                          │    (Disease)       │
                          └────────┬─────────┘
                                   │treated_by
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
    ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
    │    ACEi      │       │ Beta Blocker │       │   SGLT2i    │
    │  (Drug)      │       │  (Drug)      │       │  (Drug)      │
    └──────┬───────┘       └──────┬───────┘       └──────┬───────┘
           │                       │                       │
           ▼                       ▼                       ▼
    ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
    │ contraindicated │   │   indication  │       │   indication  │
    │    with ARNI   │   │   for HFrEF   │       │   for HFrEF   │
    └──────────────┘       └──────────────┘       └──────────────┘

Entity Types: Drug, Disease, LabValue, DrugClass
Relationship Types: treats, contraindicated_with, indicated_for, interacts_with, metabolized_by
```

The knowledge graph centers on heart failure as a disease node linked to GDMT drug classes through `treated_by` relationships. Each drug or class node carries contraindications, indications, and interaction edges supporting local entity retrieval and multi-hop expansion in Neo4j. At runtime, GraphRAG binds patient medication terms to graph nodes, retrieves neighboring facts (for example ACEi → contraindicated_with → ARNI), and merges graph-derived evidence with textual chunks via RRF. Entity types and relation vocabularies align with ingestion JSONL relationship records synchronized from the scraper pipeline.

Graph structure complements vector retrieval: dense embeddings excel at paraphrased indication language, while graph traversal surfaces explicit contraindication triples that may be split across chunk boundaries during ingestion. The `interacts_with` and `contraindicated_with` edges directly support interaction F1 of 97.1% when combined with PostgreSQL interaction rules—the graph provides evidentiary context for verification agents, while PostgreSQL rules provide executable enforcement.

### 3.2.4. End-to-End Scenario Walkthrough: Sample Patient Case

To concretize the architecture, this section traces a representative clinical vignette through every module. The case—a 65-year-old male with HFrEF—mirrors evaluation test inputs and illustrates event ordering, module handoffs, and design decisions.

**Initial physician message (Turn 1):**

> "65-year-old male, EF 30%, currently on bisoprolol 5mg once daily. eGFR 45, K+ 4.2. Not on ACEi or MRA. Can we optimize GDMT?"

**Stage 1 — Patient Profile Extraction (Module 3.3.1).** The chat service receives the POST body and invokes hybrid intake. Regex patterns match `EF 30%` → LVEF 30 (percent unit), `eGFR 45` → eGFR 45 (mL/min/1.73m² implicit), `K+ 4.2` → potassium 4.2 mEq/L, and `bisoprolol 5mg` via lexicon NER mapping to substance key `bisoprolol`. Demographics `{age: 65, sex: male}` extract from the opening phrase. Negation detection on "Not on ACEi or MRA" suppresses false positive medication assertions for those classes while recording GDMT gaps. Because numeric fields exceed regex confidence thresholds, selective LLM merge is not invoked—keeping extraction within the 1.1s P50 latency band. The module emits SSE event `draft_ready` with serialized `PatientProfile` and compressed `clinical_state` `{intent: "gdmt_optimization", hf_type: "HFrEF", focus_classes: ["ACEi/ARB/ARNI", "MRA", "SGLT2i"], key_labs: {ef: 30, egfr: 45, k: 4.2}}`.

**Stage 2 — Missing-Field Check.** The missing-field checker confirms LVEF, eGFR, and potassium are present for MRA and RAAS evaluation. No `missing_check` event fires; the pipeline proceeds. Had potassium been absent while MRA was in scope, the system would short-circuit with a clarification prompt—a design choice prioritizing safety over speculative recommendation.

**Stage 3 — Parallel GraphRAG Prefetch (Module 3.3.2).** Concurrently with reasoning, GraphRAG constructs queries from clinical state: "HFrEF GDMT ACE inhibitor initiation eGFR 45," "MRA spironolactone eGFR 45 potassium 4.2," "SGLT2 inhibitor HFrEF eGFR 45." HyDE expansion (if enabled) generates a hypothetical passage describing GDMT optimization for this phenotype. ChromaDB dense search returns guideline chunks on four-pillar therapy; BM25 retrieves exact drug names ("bisoprolol," "spironolactone"); Neo4j expands `HEART_FAILURE → treated_by → MRA` with `indicated_for HFrEF` facts. RRF fusion merges ranked lists; chunk window expansion restores sentences split at chunk boundaries. Output: `GraphRAGContextResponse` with 12–20 evidence chunks and 3–5 graph facts—sufficient for evidence agent validation.

**Stage 4 — Deterministic Reasoning (Module 3.3.3).** Patient normalization classifies renal status as moderately reduced (eGFR 45), potassium normal (4.2 mEq/L), HF type HFrEF (LVEF ≤ 40%). GDMT gap analysis evaluates four pillars: ACEi/ARB/ARNI → `consider` (not on therapy, eligible); beta blocker → `continue` (on bisoprolol 5mg, below target); MRA → `consider` (not on therapy, eGFR and K+ within typical initiation bounds); SGLT2i → `consider` (HFrEF indication, eGFR > 20). Constraint matching queries approved rules; no hard `avoid` triggers. Interaction checks find no dangerous pairs. Overall status: `approved_with_warnings` (GDMT gaps present). SSE event `recommendation_ready` delivers structured JSON.

**Stage 5 — Dose Calculation (Module 3.3.4).** For recommended MRA (spironolactone), dose rules emit starting dose 12.5–25 mg daily, target 25–50 mg, renal adjustment noting slower titration at eGFR 30–45, and week-by-week titration steps. Bisoprolol dose plan confirms current 5mg with pathway to 10mg target per Section 3.3.4 exemplar schedule.

**Stage 6 — Verification Agents (Module 3.3.6).** Safety agent: pass (no hard avoids). Missing-data agent: pass (critical labs present). Evidence agent: pass (GraphRAG returned non-zero chunks). Citation validation maps evidence references to retrieved chunk IDs. Aggregated verdict: `pass` with informational warnings on GDMT gaps. SSE event `verification_ready`.

**Stage 7 — Card Summarizer and LLM Answer.** Card summarizer attaches Vietnamese and English plain-language labels: "Blood pressure medication" / "Thuốc hạ huyết áp" for ACEi class; "Consider" / "Cân nhắc" for status. LLM (Qwen2.5-7B) generates streaming narrative grounded in recommendation and verification payloads—explaining rationale for ACEi and MRA initiation, citing retrieved guideline passages, and explicitly noting bisoprolol uptitration opportunity. SSE events `answer_delta` stream tokens; `done` terminates with conversation metadata.

**Clinical panel update sequence.** The React dashboard renders patient summary on `draft_ready`, GDMT status grid on `recommendation_ready`, verdict badges on `verification_ready`, and chat prose incrementally on `answer_delta`. Total elapsed time: approximately 7–9 seconds on evaluation hardware (P50 7.4s, mean 8.1s, Section 5.3.2).

This walkthrough demonstrates the thesis design principle: structured safety and GDMT outcomes precede generative prose; GraphRAG grounds explanation without overriding deterministic statuses; and bilingual presentation layers operate independently of inference cost.

## 3.3. Functional Module Design

### 3.3.1. Patient Profile Extraction Module

The patient profile extraction module converts free-form physician chat into a typed `PatientProfile` schema: demographics, heart failure phenotype (LVEF, HF type, NYHA class), medications, allergies, labs (eGFR, potassium, creatinine), vitals (blood pressure, heart rate, weight), red flags (cardiogenic shock, active bleeding, acute decompensation), and care context (clinician question, ACEi last-dose timing for washout checks).

**Regex numeric extraction** applies compiled patterns to normalized text for LVEF/EF ("EF 30%", "LVEF = 35"), eGFR, serum potassium, systolic blood pressure, heart rate, weight, INR, and ACEi last-dose hours. Patterns support bilingual cues (Vietnamese diacritics stripped via Unicode NFKD normalization). Numeric capture groups tolerate comma decimal separators. Primary extraction targets the `[Current]` message segment when conversation history is aggregated, falling back to full text when isolated values appear only in prior turns.

**Lexicon NER for drugs and conditions** matches medication names against a curated catalog mapping synonyms to substance keys (generic names, common brands, Vietnamese aliases). Condition and red-flag lexicons detect CKD, diabetes, atrial fibrillation, hypertension, and acute instability phrases. Longest-token-first matching reduces substring false positives.

**Negation detection** inspects a 24-character window preceding each lexicon hit for prefixes such as "no," "not," "without," "denies," and Vietnamese "khong," suppressing false medication and condition assertions when clinicians document absent findings.

**Unit normalization** attaches standard units to `ClinicalValue` objects (percent for LVEF, mL/min/1.73m² or implicit eGFR units, mEq/L for potassium, mmHg for blood pressure, bpm for heart rate, kg for weight) and preserves raw source spans in `SourceTrace` for audit.

**Selective LLM merge** invokes a small LLM extractor only when heuristics detect low regex confidence: long narrative messages, multiple negation or contrast markers, or semantic conflicts between regex and LLM partial profiles. Merge policy `_prefer_measured` retains regex-sourced numeric labs over LLM guesses; list fields merge by normalized name keys. Prompt injection sanitization strips override patterns before LLM calls.

Output feeds `build_clinical_state`, which compresses the profile into intent, focus medication classes, and key values for GraphRAG query construction. Critical missing fields (LVEF, eGFR, potassium when MRA or RAAS therapy is in scope) trigger `missing_check` SSE events and clarification prompts before full recommendation.

#### 3.3.1.1. Design Trade-offs in Hybrid Intake

Pure regex intake minimizes latency and cost but fails on narrative chart summaries; pure LLM intake handles nuance but introduces hallucination risk and multi-second delays. The hybrid cascade mirrors the ingestion section filter (Section 4.2.6): fast deterministic methods first, LLM only on uncertainty. The `_prefer_measured` merge policy is non-negotiable for laboratories—a design invariant supporting NFR-2 accuracy. Vietnamese diacritic normalization trades occasional homograph ambiguity for recall on unaccented clinical typing common in mobile chat interfaces.

### 3.3.2. Knowledge Graph Engine Module (GraphRAG)

The GraphRAG engine assembles explanatory context—evidence chunks and graph facts—for verification agents and the LLM answer generator. It does not replace the deterministic recommendation engine; it grounds narrative and citation validation.

**HyDE expansion.** When enabled, a lightweight model (Qwen2.5-1.5B via Ollama) generates a hypothetical clinical passage answering the physician query given patient context lines (HF phenotype, key labs, focus classes). The hypothetical document is combined with the baseline query for embedding; cache keys avoid repeated expansion within TTL bounds.

**Query decomposition.** For complex turns, the decomposition module emits additional sub-queries targeting medication classes, safety labs, or interaction themes. Sub-queries join the retrieval set alongside clinical-state-derived text.

**Chroma dense search.** BGE-M3 embeddings index clinical chunks in ChromaDB collection `clinical_chunks`. Metadata filters narrow by drug class, section, and chunk type. Candidate pool size adapts to case complexity (`adaptive_top_k`).

**BM25 sparse retrieval.** An in-memory BM25 index over published chunks provides lexical recall complementary to dense search—critical for exact drug names and regulatory phrases. Hybrid fusion weighting is configurable (`hybrid_bm25_weight`).

**Neo4j neighborhood retrieval.** Cypher queries expand matched entity terms into `GraphFact` records (subject, predicate, object, provenance). Parallel retrieval runs alongside vector and BM25 searches.

**RRF fusion.** Ranked lists from Chroma, BM25, and graph-derived chunk boosts merge via reciprocal rank fusion with smoothing constant \(k\) (default 60). Post-fusion, chunk window expansion pulls adjacent chunk indices within a configurable window to restore sentence context truncated at chunk boundaries.

**Optional Cohere or semantic rerank.** When API keys are present, Cohere rerank-v3.5 rescores the top candidate pool; otherwise a bi-encoder rescore recomputes cosine similarity between query and chunk embeddings, blending with first-stage scores and source-type quality boosts (guideline versus label).

Evidence filtering removes low-quality or out-of-scope chunks; clinical entity boosting elevates chunks matching patient medication terms. Output schema `GraphRAGContextResponse` bundles ranked `EvidenceChunk` lists, `GraphFact` lists, HyDE metadata, and scope annotations for downstream agents.

#### 3.3.2.1. GraphRAG Design Rationale

Vector-only RAG retrieves semantically similar passages but may miss exact drug names embedded in tables; BM25 alone misses paraphrased guideline language. RRF fusion (Chapter 2) combines incomparable retriever scores without manual weight tuning per query type—a robustness property validated qualitatively in Section 5.5.2. Graph neighborhood retrieval adds multi-hop facts (ACEi contraindicated with ARNI) that span chunk boundaries. HyDE expansion addresses vocabulary mismatch between terse clinical queries and verbose guideline prose, at the cost of one additional small-model inference per cache miss.

### 3.3.3. Reasoning Service Module

The reasoning service produces the authoritative `RecommendationResponse` through deterministic orchestration—no LLM inside the critical path.

**Patient normalization** classifies renal status (normal, moderately reduced, severely reduced, kidney failure), potassium status, blood pressure status, heart rate status, HF type from LVEF thresholds, and comorbidity flags from structured intake.

**Risk flag derivation** emits `RiskFlag` objects for missing critical fields, renal impairment, hyperkalemia, hypotension, bradycardia, and polypharmacy—each with severity and evidentiary text referencing observed values.

**GDMT gap analysis** loads executable GDMT policies from PostgreSQL and evaluates, for each pillar class (ACEi/ARB/ARNI, beta blocker, MRA, SGLT2i), whether the patient is on therapy, eligible, contraindicated, or missing data. `recommendation_for_policy` generates class-level recommendations with priority, action verbs (start, uptitrate, avoid), linked constraint IDs, and evidence references.

**Constraint matching** queries approved `constraint_rules` filtered by target drug class, matching patient risk names and severity predicates. Actions include `avoid` (hard block), `caution`, `consider`, and `continue`. Minimum bundled safety rules apply if database governance is unavailable.

**Interaction set checks** evaluate `interaction_rules` drug-set pairs against normalized medications, producing interaction warnings with severity and management text merged into `safety_warnings`.

**Overall status** aggregates outcomes: `blocked` if any hard avoid constraint or critical safety warning exists; `approved_with_warnings` when moderate risks or soft constraints present; otherwise `approved`.

The module attaches `dose_plans` from the dose calculation service and records governance version strings for traceability.

#### 3.3.3.1. Deterministic Reasoning Invariants

Three invariants govern reasoning design: (1) LLM output never modifies `avoid` statuses; (2) hard_block rules from PostgreSQL override permissive-sounding retrieved prose; (3) overall status aggregation is monotonic—adding a hard constraint cannot be undone by subsequent modules. These invariants directly support 100% pass on structured safety scenarios (Section 5.7.1) and 92.5% safety sensitivity (Section 5.3.1).

### 3.3.4. Dose Calculation Module

The dose calculation module personalizes pharmacotherapy numeric guidance from JSONB dose rules and FDA label-derived tables.

**Starting dose** reads `starting_dose` JSON objects (`value`, `unit`, frequency) keyed by drug class and drug aliases.

**Target dose** reads `target_dose` JSON defining guideline maxima or highest tolerated dose.

**Renal adjustment** evaluates `renal_adjustment` JSON predicates against patient eGFR bands— for example halving starting dose or slowing titration when eGFR < 30.

**Titration schedule** expands `titration_schedule` JSON into week-by-week step instructions, conditional on tolerance flags.

The evaluator resolves drug keys from free-text medication names, applies eGFR bands, emits `SuggestedDosePlan` objects with recommended value, unit, frequency, renal rationale, and human-readable titration steps. Bisoprolol exemplifies the pattern:

```
Base starting dose: 1.25mg once daily
Target dose: 10mg once daily (or highest tolerated)

Renal adjustment (eGFR < 30):
  → Start at 1.25mg, titrate slower

Titration schedule:
  Week 1-2: 1.25mg
  Week 3-4: 2.5mg (if tolerated)
  Week 5-6: 3.75mg (if tolerated)
  Week 7-8: 5mg (if tolerated)
  Week 9-10: 7.5mg (if tolerated)
  Week 11+: 10mg (target)
```

Dose plans attach to the recommendation response for display alongside GDMT class actions; dose safety warnings from a separate checker flag when planned doses exceed label maxima for the patient's renal band.

JSONB encoding for dose rules trades query-time JSON parsing cost for schema flexibility when FDA labels introduce new titration patterns—a governance velocity trade-off appropriate for a domain where labeling updates occur quarterly.

### 3.3.5. Safety Constraint Engine Module

The safety constraint engine materializes PostgreSQL constraint rules into runtime `Constraint` objects and complements them with dose and interaction warnings.

**Hard constraints** are non-violable: absolute contraindications, life-threatening interactions, and `avoid` actions that set overall status to `blocked`. Example: concurrent ACEi and recent ARNI within 36 hours.

**Soft constraints** emit warnings requiring monitoring, dose adjustment, or clinical review without automatic blocking—`consider_with_caution` actions with attached monitoring plans.

```
Hard Constraint:
IF drug = ACEi AND recent_ARNI_use = true
THEN status = "avoid" (contraindicated within 36 hours)

Soft Constraint:
IF drug = MRA AND eGFR < 30
THEN status = "consider_with_caution"
AND monitoring = ["Check potassium within 1 week"]
```

Constraint rules carry `risk_names` and `severity_any` arrays matched against derived patient risk flags; evidence references link to label sections and guideline passages for GraphRAG citation validation. Admin workflows require `clinical_lead` approval before rules transition from `draft` to `approved`.

The 667 hard_block rules classified during ingestion (11.1% of extracted rules, Section 5.2.3) feed this module exclusively after clinical_lead approval—preventing draft extraction artifacts from executing at runtime.

### 3.3.6. Verification Agents Module

Verification agents cross-check the deterministic recommendation before streaming natural-language answers. The **safety agent** fails when hard `avoid` constraints exist; warns on `caution` constraints. The **missing-data agent** warns when critical labs or vitals remain unset. The **evidence agent** fails when GraphRAG returns zero chunks and graph facts. An optional **LLM agent** with tool access can propose refinements but does not override blocked statuses. Citation validation maps evidence references to retrieved chunk IDs. Aggregated verdicts (`pass`, `warning`, `fail`) appear in `verification_ready` SSE payloads.

Verification adds mean 0.5s latency (Section 5.3.2) but closes the hallucination gap between structured recommendations and LLM narrative—a defense-in-depth layer when GraphRAG retrieves permissive-sounding adjacent passages that contradict hard constraints.

## 3.4. Database Design

### 3.4.1. PostgreSQL Schema

PostgreSQL holds versioned, governable rule catalogs. JSONB columns encode structured dose objects without schema migrations for each new titration pattern.

**Constraints Table:**

```sql
CREATE TABLE constraint_rules (
    id SERIAL PRIMARY KEY,
    constraint_id VARCHAR(100) UNIQUE NOT NULL,
    version INTEGER DEFAULT 1,
    target_drug_class VARCHAR(100),
    action VARCHAR(50),  -- 'avoid', 'consider', 'continue', etc.
    reason TEXT,
    risk_names TEXT[],
    severity_any TEXT[],
    evidence_ref TEXT,
    clinical_sources JSONB,
    status VARCHAR(20) DEFAULT 'draft',  -- draft, approved, retired
    source VARCHAR(50),
    approved_by VARCHAR(100),
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB
);
```

The `action` column drives hard versus soft behavior at runtime. `risk_names` binds rules to derived risk flags (for example `hyperkalemia`, `renal_impairment`). History tables record approve/retire transitions for audit.

**Dose Rules Table:**

```sql
CREATE TABLE dose_rules (
    id SERIAL PRIMARY KEY,
    dose_rule_id VARCHAR(100) UNIQUE NOT NULL,
    version INTEGER DEFAULT 1,
    drug_class VARCHAR(100),
    drug_keys TEXT[],
    calculation_type VARCHAR(50),
    starting_dose JSONB,      -- {"value": 1.25, "unit": "mg"}
    target_dose JSONB,
    renal_adjustment JSONB,
    titration_schedule JSONB,
    evidence_ref TEXT,
    status VARCHAR(20) DEFAULT 'draft',
    safety_tier VARCHAR(50),
    metadata JSONB
);
```

**Interactions Table:**

```sql
CREATE TABLE interaction_rules (
    id SERIAL PRIMARY KEY,
    interaction_rule_id VARCHAR(100) UNIQUE NOT NULL,
    drug_set_a TEXT[],
    drug_set_b TEXT[],
    interaction_type VARCHAR(50),
    severity VARCHAR(20),
    description TEXT,
    management TEXT,
    evidence_ref TEXT,
    status VARCHAR(20) DEFAULT 'draft'
);
```

GDMT policy tables mirror the same draft/approved/retired lifecycle, storing executable class definitions consumed by the policy engine.

#### 3.4.1.1. Data Model Design Discussion

The relational schema encodes a governance-centric data model rather than a patient-centric EMR. Patient profiles exist ephemerally in Redis conversation caches; authoritative persisted state comprises rule catalogs and audit logs. This separation reflects the CDSS role as a decision adjunct, not a system of record—hospital EMRs retain longitudinal records while HF-CDSS evaluates snapshots from chat input.

The draft/approved/retired lifecycle on every rule table implements clinical governance without code deployment: clinical_leads review extraction artifacts flagged `needs_condition_refinement` (35.2% of rules, Section 5.2.3) before promotion. Version integers support diff views in the admin portal. JSONB columns (`starting_dose`, `renal_adjustment`, `clinical_sources`) accommodate heterogeneous FDA label structures that resist rigid normalization—each SPL section may express dosing differently, yet runtime evaluators consume a uniform JSON interface.

Array columns (`risk_names`, `drug_set_a`, `drug_keys`) enable PostgreSQL GIN indexing for membership queries during constraint matching. The 6,032 constraint rules and 1,096 interaction rules (Section 5.1.2) demonstrate catalog scale; runtime loaders filter to `approved` status and cache by drug class in Redis to bound query latency.

Entity-relationship semantics: constraint rules associate with drug classes and risk flags; dose rules associate with drug keys and renal bands; interaction rules associate symmetric drug sets. GDMT policies sit at a higher abstraction level, defining pillar coverage logic independent of individual drug instances—a three-level hierarchy (policy → class → substance) matching guideline organization.

### 3.4.2. Redis Cache Structure

```
# Constraint cache
constraint_cache:{drug_class} → [constraint_json]

# Draft patient cache
draft:{conversation_id} → {patient_profile_json}

# Message history cache
messages:{conversation_id} → [messages_json]

# LLM response cache
llm_cache:{hash(input)} → {response_json}
```

Redis caches constraint lookups by drug class with TTL invalidation on admin writes, draft patient profiles and message history by conversation identifier for multi-turn continuity, and LLM or HyDE response hashes to reduce latency on repeated similar queries. Ephemeral cache entries are not authoritative; PostgreSQL approved rules remain the source of truth.

Cache TTL bounds limit exposure duration for patient narratives stored in Redis (NFR-3). Admin approve/retire operations invalidate constraint cache keys synchronously to prevent stale rule execution—a consistency trade-off favoring correctness over cache hit rate.

### 3.4.3. Vector Store Schema (ChromaDB)

```python
Collection: "clinical_chunks"

Schema:
{
    "id": str,              # chunk_id
    "embedding": float[384], # embedding vector
    "document": str,         # text content
    "metadata": {
        "source": str,       # drug_label, guideline, etc.
        "drug_class": str,
        "section": str,
        "chunk_type": str    # dosing, warning, indication, etc.
    }
}
```

Embeddings are produced by BGE-M3 (dimension configuration follows deployment settings). Metadata enables pre-filtering during GraphRAG retrieval and citation linking back to source URLs and page numbers stored in chunk metadata.

ChromaDB was chosen over managed vector services for on-premise deployability alongside Ollama. Embeddings are computed offline during ingestion (batch BGE-M3), keeping query-time GraphRAG at 0.8s mean—an architectural decision separating indexing cost from interactive latency.

## 3.5. API Design

### 3.5.1. Chat API

The chat API exposes REST entry with SSE response bodies for progressive updates. Authentication headers carry JWT access tokens; conversation identifiers tie requests to Redis-backed history.

**Endpoint: POST /api/v1/chat**

```json
Request:
{
    "message": "65-year-old male, EF 30%, currently on bisoprolol 5mg...",
    "conversation_id": "conv_123",
    "patient": {
        "age": 65,
        "sex": "male",
        "diagnosis": {
            "hf_type": "HFrEF",
            "ef": 30
        }
    },
    "language": "en"
}
```

**SSE event stream (implementation event types):**

```
event: draft_ready
data: { "conversation_id": "...", "patient": {...}, "clinical_state": {...} }

event: missing_check
data: { "missing_fields": [...], "prompt": "..." }

event: status
data: { "step": "building_recommendation" }

event: recommendation_ready
data: { "recommendation": {...} }

event: verification_ready
data: { "verification": {...} }

event: status
data: { "step": "generating_answer" }

event: status
data: { "step": "generating_answer" }

event: answer_delta
data: { "content": "..." }

event: done
data: { "conversation_id": "...", "status": "complete", ... }
```

#### 3.5.1.1. SSE Event Semantics and Client Contract

Each SSE event type carries explicit semantics governing client rendering and error handling:

**`draft_ready`** — Emitted immediately after hybrid intake and `build_clinical_state` complete. Payload includes full `PatientProfile`, compressed `clinical_state`, and `conversation_id`. Clients MUST update the clinical panel patient summary upon receipt. This event arrives before any LLM invocation on typical structured inputs, supporting sub-2-second perceived responsiveness. Idempotency: re-emission on retry replaces prior draft for the same turn.

**`missing_check`** — Emitted when critical fields are absent for the requested clinical intent. Payload includes `missing_fields` array (e.g., `["potassium", "egfr"]`) and `prompt` string for clinician clarification. When present, subsequent events may include only clarification `answer_delta` tokens before `done`; `recommendation_ready` and `verification_ready` are suppressed. Clients MUST NOT render GDMT cards until missing fields are resolved in a follow-up turn.

**`status`** — Informational progress markers (`building_recommendation`, `generating_answer`). Non-terminal; clients may display loading indicators. No clinical content.

**`recommendation_ready`** — Emitted after deterministic reasoning, dose calculation, and interaction checking. Payload contains authoritative `RecommendationResponse` JSON including per-class statuses, dose plans, safety warnings, and governance version. Clients MUST render GDMT status grid and recommendation cards from this payload—not from LLM prose. This event implements the Five Rights timing principle: structured safety signals precede narrative.

**`verification_ready`** — Emitted after verification agents complete. Payload includes per-agent verdicts, aggregated status (`pass`, `warning`, `fail`), and citation validation results. Clients render verdict badges. A `fail` verdict SHOULD trigger prominent warning styling even if recommendation JSON exists.

**`answer_delta`** — Incremental LLM token chunks for clinician-facing narrative. Payload `{ "content": "..." }` appends to chat thread. Clients MUST NOT treat answer tokens as authoritative for dosing or safety status—structured events remain source of truth.

**`done`** — Terminal event with `status: "complete"`, full response metadata, and timing annotations. Clients close SSE connection or prepare for next turn. Error paths emit `done` with `status: "error"` and error detail (not shown in happy-path example).

Event ordering invariant: `draft_ready` → (`missing_check` OR (`recommendation_ready` → `verification_ready` → `answer_delta`* → `done`)). Violations indicate server bugs and should be logged client-side.

Optional `patient` field in POST body allows clients to pre-seed demographics from EHR integration (future FHIR work, Section 6.3); intake merge treats explicit JSON fields as high-confidence overrides to extracted chat values.

### 3.5.2. Admin APIs

**Constraints Management:**

```
GET    /api/v1/admin/constraints/rules
POST   /api/v1/admin/constraints/rules/{id}/approve
POST   /api/v1/admin/constraints/rules/{id}/retire
GET    /api/v1/admin/constraints/rules/{id}/history
```

**Dose Rules Management:**

```
GET    /api/v1/admin/dose-rules
POST   /api/v1/admin/dose-rules/{id}/approve
GET    /api/v1/admin/dose-rules/active  # For runtime
```

**System Health:**

```
GET    /api/v1/health
GET    /api/v1/health/ready
GET    /api/v1/health/dependencies
```

Administrative endpoints support rule lifecycle management (review, approve, retire, history) and dependency-aware health monitoring for PostgreSQL, Redis, Chroma, and LLM runtimes. Approve transitions require `clinical_lead` or `admin` roles; retire operations may be restricted to `admin` depending on rule type.

## 3.6. User Interface Design

### 3.6.1. Doctor Dashboard

The doctor dashboard uses a split layout with a chat interface on the left and a clinical panel on the right. The header provides navigation, language toggle, and user controls. The chat area displays message history and an input field for new queries; SSE handlers append streaming tokens incrementally. The clinical panel updates on `draft_ready` (patient summary: demographics, EF, eGFR, current medications), `recommendation_ready` (GDMT status indicators and class-level actions), and `verification_ready` (verdict badges and evidence counts). Plain-language labels render recommendation priorities for quick scanning.

```
┌────────────────────────────────────────────────────────────────────┐
│ Header: Logo | Navigation | Language Toggle | User               │
├───────────────────────────────┬────────────────────────────────────┤
│                               │                                    │
│   Chat Interface              │    Clinical Panel                  │
│   ┌───────────────────────┐  │    ┌────────────────────────────┐ │
│   │ Message History       │  │    │ Patient Summary           │ │
│   │                       │  │    │ • Age: 65, Male          │ │
│   │ User: Male patient    │  │    │ • EF: 30%                │ │
│   │                       │  │    │ • eGFR: 45               │ │
│   │ Assistant: Patient    │  │    │ Current Medications:     │ │
│   │ profile analyzed      │  │    │ • Bisoprolol 5mg         │ │
│   │                       │  │    └────────────────────────────┘ │
│   └───────────────────────┘  │                                    │
│   ┌───────────────────────┐  │    ┌────────────────────────────┐ │
│   │ Input: Enter message  │  │    │ GDMT Status               │ │
│   │ [Send]                │  │    │ ✓ ACEi/ARB/ARNI: Missing  │ │
│   └───────────────────────┘  │    │ ✓ Beta Blocker: On target │ │
│                               │    │ ✗ MRA: Not on list       │ │
│                               │    │ ✗ SGLT2i: Not on list   │ │
│                               │    └────────────────────────────┘ │
│                               │                                    │
│                               │    ┌────────────────────────────┐ │
│                               │    │ Recommendations           │ │
│                               │    │ ⚠️ Consider starting MRA   │ │
│                               │    │ ⚠️ Consider SGLT2i       │ │
│                               │    └────────────────────────────┘ │
└───────────────────────────────┴────────────────────────────────────┘
```

The split layout encodes a cognitive model: conversational exploration on the left, structured decision artifacts on the right. Clinicians scanning rounds can read GDMT status without parsing LLM paragraphs—a usability pattern reflected in clinical usefulness scoring of 4.5/5 (Section 5.4.3).

### 3.6.2. Admin Portal

The admin portal provides rules management for reviewing, editing, and approving clinical rules; system monitoring for health and performance tracking; and data import capabilities to ingest pipeline output into the governance catalog. Diff views highlight version changes before approval; retired rules stop appearing in runtime loaders on next cache refresh.

## 3.7. Security and Access Control

### 3.7.1. Authentication

Authentication uses **JWT** (JSON Web Token) bearer tokens issued at login, validated on each API request via FastAPI dependencies. Tokens encode subject identifier, role list, and expiry; refresh or re-login handles rotation. Session blocklisting on logout prevents reuse of compromised tokens until expiry. Redis may store session metadata for revocation lists.

### 3.7.2. Authorization

**Role-based access control (RBAC)** governs endpoints. Three clinical roles appear in deployment documentation: **doctor** (clinical chat user, implemented as `clinician` in the API role enum), **clinical_lead** (may approve or reject draft rules and manage clinical content), and **admin** (full system access including user management and configuration). Viewers may have read-only analytics access in extended deployments.

```
Roles:
├── doctor: Read-only access to chat, view recommendations
├── clinical_lead: Approve/reject rules, manage constraints
└── admin: Full system access

Permissions Matrix:
│ Action              │ doctor │ clinical_lead │ admin │
│---------------------│--------│---------------│-------│
│ Chat                │ ✓      │ ✓             │ ✓     │
│ View recommendations│ ✓      │ ✓             │ ✓     │
│ Approve rules       │ ✗      │ ✓             │ ✓     │
│ Manage users        │ ✗      │ ✗             │ ✓     │
│ System config       │ ✗      │ ✗             │ ✓     │
```

Rule approval endpoints call `require_role("clinical_lead")` or equivalent checks; unauthorized attempts return HTTP 403. Audit events log actor, action, and payload hash for governance review.

### 3.7.3. Data Encryption

Data in transit is protected with **TLS 1.3** terminated at the reverse proxy (Nginx) with modern cipher suites. PostgreSQL connections use SSL in production configurations; data at rest relies on database and filesystem encryption policies appropriate to the hosting environment. Patient profiles cached in Redis inherit the same encryption-at-rest requirements as the primary database; caches use TTL bounds to limit exposure duration. Clinical attachments and chat logs stored for audit comply with institutional retention policies configured outside the application layer.

### 3.7.4. Security Threat Model

A brief STRIDE-oriented threat model informs the security controls above and identifies residual risks for future hardening.

**Spoofing.** An attacker could attempt to impersonate a clinical_lead to approve malicious constraint rules. Mitigation: JWT signature validation, role claims bound at login, and audit logging of approve actions with actor identity. Residual risk: compromised clinical_lead credentials; institutional MFA policies are out of scope but recommended.

**Tampering.** An attacker could modify chat requests in transit to inject false laboratory values. Mitigation: TLS 1.3 on all `/api` routes. Residual risk: client-side malware altering requests before encryption—mitigated only by endpoint security policies.

**Repudiation.** A clinician might deny having received a specific recommendation. Mitigation: server-side audit logs of chat turns, recommendation JSON, and verification verdicts with timestamps. Logs do not currently include cryptographic non-repudiation signatures.

**Information disclosure.** Patient narratives in Redis caches or application logs could leak PHI. Mitigation: TTL-bounded caches, log redaction policies, encryption at rest, network segmentation in Docker Compose production profiles. Residual risk: verbose DEBUG logging in misconfigured deployments.

**Denial of service.** High-volume chat requests could exhaust Ollama GPU memory or PostgreSQL connections. Mitigation: rate limiting via Redis counters (Section 4.5), health-check gated startup, bounded retrieval pools. Residual risk: sustained adversarial load requires external WAF/rate limiting.

**Elevation of privilege.** A doctor role might attempt to call admin approve endpoints. Mitigation: FastAPI `require_role` dependencies on all governance routes; 403 responses without side effects. Unit and integration tests verify role boundaries (Section 4.6).

**Prompt injection.** A physician (or embedded text in a forwarded note) could attempt to override system instructions during LLM intake or answer generation. Mitigation: prompt injection sanitization in intake merge; verification agents check structured statuses independently of LLM prose; deterministic rules are not LLM-modifiable. Residual risk: LLM narrative could still misphrase recommendations—human review remains required.

This threat model supports NFR-3 compliance as a baseline for hospital IT security review while acknowledging that full HIPAA or local equivalent certification requires institutional processes beyond application design alone.

---

This chapter specified requirements with design rationale, layered architecture, an end-to-end patient scenario walkthrough, module-level techniques, persistence schemas with data model discussion, streaming API contracts with event semantics, interface layout, security controls, and a brief threat model for HF-CDSS. Chapter 4 maps these designs to implementation artifacts, ingestion pipelines, deployment configuration, and testing strategy.
