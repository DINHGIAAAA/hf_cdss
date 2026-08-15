# CHAPTER 3: SYSTEM DESIGN

<link rel="stylesheet" href="figures/thesis-figures.css">

Chapter 3 specifies requirements, architecture, data models, and module boundaries. Purpose, scope, thesis statement, and offline/online approach are in Chapter 1 (Section 1.2). Theory is in Chapter 2; implementation and results are in Chapters 4 and 5.

## 3.0 Orientation

Content that duplicates Chapter 1 (Section 1.2) is not repeated here. Section 3.2.1 restates the “rules as authority” principle in the full runtime architecture.

## 3.1. System Requirements

The system must read clinician chat, run GDMT and safety rules, retrieve evidence, verify outputs, and present bilingual recommendation cards plus explanation. The subsections below list functional and non-functional requirements mapped to modules.

### 3.1.1. Functional Requirements

The system must perform a connected set of clinical and operational jobs. Each job maps to modules described later in this chapter. Together they address incomplete GDMT, hard-to-remember interaction rules, individualized dosing, evidence grounding, bilingual communication, and maintainable rule catalogs.

When a doctor types a message such as "65-year-old male, EF 30%, eGFR 45, K+ 4.2, on bisoprolol 5mg," the system must turn that free text into a structured patient profile with demographics, heart failure phenotype, laboratory values, vital signs, medications, allergies, red flags, and care context. Downstream safety checks depend on typed numbers with known units; a wrong potassium value could wrongly block or approve a mineralocorticoid receptor antagonist (MRA). Intake uses a hybrid design: fast pattern matching extracts ejection fraction, eGFR, and potassium; a medication lexicon maps brand names and Vietnamese aliases to standard drug keys; negation detection prevents "not on ACEi" from being read as "on ACEi"; when the message is long or ambiguous, a language model fills gaps, but measured values from pattern matching always win over model guesses during merge.

The system must assess how completely the patient receives the four GDMT classes (ACE inhibitor, ARB, or ARNI; beta blocker; MRA; and SGLT2 inhibitor), identify gaps, and propose changes grounded in ESC and AHA/ACC/HFSA guidelines. Each recommendation must carry a clear status such as start, continue, caution, or avoid, plus linked evidence for explanation. This requirement is handled by a deterministic reasoning engine, not by the language model alone. The reasoning service reads approved policies and constraint rules from PostgreSQL and produces a structured recommendation object. GraphRAG retrieval supplies explanatory passages and citations for the narrative layer but never overrides a hard avoid status.

Dangerous combinations such as ACE inhibitors with recent ARNI use, triple RAAS blockade, or combinations that raise potassium must be detected automatically. Interaction rules live in PostgreSQL as drug-set pairs with severity and management text. Free-text medication names are normalized so that "Entresto" and "sacubitril/valsartan" resolve to the same substance key. Starting doses, target doses, renal adjustments, and titration schedules must be computed from patient characteristics. Dose rules are stored as flexible JSON objects so new titration patterns from FDA labels can be added without schema migrations. Dose-safety warnings flag planned doses that exceed label maxima for the patient's renal band.

The system must surface renal impairment, hyperkalemia, hypotension, bradycardia, and missing critical labs before recommendations are finalized. Hard constraints block unsafe actions; soft constraints emit warnings with monitoring instructions. If required labs are absent for the inferred intent (for example potassium before MRA evaluation), the pipeline stops and asks for clarification instead of guessing. Safety outcomes stream to the clinician before the conversational answer finishes generating. For every recommendation turn that proceeds past missing-field checks, the system must assemble citation-ready evidence from drug labels and guidelines and verify that structured recommendations remain consistent with hard blocks and retrieved context. Verification agents audit safety, missing data, and evidence presence before narrative generation completes.

The system must support Vietnamese and English. Doctors can switch language without losing conversation context; the chat service also auto-detects locale from each message so mixed-language threads stay coherent. Intake handles Vietnamese diacritics and bilingual medication names. Plain-language labels on recommendation cards are generated in the selected locale without re-running expensive retrieval or reasoning. The system must ingest FDA Structured Product Labels and heart-failure guidelines into governed catalogs, vector indexes, and graph stores. Clinical leads must be able to review draft rules, refine conditions, approve usable rules, and retire outdated ones without redeploying application code; only approved executable tiers affect chat recommendations. Finally, the system must expose health, readiness, and dependency probes for PostgreSQL, Redis, ChromaDB, Neo4j, object storage, and local LLM services, and audit events must record recommendation and governance actions for later review.

### 3.1.2. Non-Functional Requirements

Recommendation response time should stay below ten seconds for typical interactive queries on modest hospital hardware, with support for on the order of fifty concurrent users in a pilot deployment. Server-Sent Events (SSE) streaming shows partial results before the full conversational answer completes. Redis caching and bounded retrieval pools prevent latency from growing linearly with catalog size. Treatment recommendation accuracy should reach at least ninety percent against ESC-aligned evaluation cases measured on structured recommendation objects, not LLM prose. Hard safety constraints must never be silently missed; the system may emit precautionary alerts rather than approve therapy when kidney function or electrolytes are uncertain.

Patient data must be protected in transit and at rest according to institutional hosting policy. JWT authentication, role-based access control, TLS termination, and audit logging address baseline healthcare security expectations. Local LLM inference via Ollama supports pilots that prefer not to send vignettes to external cloud APIs. Guideline and label updates must not require application redeployment. JSONL pipeline artifacts, PostgreSQL governance tables, ChromaDB embeddings, and Neo4j imports can be refreshed independently. Draft, approved, and retired lifecycles keep automation accountable to clinical leads. Clinicians must see why a status appeared: structured cards, verification badges, and evidence excerpts with openable source links provide that trail without forcing doctors to trust opaque model text.

## 3.2. Overall Architecture

### 3.2.1. Design Principles

Four principles shape every architectural choice. Authority separation: deterministic PostgreSQL-backed rules are authoritative for GDMT statuses, hard contraindications, interactions, and dose plans. Large language models help with intake fallback, borderline document review during ingestion, query expansion, and narrative explanation; they do not become the sole source of clinical truth. Safety before prose: structured outcomes such as patient drafts, missing-field checks, recommendations, and verification verdicts stream to the clinician before answer tokens finish, encoding Osheroff's timing principle in protocol design. Governed knowledge: automated extraction produces drafts, humans promote executable rules, and runtime loaders ignore unfinished refinement rows. On-premise friendliness: the stack runs as a modular monolith with Docker Compose, local embeddings, and local generation so hospitals can pilot without mandatory cloud LLM dependency.

### 3.2.2. Three-Tier Runtime Architecture

The interactive system follows a classic three-tier layout. The presentation tier is built with React and Vite. It includes a doctor dashboard for clinical chat and evidence review, an admin portal for rule governance, and an API explorer for development. Clients subscribe to SSE streams and update the clinical panel as structured events arrive. The application tier is a FastAPI modular monolith that orchestrates hybrid intake, clinical-state construction, missing-field checks, GraphRAG retrieval, deterministic reasoning, dose calculation, dose-safety checks, verification agents, card summarization, and streaming answer generation. Async design allows GraphRAG prefetch to run in parallel with rule-engine evaluation on a thread pool, so long chat turns do not starve admin or health requests. The data tier uses several stores because no single database fits every access pattern. PostgreSQL holds governable rule catalogs, chat history, patient drafts, users, and audit events. Redis caches session slices, constraint lookups, rate limits, and repeated LLM response hashes. ChromaDB stores dense embeddings for semantic retrieval. Neo4j holds entity-relationship graphs for multi-hop clinical facts. S3-compatible object storage holds raw downloads and processed JSONL artifacts for reproducible pipeline runs. Ollama hosts local embedding and generation models.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-1-architecture.html" title="Figure 3.1 System architecture"></iframe>
  <figcaption><strong>Figure 3.1.</strong> Overall HF-CDSS runtime architecture (mono-app). Interactive duplicate: Appendix A, Figure A.1.</figcaption>
</figure>

Table 3.1 is the deployment-facing inventory for the architecture in Figure 3.1. Each row ties a runtime role (presentation, application logic, inference, or persistence) to the technology chosen in this study and the host port used in the Docker Compose pilot. Readers should use the table to see which service owns governed rules versus vectors versus graph edges, not to memorize port numbers: the important design point is that clinical authority stays in PostgreSQL while ChromaDB and Neo4j support retrieval and explanation.

**Table 3.1. Main system components and ports** (Appendix A, Table A.1)

| Component | Technology | Port | Purpose |
|-----------|-----------|------|---------|
| **Frontend (Mono App)** | React + Vite | 5173 | Doctor Dashboard + Admin Portal |
| **Backend API** | FastAPI + Python | 8000 | Clinical logic |
| **LLM Server** | Ollama | 11434 | Local LLM inference |
| **PostgreSQL** | Database | 55432 | Rules, audit, chat history |
| **Neo4j** | Graph DB | 7474 | Knowledge graph |
| **ChromaDB** | Vector DB | 8001 | Evidence embeddings |
| **Redis** | Cache | 6379 | Draft, messages, LLM cache |
| **MinIO** | S3-compatible storage | 4566 | Artifact storage (persistent dev bucket) |

Together, these processes form one deployable stack: the browser talks to FastAPI and static assets; FastAPI talks to the data tier and Ollama; batch ingestion (Chapter 4) writes the same artifact layout that bootstrap loads at backend startup. Port values may change in production behind Nginx, but the responsibility split in the table remains the contract for operations and security review.

Standalone HTML: [`tables/chapters/table-3-1-components.html`](tables/chapters/table-3-1-components.html).

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-2-datastores.html" title="Figure 3.2 Data stores"></iframe>
  <figcaption><strong>Figure 3.2.</strong> Persistence layer: PostgreSQL governance catalogs, Neo4j, ChromaDB, and Redis. Appendix A, Figure A.5.</figcaption>
</figure>

A single backend container was chosen over microservices because deployment simplicity matters more than independent scaling at pilot load. Internal module boundaries preserve testability and allow future extraction of GraphRAG or ingestion workers if needed.

### 3.2.3. Dual-Plane Architecture: Offline Knowledge and Online Reasoning

The complete system is not only the chat path. It has two cooperating planes. The offline knowledge plane acquires FDA DailyMed labels and heart-failure guidelines, filters clinically relevant sections, chunks text, extracts claims and rules, classifies safety tiers, and synchronizes artifacts into PostgreSQL, ChromaDB, and Neo4j. The online reasoning plane accepts clinician chat, builds a patient profile, evaluates governed rules, retrieves evidence, verifies consistency, and streams bilingual explanations. Without the offline plane, chat would have nothing trustworthy to enforce or cite. Without the online plane, catalogs would remain inert databases. Chapter 4 details implementation of both planes; this chapter specifies their design contracts and interactions.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-3-dual-plane.html" title="Figure 3.3 Dual-plane architecture"></iframe>
  <figcaption><strong>Figure 3.3.</strong> Dual-plane architecture: offline ingestion and governance feed governed catalogs that the online chat path enforces; dashed return path marks clinician review feedback. Appendix A, Figure A.8.</figcaption>
</figure>

### 3.2.4. End-to-End Online Data Flow

When a physician sends a chat message, processing follows a fixed safety-first sequence. Authentication establishes the caller's role. The chat service ensures a conversation identifier exists, resolves response language from message text (overriding the UI toggle when Vietnamese or English is clearly detected), and appends the user message to history. On the first turn of a new conversation, the question planner and hybrid intake may run in parallel: the planner splits multi-part questions and lists required data fields per sub-question, while intake extracts and merges patient facts. Clinical-state construction normalizes units, derives missing eGFR when creatinine, age, and sex are available, infers intent and focus drug classes (including from the prior assistant message on follow-ups), and attaches risk flags. The service emits `draft_ready` and, when planning runs, `question_plan_ready`. A missing-field checker then decides whether critical labs are absent for the inferred intent or the active planned question. If so, the pipeline emits `missing_check`, asks for clarification (with multi-question index context when applicable), and returns without producing a recommendation. Guessing electrolytes or ejection fraction is intentionally forbidden.

When required fields are present, GraphRAG prefetch starts asynchronously while deterministic recommendation building runs in a worker thread. Reasoning evaluates GDMT policies, constraints, interactions, dose plans, and dose-safety warnings. Verification agents await both the recommendation and GraphRAG context, then audit hard blocks, missing data, and evidence presence. Plain-language summaries and deterministic simplified card fields attach next. The service emits `recommendation_ready` and `verification_ready`. Finally, the explanation layer streams `answer_delta` tokens grounded in the verified recommendation and retrieved evidence, then emits `done`. Cards and safety statuses remain authoritative; narrative text remains explanatory.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-5-chat-workflow.html" title="Figure 3.5 Chat pipeline"></iframe>
  <figcaption><strong>Figure 3.5.</strong> Chat message processing from dashboard input through backend stages to SSE clinical panel. Appendix A, Figure A.2.</figcaption>
</figure>

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-6-chat-sequence.html" title="Figure 3.6 Chat sequence"></iframe>
  <figcaption><strong>Figure 3.6.</strong> Sequence of one chat turn (doctor, dashboard, API, services, Ollama). Appendix A, Figure A.7.</figcaption>
</figure>

### 3.2.5. Knowledge Graph and Hybrid Retrieval Architecture

The knowledge graph centers on heart-failure entities linked to GDMT drug classes and agents. Entity types include drugs, drug classes, diseases, laboratory concepts, and related clinical nodes. Relationship types include treats, contraindicated with, indicated for, interacts with, and related monitoring edges. At runtime, GraphRAG binds patient medication terms to graph nodes, retrieves neighboring facts, and merges graph-derived evidence with textual chunks.

Hybrid retrieval combines four complementary signals. HyDE expansion can turn a short clinician question into a hypothetical answer document before embedding, bridging vocabulary gaps. Dense ChromaDB search with BGE-M3 finds paraphrased guideline language. BM25 sparse search favors exact drug names and regulatory phrases. Neo4j neighborhood traversal surfaces multi-hop facts that may be split across chunk boundaries. Reciprocal Rank Fusion merges ranked lists without brittle hand-tuned score calibration. Optional reranking can refine the top pool when latency budgets allow.

PostgreSQL rules provide executable enforcement. The graph and vector indexes provide evidentiary context for verification and explanation. This split is the architectural heart of the thesis: retrieval grounds language; rules govern safety.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-4-graphrag.html" title="Figure 3.4 GraphRAG"></iframe>
  <figcaption><strong>Figure 3.4.</strong> GraphRAG hybrid retrieval (HyDE, multi-retriever fusion, reranking). Appendix A, Figure A.4.</figcaption>
</figure>

### 3.2.6. Component Map of the Application Tier

Inside the FastAPI application, the auth component issues and validates JWT tokens and enforces roles. The chat orchestrator owns conversation lifecycle, SSE event ordering, multi-question state, and chat audit payloads. A lightweight language resolver infers vi/en from each message. The question planner splits compound queries and declares required fields per sub-question. Clinical intake extraction owns hybrid profile building. Clinical-state and risk-extraction helpers compress profiles into intent, focus classes, and flags used by reasoning and retrieval. The missing-fields component owns fail-closed clarification gates. The reasoning service owns RecommendationResponse construction. GDMT policy, constraint, interaction, dose-calculation, and dose-safety modules supply the rule families reasoning depends on. Drug normalization maps surface strings to substance keys. GraphRAG and semantic-retrieval modules assemble evidence. Citation validation and verification agents audit consistency. Explanation modules provide card summarization and LLM narrative generation. Governance modules support admin approve, retire, and diff workflows. Datastore adapters isolate PostgreSQL, Redis, ChromaDB, Neo4j, and artifact bootstrap details from clinical logic. Each component exists because a known failure mode appears when it is missing: without normalization, interactions miss brand names; without missing-field gates, rules evaluate incomplete labs; without verification, fluent prose can contradict hard blocks; without governance, extracted drafts become silent runtime hazards.

### 3.2.7. Sample Patient Walkthrough

Consider a 65-year-old man with HFrEF, EF 30%, on bisoprolol 5 mg, eGFR 45, potassium 4.2, not on ACE inhibitor or MRA, asking to optimize GDMT.

Hybrid intake extracts demographics, labs, and medications. Because numeric fields are clear, LLM merge may be skipped, keeping extraction fast. The system emits `draft_ready` with clinical state focused on ACE inhibitor or ARNI, MRA, and SGLT2 inhibitor classes.

GraphRAG constructs queries from this state and may run HyDE expansion, ChromaDB dense search, BM25 keyword search, and Neo4j neighborhood retrieval. RRF fusion merges ranked results into a bounded evidence set and graph facts.

The reasoning engine classifies renal status as moderately reduced, potassium as normal, and HF type as HFrEF. GDMT gap analysis may yield ACE inhibitor or ARNI consider, beta blocker continue with possible uptitration, MRA consider, and SGLT2 inhibitor consider, assuming no hard avoid triggers fire. Dose calculation attaches plans when catalog rows exist. Verification agents pass or warn according to evidence and safety checks. The card summarizer attaches Vietnamese and English labels. The LLM streams a grounded narrative. The React dashboard updates the patient summary, GDMT grid, verdict badges, and chat prose progressively. Total elapsed time is typically several seconds on evaluation hardware.

If potassium had been omitted, the missing-field gate would stop the turn and ask for the value before any MRA recommendation appeared. That branch is part of the architecture, not an edge-case apology.

## 3.3. Offline Knowledge Construction Design

### 3.3.1. Goals of the Knowledge Plane

The offline plane must transform heterogeneous medical documents into three synchronized runtime views: executable governed rules in PostgreSQL, semantically searchable passages in ChromaDB, and relational facts in Neo4j. It must preserve provenance so a clinician can open the source of a citation. It must control LLM cost during ingestion. It must support resume and re-sync so operators can update one catalog family without re-downloading everything.

### 3.3.2. Pipeline Stages

Acquisition downloads immutable raw blobs from DailyMed and guideline sources into object storage. Loading and processing parse XML, PDF, and HTML into section-identified text with stable identifiers and normalized drug and unit forms. Section filtering retains clinically relevant sections through a three-tier cascade: keyword matching for standard headings, embedding similarity for paraphrased headings, and borderline LLM review only in an uncertain score band. Chunking splits kept sections into overlapping sentence-aware windows suitable for retrieval. Extraction builds constraint, dose, interaction, GDMT policy, and dose-safety artifacts using regex-first methods and schema-validated LLM enrichment when patterns are sparse. Classification assigns safety tiers and action types. Synchronization upserts catalogs to PostgreSQL and prepares vector and graph indexes.

### 3.3.3. Governance Contract Between Offline and Online Planes

Extracted rows enter draft or refinement states by default when conditions are incomplete. Clinical leads review them in the admin portal. Only approved executable tiers load into online reasoning. Retiring a rule removes it from runtime loaders after cache invalidation while preserving audit history. This contract ensures that automation accelerates catalog growth without silently deploying unsafe or incomplete logic.

## 3.4. Functional Module Design

This section describes how the online CDSS is decomposed into functional modules. Each subsection states what the module is responsible for, how it fits into the end-to-end chat flow, and which implementation files and test suites verify its behavior. Paths refer to code under `backend/app/`. **Key test case IDs** below are design contracts; full input/expected specifications appear in **Chapter 4, Section 4.6** (Tables 4.3–4.21).

The modules form a pipeline rather than a flat list. A clinician message first becomes a typed patient profile (intake and schema), then normalized observations and risk flags (normalization and risk extraction). Language is resolved from message text; a question planner may split multi-part queries and declare per-question data requirements. Drug names are canonicalized so catalogs can match free text. Deterministic reasoning applies governed constraints, dose-safety rules, interactions, and GDMT policies, optionally enriched with label-derived dose plans. In parallel, GraphRAG retrieves evidence; linking and citation validation connect recommendations to passages. Verification agents cross-check outcomes before bilingual explanation and SSE streaming deliver the answer. Governance and auth modules surround this path so only approved rules execute and only authorized users can change them.

---

### 3.4.1. Patient Profile Extraction Module

**Implementation:** `app/modules/clinical_intake_extraction/service.py`

**Purpose.** Clinicians rarely submit structured forms. They type abbreviations, mixed Vietnamese and English, brand names, and partial labs. This module converts that free text into a `PatientProfile` (Section 3.4.4) that downstream rules can evaluate, while preserving traceability to the original wording for audit.

**Three-stage design.** Stage 1 uses regular expressions and a medication lexicon to extract high-confidence numerics and drug mentions: LVEF, eGFR, potassium, blood pressure, heart rate, weight, and INR. Vietnamese aliases and brand names are included; longest-token matching avoids substring errors (e.g., matching “olol” inside another token). Negation phrases (“no,” “not,” “denies,” “không”) suppress false positives. Units are normalized where needed (for example potassium to mmol/L).

Stage 2 applies semantic matching (`semantic.py`) for brand names absent from the static lexicon, with a thread-safe embedding cache.

Stage 3 invokes a selective LLM extractor only when heuristics flag low confidence—long narratives, conflicting cues, or incomplete required fields. Merge logic deliberately prefers regex-sourced numerics over model guesses: instrument-like values outweigh probabilistic inference. Before any LLM call, `_sanitize_llm_input()` strips known injection patterns and normalizes Unicode (NFKC) to reduce prompt-manipulation risk.

**Outputs and verification.** The result is a profile rich enough for constraint matching and dose logic.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-I-01 | Vietnamese vitals/labs extraction — EF 32%, eGFR 78, K+ 4.4, SBP 118, HR 74; metoprolol 25 mg bid parsed with dose and frequency |
| TC-I-02 | Negation prevents false positives — “no CKD”, “not on spironolactone”; NKDA recorded |
| TC-I-03 | Brand-name resolution — Entresto → sacubitril/valsartan, Farxiga → dapagliflozin |
| TC-I-04 | Acute red flag — “active bleeding today” → red_flag present |
| TC-I-05 | LLM skipped when required fields complete — `_call_llm_extractor` not invoked |
| TC-I-06 | LLM enriches when confidence low — identity fields added; regex numerics override model guesses |

**Implementation file:** `backend/app/tests/test_clinical_intake_extraction.py`

---

### 3.4.2. Clinical Normalization Module

**Implementation:** `app/modules/clinical_normalization/service.py`

**Purpose.** Raw numbers are not yet clinical categories. Constraint rules reason over bands such as “severely reduced renal function” or “elevated potassium,” not isolated floats. Normalization translates typed labs and vitals into a small set of discrete status labels used everywhere else in the stack.

**Design.** All classifiers are pure functions with no I/O. Heart failure type follows guideline LVEF cutoffs: HFrEF (≤40%), HFmrEF (41–49%), HFpEF (≥50%), or unknown when LVEF is missing. Renal status uses eGFR bands from kidney failure (&lt;15) through preserved (≥60). Potassium is classified as low, normal, elevated, or high; blood pressure and heart rate receive analogous bands. Polypharmacy is detected when five or more medications are present. `normalize_patient()` assembles a `NormalizedPatientProfile`, including cleaned comorbidity strings.

| Function | Input | Output bands |
|---|---|---|
| `classify_hf_type(lvef)` | LVEF % | HFrEF ≤40, HFmrEF 41–49, HFpEF ≥50, unknown |
| `classify_renal_status(egfr)` | eGFR | kidney_failure &lt;15 … preserved ≥60, missing |
| `classify_potassium_status(k)` | K⁺ mmol/L | low &lt;3.5, normal 3.5–5.0, elevated 5.0–5.3, high ≥5.3 |
| `classify_bp_status(sbp)` | SBP mmHg | hypotension &lt;90, low 90–99, acceptable 100–130, elevated &gt;130 |
| `classify_hr_status(hr)` | HR bpm | bradycardia &lt;60, acceptable ≤100, tachycardia &gt;100 |
| `detect_polypharmacy(meds)` | medication list | True if ≥5 medications |

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-N-01 | HF type thresholds — LVEF 40→HFrEF, 45→HFmrEF, 55→HFpEF, None→unknown |
| TC-N-02 | Renal bands — eGFR 12→kidney_failure … 90→preserved |
| TC-N-03 | Potassium — K+ 3.2→low, 4.9→normal, 5.2→elevated, 5.5→high |
| TC-N-04 | BP and HR classification per thresholds above |
| TC-N-05 | Polypharmacy — 5+ medications → True |
| TC-N-06 | Comorbidity normalization — “ Chronic_Kidney Disease “ → “chronic kidney disease” |

**Implementation file:** `backend/app/tests/test_clinical_normalization.py`

---

### 3.4.3. Risk Extraction Module

**Implementation:** `app/modules/risk_extraction/service.py`

**Purpose.** Constraint rules should not re-derive clinical logic from raw labs on every evaluation. `extract_risks()` maps the normalized profile to a compact list of `RiskFlag` objects that rule authors can reference by name.

**Flags produced.** Clinical risks include renal impairment, hyperkalemia, hypotension, bradycardia, and polypharmacy. Comorbidity-derived flags include diabetes and CKD history (set when CKD appears in comorbidities even if eGFR is not reduced). Missing-data flags (`missing_egfr`, `missing_potassium`, `missing_lvef`, `missing_sbp`, `missing_heart_rate`) allow warn-and-ask behavior instead of silent guessing.

| Flag | Trigger condition |
|------|-------------------|
| `renal_impairment` | renal_status in {kidney_failure, severely_reduced, moderately_reduced} |
| `hyperkalemia` | potassium_status in {elevated, high} |
| `hypotension` | bp_status in {hypotension, low} |
| `bradycardia` | hr_status = bradycardia |
| `polypharmacy` | ≥5 current medications |
| `diabetes` | “diabetes” in normalized comorbidities |
| `ckd_history` | “chronic kidney disease” in comorbidities (even when eGFR not reduced) |
| `missing_*` | corresponding lab or vital not provided |

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-R-01 | eGFR 28, K+ 5.6, SBP 88, HR 55, 5 meds, diabetes → renal_impairment, hyperkalemia, hypotension, bradycardia, polypharmacy, diabetes |
| TC-R-02 | No LVEF → `missing_lvef` |
| TC-R-03 | LVEF only — no false renal/hyperK risks; missing lab flags present |
| TC-R-04 | CKD comorbidity + eGFR 70 → `ckd_history` set, `renal_impairment` absent |

**Implementation file:** `backend/app/tests/test_risk_extraction.py`

---

### 3.4.4. Patient Schema Module

**Implementation:** `app/schemas/patient.py` — class `PatientProfile`

**Purpose.** Every clinical module shares one canonical patient model. The schema must accept both API-style flat payloads (legacy integrations and chat drafts) and nested domain documents (richer ingestion or FHIR-like shapes) without forcing callers to transform data manually.

**Dual-shape acceptance.** A legacy flat payload supplies `case_id`, scalar labs, vitals, comorbidities, medications, and allergies at the top level. A nested payload groups identity, demographics, heart-failure profile, labs, vitals, conditions, and medications into structured sub-objects with optional `ClinicalValue` wrappers (value, unit, source). A Pydantic `model_validator` normalizes either shape into the internal representation. Computed properties (`lvef`, `egfr`, `potassium`, etc.) expose flat accessors so downstream code stays simple. Physiological range validation rejects impossible values (for example LVEF outside 0–100%). `legacy_summary()` supports older callers during migration.

**Verification.**

| TC | Description |
|----|-------------|
| TC-S-01 | Legacy flat payload — all fields map via computed properties |
| TC-S-02 | Nested domain payload — identity, demographics, labs, vitals, conditions parsed |

**Implementation file:** `backend/app/tests/test_patient_schema.py`

---

### 3.4.5. Drug Normalization Module

**Implementation:** `app/modules/drug_normalization/service.py` (runtime); `scraper/process/drug_normalization.py` (ingestion)

**Purpose.** Interaction rules, GDMT policies, and dose catalogs key on substance identifiers. Clinicians type brands (“Jardiance,” “Entresto”) and salts. Without normalization, valid rules would silently fail to match.

**Behavior.** `normalize_drug_name()` returns a canonical key; `expand_drug_search_terms()` yields brand and generic variants for retrieval; `resolve_pipeline_drug_id()` is the primary resolver used at query time. The scraper-side copy ensures ingestion and online paths share the same naming contract.

**Verification.**

| TC | Description |
|----|-------------|
| TC-D-01 | Brand → pipeline ID — Jardiance→empagliflozin, Entresto→sacubitril_and_valsartan |
| TC-D-02 | Search term expansion includes brand and generic |
| TC-D-03 | Chunk claim matching by document, section, text |
| TC-D-04 | `enrich_recommendation_evidence` attaches constraint chunk IDs |
| TC-D-05 | `prioritize_context_chunks` ranks linked chunks first |

**Implementation files:** `backend/app/tests/test_drug_normalization_and_evidence_linking.py`, `scraper/process/drug_normalization.py`

---

### 3.4.6. Constraint Builder Module

**Implementation:** `app/modules/constraint_builder/service.py`

**Purpose.** Approved constraint rules encode when a drug class should be avoided or used with caution given patient risks. `build_constraints(profile, risks)` evaluates those rules and returns `(target_drug_class, action)` pairs consumed by the reasoning service.

**Rule model and matching.** Each rule carries `constraint_id`, target class, action (`avoid` or `caution`), human-readable `reason`, `risk_names`, optional `severity_any`, and evidence metadata. Matching requires every named risk to be present and at least one listed severity to match when severities are specified—an AND-over-risks, OR-over-severities design that mirrors how clinicians phrase conditional advice.

**Caching and failure behavior.** `load_constraint_rules()` reads from PostgreSQL with a five-minute TTL cache. On database errors, the loader serves the last successful cache (fail-stale, not fail-empty). Admin approve/retire invalidates the cache.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-C-01 | Rules loaded from PostgreSQL with `constraint_id` on each |
| TC-C-02 | TTL cache — repeated calls produce single DB read |
| TC-C-03 | Stale cache served on DB error after prior success |
| TC-C-04 | Empty cache on fresh DB error |
| TC-C-05 | eGFR 25 + K+ 4.8 → MRA avoid |
| TC-C-06 | SBP 96 + K+ 5.2 → ARNI/ACEi/ARB caution |
| TC-C-07 | HR 55 → beta_blocker caution |
| TC-C-08 | Clean labs → empty constraint set |

**Implementation file:** `backend/app/tests/test_constraint_builder.py`

---

### 3.4.7. Dose Safety Module

**Implementation:** `app/modules/dose_safety/evaluator.py`, `rule_loader.py`

**Purpose.** Even when GDMT class-level advice is permissive, specific medications may require renal review, electrolyte monitoring, or dose ceilings. `evaluate_dose_safety_warnings()` evaluates label-derived warning predicates against the current profile and medication list.

**Design.** Warnings are keyed by `warning_id` and target medications. Condition operators include `lt`, `lte`, `gt`, `gte`, presence/missing, and `missing_or_lt`. Severity resolves to the highest applicable level. Representative warnings: digoxin renal review, MRA renal/potassium review, loop-diuretic monitoring in CKD. PostgreSQL unavailable → empty list (no fabricated warnings).

| warning_id | Trigger |
|------------|---------|
| `dose_digoxin_renal_review` | digoxin + reduced renal function |
| `dose_mra_renal_potassium_review` | MRA + eGFR &lt;45 or K⁺ ≥5.0 |
| `dose_loop_diuretic_lab_monitoring` | loop diuretic + CKD comorbidity |

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-DS-01 | Digoxin + MRA + loop diuretic → all three warning IDs |
| TC-DS-02 | Digoxin renal review severity = critical |
| TC-DS-03 | PostgreSQL unavailable → empty list |
| TC-DS-04 | Lisinopril + losartan → ACEi-ARB combination warning |
| TC-DS-05 | RAAS + MRA → hyperkalemia monitoring warning |
| TC-DS-06 | Anticoagulant + antiplatelet → bleeding warning |
| TC-DS-07 | MRA recommendation carries `dose_mra_renal_potassium_review` |

**Implementation files:** `backend/app/tests/test_dose_safety_evaluator.py`, `backend/app/tests/test_medication_safety.py`

---

### 3.4.8. Medication Safety — Interaction Checking Module

**Implementation:** `app/modules/interaction_checking/`, `app/api/routes/medication_safety.py`

**Purpose.** Drug–drug interactions are evaluated at query time through `/interaction/check` and `/dose/check`, independent of the main recommendation path when a standalone medication review is needed.

**Design.** Interaction rules store normalized drug-set pairs with severity and management text. The evaluator compares the patient’s normalized medication list against approved pairs. Examples include ACEi+ARB combination (triple RAAS blockade risk), RAAS inhibitor with MRA (hyperkalemia monitoring), and anticoagulant with antiplatelet (bleeding risk). Normalization (Section 3.4.5) runs before comparison.

**Key test cases:** TC-DS-04 through TC-DS-07 (Section 3.4.7).

---

### 3.4.9. Reasoning Service Module

**Implementation:** `app/modules/reasoning/service.py`

**Purpose.** Produce the authoritative `RecommendationResponse`—the structured clinical decision artifact—without placing an LLM on the critical path.

**Pipeline.** `build_recommendation()` executes nine synchronous steps: normalize the patient; extract risks; build constraints (thread-offloaded); evaluate dose-safety warnings; check interactions; load GDMT policies; emit per-class `MedicationRecommendation` statuses (`start`, `continue`, `caution`, `avoid`, `review`); attach dose plans from the dose-calculation module; compute `overall_status`. Status becomes **blocked** when any hard avoid constraint or critical warning fires; **approved_with_warnings** when risks or non-critical warnings remain; otherwise **approved**.

**Invariants.** LLM prose never upgrades an avoid decision. Hard-block rules override permissive retrieved text. Dose numbers are never invented when catalog rows are incomplete. Governance version strings stamp the response for audit reconstruction.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-REC-01 | High-risk Week-3 case → `overall_status=blocked`; MRA avoid; multiple risk flags |
| TC-REC-02 | Clean HFrEF → `overall_status=approved`; all GDMT classes consider |
| TC-REC-03 | HFpEF LVEF 55 → all GDMT classes `review` |
| TC-REC-04 | Missing eGFR/K/HR → `approved_with_warnings`; consider_with_caution on GDMT |

**Implementation file:** `backend/app/tests/test_recommendation.py`

---

### 3.4.10. Dose Calculation Module

**Implementation:** `app/modules/dose_calculation/`

**Purpose.** When label-derived dose rules exist, personalize starting dose, target dose, renal adjustments, and titration steps for the patient’s current labs and medications.

**Design.** `build_dose_plans(patient, clinical_state)` selects drug keys from profile and recommendation context, resolves eGFR/potassium bands, and returns `DosePlan` objects. The missing-fields module adds dose-personalization requirements (`weight_kg`, `sex`, `age`, `creatinine`, `inr`, `acei_last_dose_hours_ago`) when the clinician asks about titration or ARNI switch. Incomplete catalog rows yield no numeric guess.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-DC-01 | Dose plans from current medications — enalapril `plan_id` returned |
| TC-DC-02 | Recommendation includes dose plans and `dose_rules_version` |

**Implementation file:** `backend/app/tests/test_dose_calculation_integration.py`

---

### 3.4.11. GraphRAG and Evidence Retrieval Module

**Implementation:** `app/modules/graphrag/service.py`, `app/modules/evidence_filter.py`, `app/modules/evidence_quality.py`

**Purpose.** Recommendations must be explainable with guideline and label passages, not model parametric memory alone. This module assembles citation-ready context from vector, lexical, and graph stores.

**Hybrid retrieval.** Four signals complement one another. HyDE expansion (`hyde_expansion.py`) drafts a hypothetical evidence paragraph from a short clinical query, then embeds it—bridging shorthand (“start MRA?”) to regulatory prose. Dense retrieval queries ChromaDB with BGE-M3 embeddings. Sparse BM25 retrieval favors exact drug names and regulatory phrases. Graph retrieval walks Neo4j neighborhoods seeded by patient medications and conditions. Reciprocal Rank Fusion merges ranked lists without hand-tuned score calibration.

**Filtering and boosting.** `filter_evidence_chunks()` drops low-quality or off-topic sections (packaging, contact information, generic wellness text lacking patient-specific terms). Patient entities (medications, abnormal labs) score relevance. Constraint-pinned chunks always survive filtering. If too few chunks remain, backfill restores a minimum `top_k` floor so verification never faces an empty context. Post-fusion boosting elevates passages mentioning current therapies.

**Outputs.** Ranked `evidence_chunks`, `graph_facts`, and `retrieval_sources`.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-E-01 | Patient entities include medications and abnormal labs |
| TC-E-02 | Negative filter drops low-quality/noisy chunks |
| TC-E-03 | Constraint-pinned chunks always kept |
| TC-E-04 | Backfill when too few results — meets `top_k` floor |

**Implementation file:** `backend/app/tests/test_evidence_filter.py`

---

### 3.4.12. Evidence Linking and Citation Module

**Implementation:** `app/modules/evidence_linking/service.py`

**Purpose.** Connect deterministic recommendation metadata to retrieved passages so cards and narratives cite the right source.

**Behavior.** `find_chunk_for_claim()` matches claims to chunks by document, section, and text overlap. `enrich_recommendation_evidence()` attaches constraint `evidence_ref` chunk IDs to each `MedicationRecommendation`. `prioritize_context_chunks()` reorders context so linked passages appear before generic high-score hits. Citation helpers append PDF page fragments (`#page=N`) so clinicians can open the exact location in source documents.

**Verification.** TC-D-03 through TC-D-05 (Section 3.4.5).

---

### 3.4.13. Citation Validation Module

**Implementation:** `app/modules/citation_validation/service.py`

**Purpose.** Before streaming an answer, verify that cited evidence actually appears in the retrieved context.

**Behavior.** `validate_citations(recommendation, context)` cross-checks each constraint `evidence_ref` against `evidence_chunks`, producing per-citation verdicts (`supported`, `weakly_supported`, `unsupported`) and an aggregate status (`strong`, `weak`, `missing`). `source_link_for_chunk()` builds clickable URLs with page anchors from chunk metadata.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-CV-01 | Matching chunk → supported verdict with evidence_refs |
| TC-CV-02 | Source link includes `#page=N` fragment |
| TC-CV-03 | Confidence score &gt; 0 for supported items |

**Implementation file:** `backend/app/tests/test_citation_validation.py`

---

### 3.4.14. GraphRAG Verification Agents Module

**Implementation:** `app/modules/verification_agents/` (six agents)

**Purpose.** Independent agents cross-check the deterministic recommendation and retrieved context before narrative generation—a fail-closed gate on top of rules.

**Agents.**

| Agent | Role | Fail-closed behavior |
|-------|------|---------------------|
| `safety_agent` | Hard avoid constraints respected | Fails if block contradicted by permissive narrative |
| `missing_data_agent` | Required labs for intent | Warns when critical labs unset |
| `evidence_agent` | Evidence retrieved for claims | Fails if no usable chunks |
| `guideline_alignment_agent` | Within guideline bounds | Passes when policy-consistent |
| `citation_validator_agent` | Citation-to-chunk linkage | Sets strong/weak/missing citation status |
| `final_reviewer_agent` | Aggregates verdicts | Any `fail` → `final_verdict=fail` |

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-G-01 | GraphRAG context returns graph_facts, evidence_chunks, retrieval_sources |
| TC-G-02 | All six agents produce results on typical HFrEF case |
| TC-G-03 | Final verdict ∈ {pass, warning, fail} |
| TC-G-04 | Citation status ∈ {strong, weak, missing} |

**Implementation file:** `backend/app/tests/test_graphrag_agents.py`

---

### 3.4.15. Explanation and Card Summarizer Module

**Implementation:** `app/modules/explanation/card_summarizer.py`, `llm_service.py`

**Purpose.** Deliver bilingual, plain-language summaries suitable for busy clinicians—fast enough to toggle language without re-running retrieval.

**Two layers.** Deterministic card summarizer maps drug-class codes to localized phrases in under two seconds. LLM layer (`attach_plain_language_summaries()`) generates richer prose per class, cached in Redis (24 h). For Vietnamese and English outputs, Han-script characters are stripped from streamed tokens when the resolved locale is not Chinese—preventing CJK leakage from the base model. `question_focus.py` derives `focus_class_ids` from the clinician message and prior assistant excerpt so follow-up answers stay on the requested drug class. `merge_summaries()` falls back per item; structured `plain_language_summary` is authoritative over generated text.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-CS-01 | Vietnamese summary contains ARNI/RAAS; no English placeholder |
| TC-CS-02 | Vietnamese card details in plain language |
| TC-CS-03 | Unknown drug classes ignored in LLM map |
| TC-CS-04 | Per-item fallback when LLM omits one class |
| TC-CS-05 | `fallback_answer` prefers `plain_language_summary` |
| TC-CS-06 | Compact payload includes plain_language_summary |
| TC-CS-07 | LLM disabled → deterministic text only |
| TC-CS-08 | LLM JSON mapped to correct drug-class summaries |
| TC-CS-09 | Han-script characters stripped from vi/en streamed tokens and compact payload |
| TC-CS-10 | Follow-up clinical state inherits `focus_class_ids` from prior assistant message |

**Implementation file:** `backend/app/tests/test_card_summarizer.py`, `backend/app/tests/test_explanation.py`

---

### 3.4.16. Chat Orchestration and SSE Module

**Implementation:** `app/modules/chat/service.py` (`stream_chat`), `app/modules/chat/language.py`, `app/modules/chat/clinical_state.py`, `app/modules/question_planner/service.py`, `app/modules/missing_fields/service.py`

**Purpose.** Orchestrate the full turn from authenticated message to streamed response, preserving multi-turn patient context, bilingual locale, multi-question threads, and audit payloads.

**Language resolution.** `detect_message_language()` applies fast heuristics (Vietnamese diacritics, bilingual keyword hints, English question words) without an LLM call. `resolve_chat_language()` prefers the detected locale over the UI `language` field so a Vietnamese question still receives Vietnamese cards even when the dashboard toggle is English.

**Question planning.** `plan_clinical_questions()` splits compound messages into ordered `PlannedQuestion` objects with per-question intent, `focus_class_ids`, and `required_data_fields`. A rule-based fallback always runs; an optional LLM planner enriches ambiguous cases. `looks_like_obvious_single_question()` skips the planner LLM when the rule split finds exactly one question—reducing latency on typical single-intent turns. On the first draft of a conversation, planning and patient intake execute in parallel via `asyncio.gather`.

**Clinical state.** `build_clinical_state()` compresses the merged profile and message into intent (`dose_adjustment`, `start_medication`, `choice_question`, `follow_up_detail`, etc.), HF phenotype, key labs/vitals, safety flags, mentioned medications, and focus GDMT classes. On follow-up turns, `focus_class_ids_from_message()` also reads the prior assistant excerpt so “explain more” stays anchored to the drug class already under discussion.

**Missing-field gate.** `check_missing_fields()` and `check_required_field_ids()` stop the turn when GDMT labs or dose-personalization fields are absent. Dose intents accept eGFR without redundant creatinine; ARNI questions on ACEi therapy require `acei_last_dose_hours_ago`. `build_missing_fields_prompt()` echoes the active sub-question index when a multi-question batch is in progress.

**Multi-question flow.** When two or more questions are detected, the orchestrator answers the first, emits `multi_question_ready`, and stores pending state. The clinician continues with `multi_question_action=continue` or stops with `stop`. Confirmation footers append to streamed answers without hiding the LLM prose.

**Processing order (safety-first).** After language resolve and optional parallel plan+intake, hybrid intake merges the patient draft (`draft_ready`). If critical fields are missing, the pipeline emits `missing_check` and stops. Otherwise GraphRAG prefetch runs asynchronously while PostgreSQL rule evaluation executes in a worker thread. Verification joins both branches; summarization prepares cards and optional LLM prose; the stream emits `recommendation_ready`, `verification_ready`, tokenized `answer_delta` events, and a terminal `done` snapshot. Each terminal path records a structured chat audit payload.

**SSE contract.** Progress `status` events bracket the turn. `question_plan_ready` carries the planner output. `draft_ready` carries the merged `PatientDraft`. `missing_check` lists absent fields. `multi_question_ready` exposes pending sub-questions. `recommendation_ready` and `verification_ready` surface structured safety artifacts before narrative tokens. `answer_delta` streams explanation text. `done` closes with the full response.

**Continuity.** Conversation history informs intake on follow-up turns; drafts persist in PostgreSQL with Redis caching (30 min TTL).

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-LG-01 | Vietnamese diacritics → `vi` |
| TC-LG-02 | English clinical question → `en` |
| TC-LG-03 | ASCII Vietnamese hints → `vi` |
| TC-LG-04 | Detected locale overrides UI default |
| TC-QP-01 | Multi-question message → three planned sub-questions with required fields |
| TC-QP-02 | ARNI plan requires `acei_last_dose_hours_ago` when patient on ACEi |
| TC-QP-03 | Planner falls back when LLM disabled |
| TC-QP-04 | Rule split preserved when LLM under-splits |
| TC-MF-01 | Dose intent: eGFR present → creatinine not required |
| TC-MF-02 | Missing eGFR and creatinine → renal lab requested |
| TC-MF-03 | ARNI on ACEi → washout timing requested in EN/VI prompt |
| TC-MF-04 | Multi-question index echoed in missing-fields prompt |
| TC-CH-01 | New turn creates draft and asks for missing fields |
| TC-CH-02 | SSE stream emits `missing_check` before early `done` |
| TC-CH-03 | Nested patient payload accepted; intake enriches contextual fields |
| TC-CH-04 | Chat history reloads from persistent store |
| TC-CH-05 | Prior-turn clinical facts merge into draft |
| TC-CH-06 | Multi-question message → `multi_question_ready` SSE event |
| TC-CH-07 | `multi_question_action=stop` clears pending batch |
| TC-CH-08 | `multi_question_action=continue` answers next sub-question |

**Implementation files:** `backend/app/tests/test_chat_language.py`, `test_question_planner.py`, `test_missing_fields.py`, `test_chat.py`, `test_explanation.py`

---

### 3.4.17. Governance and Admin Module

**Implementation:** `app/modules/governance/`, `app/api/routes/admin/`

**Purpose.** Human-in-the-loop control over catalogs produced by the offline pipeline. Only approved executable tiers load into online reasoning; retired rules disappear from runtime loaders while history remains auditable.

**Lifecycle.** Rules progress `draft` → `approved` → `retired`; invalid transitions return HTTP 400. The diff engine (`governance/diff.py`) compares versions field-by-field per catalog family (constraints, dose rules, interactions, GDMT policies, dose-safety warnings), surfacing added, removed, or modified fields for reviewers. Role enforcement limits approval to `clinical_lead` and full administration to `admin`; `viewer` reads active catalogs only. Admin routes under `/admin/` expose list, search, approve, retire, user management, governance audit log access, and searchable chat audit at `/admin/audit/chat`. Approve and retire synchronously invalidate constraint caches so the next chat turn sees updated logic.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-AD-01 | Admin constraint routes require JWT |
| TC-AD-02 | `clinical_lead` can read active rules; `viewer` rejected on write routes |
| TC-AD-03 | `admin` can list and create users |
| TC-AD-04 | Approve draft rule → status `approved` |
| TC-AD-05 | Invalid lifecycle transition → HTTP 400 |
| TC-AD-06 | Diff engine detects field-level changes |
| TC-AD-07 | Bearer JWT accesses clinical routes without API key |
| TC-AD-08 | Versioned and legacy auth login paths both work |

**Implementation files:** `backend/app/tests/test_governance.py`, `test_admin_routes.py`

---

### 3.4.18. Auth and Security Module

**Implementation:** `app/core/jwt.py`, `passwords.py`, `middleware.py`

**Purpose.** Authenticate clinicians, authorize governance actions, and reduce abuse and data-leakage risk on a system that handles clinical narratives.

**Mechanisms.** Short-lived JWT access tokens encode user ID and roles; session cookies offer a browser-friendly alternative cleared on logout. Machine clients may use `X-API-Key`. RBAC distinguishes `clinical_lead` (chat plus rule approval), `clinician`/`doctor` (chat), `admin` (full access), and `viewer` (read-only catalogs). Login rate limiting uses a sliding window in middleware. Validation errors avoid echoing raw user input that might contain PHI—only field names and structured codes return. Each request receives a propagated request ID for log correlation. Revoked or inactive users are rejected even when the token signature is valid.

**Verification.** TC-AD-01 through TC-AD-05 plus `test_security_hardening.py` and `test_production_hardening.py` (rate limits, metrics, degraded-dependency responses).

---

### 3.4.19. Chat Persistence and Audit Modules

**Implementation:** PostgreSQL chat tables; `cdss_audit_events`; `app/modules/datastores/postgres.py` (`search_chat_audit_events`); `app/api/routes/admin/audit.py`

**Purpose.** The CDSS is not a hospital-wide EHR, but conversation and recommendation audit trails are first-class. Conversations, messages, and patient drafts persist in PostgreSQL so sessions reload across visits. Redis caches hot drafts for latency. `_chat_audit_payload()` records missing-field stops, recommendation completions, and governance actions with timestamps, actor identity, user question text, patient snapshot, and assistant answer metadata—supporting later review in the admin portal (`ChatAuditPage`).

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-AU-01 | `GET /admin/audit/chat?q=…` returns searchable chat audit items (admin JWT) |
| TC-AU-02 | Audit payload includes `user_question`, patient snapshot, and assistant answer |

**Implementation files:** `backend/app/tests/test_chat_audit_api.py`, `test_chat.py` (history persistence)

## 3.5. Database and Storage Design

### 3.5.1. PostgreSQL as Governance and Conversation Store

PostgreSQL is the sole source of truth for all clinical decision logic, governance metadata, user accounts, and conversation state. The schema is governance-centric rather than a full hospital EMR. Authoritative clinical decision logic lives in approved catalogs. Patient state for decision support may be ephemeral across turns yet still persisted enough for continuity and audit.

**Table Summary**

| Table | Purpose |
|---|---|
| `users` | User accounts, authentication, and role-based access control |
| `chat_conversations` | Top-level conversation sessions keyed by conversation ID |
| `chat_messages` | Individual messages within a conversation |
| `chat_patient_drafts` | Persisted patient profile drafts extracted from chat |
| `cdss_audit_events` | Structured audit log of all CDSS recommendation and governance events |
| `constraint_rules` | Executable GDMT eligibility rules (contraindications, required monitoring) |
| `constraint_rule_history` | Change audit trail for constraint rule lifecycle transitions |
| `dose_rules` | Medication dose calculation rules with titration schedules and renal adjustments |
| `dose_rule_history` | Change audit trail for dose rule lifecycle transitions |
| `interaction_rules` | Drug-drug interaction rules with severity and management guidance |
| `interaction_rule_history` | Change audit trail for interaction rule lifecycle transitions |
| `gdmt_policies` | Executable heart-failure GDMT class policies and recommendations |
| `gdmt_policy_history` | Change audit trail for GDMT policy lifecycle transitions |
| `dose_safety_warnings` | Numeric dose ceiling and safety predicate warnings |
| `dose_safety_warning_history` | Change audit trail for dose safety warning lifecycle transitions |

All governance catalog tables share a common lifecycle pattern: a main table holding the current active version of each rule, and a companion history table recording every status transition. The standard lifecycle states are `draft` → `approved` → `retired`. Each rule carries `version` for idempotent upserts and `metadata` (JSONB) for extensibility.

Detailed table schemas, including all columns, data types, constraints, and indexes, are documented in **Appendix B: Database Schema Reference**.

### 3.5.2. Redis Cache Design

Redis provides hot-path caching for frequently accessed data without competing with PostgreSQL as the source of truth. Cache entries are never clinical ground truth; they are performance optimizations only.

| Key Pattern | Value | TTL | Purpose |
|---|---|---|---|
| `draft:{conversation_id}` | PatientDraft JSON | 30 min | Persisted patient profile for active conversation |
| `messages:{conversation_id}` | `[ChatMessage]` JSON array | 30 min | Recent message history for a conversation |
| `llm_cache:{hash}` | Serialized LLM response | 24 h | Deduplicate repeated generation calls |
| `idempotency:{hash}` | Serialized response | 10 min | Idempotent retry deduplication |
| `constraint_cache:{drug_class}` | Constraint rule set | 5 min | Loaded rules per drug class |

Admin approve or retire operations invalidate the relevant constraint cache key, preventing stale rules from executing after governance changes.

### 3.5.3. ChromaDB Vector Store Design

ChromaDB stores semantic evidence chunks for GraphRAG retrieval. All embeddings are computed offline during the ingestion pipeline using the BGE-M3 model; runtime queries are pure nearest-neighbor lookups with no training.

**Collection: `heart_failure_evidence`**

| Field | Type | Description |
|---|---|---|
| `id` | `VARCHAR` | Unique chunk identifier (content-addressed) |
| `embedding` | `FLOAT[384]` | BGE-M3 dense embedding vector |
| `document` | `TEXT` | Full passage text |
| `metadata.source` | `TEXT` | Source type: `drug_label`, `guideline`, `interaction_db` |
| `metadata.drug_class` | `TEXT` | GDMT drug class the chunk relates to |
| `metadata.section` | `TEXT` | SPL or guideline section name |
| `metadata.chunk_type` | `TEXT` | Chunk category: `dosing`, `contraindication`, `monitoring`, `indication` |
| `metadata.chunk_id` | `TEXT` | Original chunk identifier for citation linking |

### 3.5.4. Neo4j Graph Store Design

Neo4j stores the heart-failure knowledge graph imported from pipeline artifacts. It is optimized for multi-hop neighborhood traversal, not for enforcing clinical rules (which remains PostgreSQL's responsibility).

**Core Entity Types:** `Drug`, `DrugClass`, `Disease`, `LabConcept`, `Condition`, `Guideline`

**Core Relationship Types:** `TREATED_BY`, `CONTRAINDICATED_WITH`, `INDICATED_FOR`, `INTERACTS_WITH`, `MONITORS`, `RELATED_TO`

At runtime, patient medication and condition terms are resolved to graph nodes, and bounded neighborhoods are retrieved and merged with ChromaDB passages to form the GraphRAG evidence set.

### 3.5.5. Object Storage Design

S3-compatible storage hosts two primary bucket families. Development uses **MinIO** (port 4566) with a named Docker volume so artifacts survive container recreate; production uses AWS S3 with the same key layout.

| Bucket | Content | Purpose |
|---|---|---|
| `raw` | DailyMed XML/SPL files, guideline PDFs, DrugBank exports | Immutable source archives |
| `processed` | Normalized JSONL chunks, extracted rules, graph exports | Pipeline outputs consumed by bootstrap |

Content-addressed keys and pipeline checkpoints enable efficient partial re-runs: operators can resume from a named pipeline stage without re-downloading or re-processing unchanged upstream artifacts.

## 3.5. API Design

The API is registered under `app/api/router.py`. All routes share the `/api/v1` prefix. The 19 registered route modules are:

| Route module | Prefix | Auth | Purpose |
|---|---|---|---|
| `health.router` | `/health` | None | Liveness, readiness, version |
| `chat.router` | `/chat`, `/chat/stream` | JWT or API key | Chat + SSE streaming |
| `recommendation.router` | `/recommend` | JWT or API key | Standalone recommendation |
| `clinical_pipeline.router` | `/clinical/normalize`, `/clinical/risks`, `/clinical/constraints` | JWT or API key | Intake, normalization, constraints |
| `dosing.router` | `/dosing` | JWT or API key | Dose calculation |
| `medication_safety.router` | `/dose/check`, `/interaction/check` | JWT or API key | Safety checks |
| `graphrag.router` | `/graphrag/context` | JWT or API key | GraphRAG evidence assembly |
| `evidence.router` | `/evidence/search` | JWT or API key | Evidence passage search |
| `retrieval.router` | `/retrieval` | JWT or API key | Semantic and BM25 retrieval |
| `knowledge_graph.router` | `/knowledge-graph` | JWT or API key | KG entity and relationship lookup |
| `llm.router` | `/llm` | JWT or API key | LLM answer generation |
| `audit.router` | `/audit` | JWT or API key | Recommendation audit history |
| `auth.router` | `/auth/login`, `/auth/me`, `/auth/logout` | None | Login, session, logout |
| `admin/constraint_rules_router` | `/admin/constraints` | JWT (clinical_lead/admin) | Constraint rule governance |
| `admin/dose_rules_router` | `/admin/dose_rules` | JWT (clinical_lead/admin) | Dose rule governance |
| `admin/dose_safety_warnings_router` | `/admin/dose_safety` | JWT (clinical_lead/admin) | Dose safety governance |
| `admin/interaction_rules_router` | `/admin/interactions` | JWT (clinical_lead/admin) | Interaction rule governance |
| `admin/gdmt_policies_router` | `/admin/gdmt` | JWT (clinical_lead/admin) | GDMT policy governance |
| `admin/audit_router` | `/admin/audit`, `/admin/audit/chat` | JWT (clinical_lead/admin) | Governance and chat audit search |

Legacy aliases mount `/api/auth/*` alongside versioned auth routes. A `/routes` endpoint catalogs all public routes for API explorer tooling.

### 3.5.1. Chat APIs

The primary clinician path is streaming chat at `POST /api/v1/chat/stream`. A non-streaming version exists at `POST /api/v1/chat`. History endpoints (`GET /api/v1/chat/{conversation_id}/history`) reload messages and drafts. Requests carry JWT credentials, message text, conversation identifier, optional pre-seeded patient fields, language preference, and optional attachments.

SSE event order is a hard API contract: status frames, optional `question_plan_ready`, `draft_ready`, `missing_check` when needed, optional `multi_question_ready`, then either early `done` or the sequence `recommendation_ready`, `verification_ready`, `answer_delta` tokens, and `done`. Clients must render GDMT grids from recommendation payloads, not from answer tokens.

### 3.5.2. Supporting Clinical APIs

Dedicated endpoints expose recommendation building (`POST /api/v1/recommend`), GraphRAG context assembly (`POST /api/v1/graphrag/context`), verification (`POST /api/v1/verify`), dose calculation (`POST /api/v1/dosing`), medication safety checks (`POST /api/v1/dose/check`, `POST /api/v1/interaction/check`), clinical normalization (`POST /api/v1/clinical/normalize`), risk extraction (`POST /api/v1/clinical/risks`), evidence search (`GET /api/v1/evidence/search`), retrieval (`POST /api/v1/retrieval`), knowledge-graph lookups (`GET /api/v1/knowledge-graph`), and case audit history (`GET /api/v1/audit`). These endpoints support the doctor dashboard, admin tooling, API explorer demos, and automated tests. Each concern can be exercised without running the full SSE chat path.

### 3.5.3. Auth, Health, and Admin APIs

Auth routes (`/api/v1/auth/login`, `/api/v1/auth/me`, `/api/v1/auth/logout`) handle login, current user, and logout with cookie or bearer token patterns as configured. Health routes expose liveness (`GET /api/v1/health/live`), readiness (`GET /api/v1/health/ready`), version, and dependency status separately for PostgreSQL, Redis, ChromaDB, Neo4j, object storage, and Ollama. Admin routes manage governance catalogs under role checks. Metrics endpoints (`GET /api/v1/metrics`) expose Prometheus counters.

### 3.5.4. Error and Idempotency Design

Missing-field short circuits are successful clinical outcomes, not server crashes. They return structured `MissingFieldCheck` payloads with HTTP 200. True failures emit terminal error status in the SSE stream or structured `ErrorResponse` with HTTP 4xx/5xx for non-stream routes. Idempotency keys (`X-Idempotency-Key` header) may cache identical chat responses in Redis (10 min TTL) to reduce duplicate GPU load during retries.

## 3.7. User Interface Design

### 3.7.1. Doctor Dashboard

The doctor dashboard uses a split layout: conversation sidebar and chat thread on one side, clinical panel on the other. The header provides sidebar toggle, case title, language controls, and conversation actions such as new chat, clear messages, and delete conversation.

The chat thread displays history and streams assistant tokens. The clinical panel updates on structured events: patient context on `draft_ready`, GDMT and safety cards on `recommendation_ready`, verification badges on `verification_ready`, and evidence excerpts for grounding. Cards bind only to structured fields and deterministic simplified labels. Evidence cards emphasize readable document titles, pages, publishers, and open-source links rather than technical chunk identifiers.

This layout encodes a cognitive model. Conversational exploration happens in the chat. Decision artifacts stay scannable in the panel. Clinicians on rounds can read statuses without parsing long paragraphs.

### 3.7.2. Admin Portal

The admin portal provides catalog tables for constraints, dose rules, interactions, GDMT policies, and dose-safety warnings. Detail views show conditions, provenance, and lifecycle controls. Diff views highlight changes between versions. Evidence search helps reviewers inspect passages while curating rules. Sticky action columns and short clinical titles reduce visual noise so reviewers focus on drug, action, and condition meaning.

### 3.7.3. API Explorer and Shared UI Concerns

An API explorer helps developers and evaluators exercise endpoints during demos. Shared frontend packages keep evidence formatting and API clients consistent between doctor and admin apps. Bilingual message catalogs drive UI chrome independently of clinical inference.

## 3.8. Deployment Topology Design

Although Chapter 4 covers implementation commands, deployment shape is an architectural decision. Docker Compose co-locates PostgreSQL, Redis, Neo4j, ChromaDB, Ollama, object storage, backend, frontends, and Nginx on a single pilot host. Nginx terminates HTTP, serves the doctor UI at the site root, serves admin under a path prefix, and proxies API and SSE traffic with buffering disabled. GPU passthrough to Ollama supports local generation. Health checks gate backend startup until dependencies are ready.

This topology favors institutional control and demo reproducibility over hyperscale elasticity. Horizontal microservice split remains possible later because module boundaries already isolate GraphRAG, reasoning, and governance.

## 3.9. Security and Access Control

### 3.9.1. Authentication and Authorization

Authentication uses JWT access tokens validated on protected routes. Tokens encode subject and roles. Logout can blocklist or clear cookies according to deployment mode. Authorization uses roles such as clinician or doctor for chat, clinical lead for rule approval, and admin for full system access. Governance write endpoints enforce role checks and return forbidden responses without side effects when unauthorized.

### 3.9.2. Data Protection

TLS terminates at the reverse proxy in production-like deployments. Database connections should use encrypted transport where institutional policy requires it. At-rest protection relies on host and volume encryption practices. Redis TTLs limit lingering exposure of cached narratives. Logs should avoid unnecessary clinical detail in production configurations.

### 3.9.3. Threat Model Summary

Spoofing of privileged approvers is mitigated by signed JWTs, role claims, and audited approve actions; compromised credentials remain a residual institutional risk. Tampering with requests in transit is mitigated by TLS. Repudiation concerns are addressed by server-side audit of chat and recommendation payloads. Information disclosure risks from caches and logs are reduced by TTLs, redaction discipline, and network segmentation. Denial of service against GPU or database capacity is mitigated by rate limits, bounded retrieval pools, and health-gated startup. Privilege elevation attempts on admin routes are blocked by role dependencies. Prompt injection into intake or answer generation is mitigated by merge sanitization, verification against structured statuses, and hard rules that models cannot rewrite. Human review of narrative remains required.

## 3.10. Design Traceability to Research Goals

The architecture answers the thesis research goals directly. The offline plane and governance catalogs address sustainable knowledge construction from FDA labels and guidelines. Deterministic reasoning plus hybrid GraphRAG and verification address accurate, fail-closed recommendations with grounded explanation. SSE-delivered bilingual cards and conversation continuity address usable clinician workflow. Non-functional targets for latency, accuracy, and security constrain technology choices such as local Ollama inference, Redis caching, and modular monolith deployment.

## 3.11. Chapter Summary

This chapter specified the complete system design of the heart-failure CDSS grounded in actual implementation artifacts. Requirements cover clinical decision support, evidence grounding, bilingual use, governance, and operations.

The architecture combines a three-tier online stack with an offline knowledge-construction plane. Authority stays with governed PostgreSQL rules; GraphRAG and language models support retrieval and explanation; SSE ordering delivers safety artifacts before prose.

Section 3.4 detailed 19 functional modules with implementation references and test case IDs:
- **3.4.1** Clinical intake: `extract_patient_from_message_sync` with three-stage regex→semantic→LLM pipeline; prompt injection defense; negation detection; TC-I-01 through TC-I-06
- **3.4.2** Normalization: pure classification functions `classify_hf_type`, `classify_renal_status`, `classify_potassium_status`, `classify_bp_status`, `classify_hr_status`, `detect_polypharmacy`; TC-N-01 through TC-N-06
- **3.4.3** Risk extraction: `extract_risks` producing 12 risk flags including `ckd_history` preservation invariant; TC-R-01 through TC-R-04
- **3.4.4** Patient schema: `PatientProfile` with Pydantic `model_validator` accepting legacy flat and nested domain payloads; TC-S-01 through TC-S-02
- **3.4.5** Drug normalization: `normalize_drug_name`, `expand_drug_search_terms`, `resolve_pipeline_drug_id`; TC-D-01 through TC-D-05
- **3.4.6** Constraint builder: `build_constraints` with TTL cache and stale-on-DB-error fallback; TC-C-01 through TC-C-08
- **3.4.7** Dose safety: `evaluate_dose_safety_warnings` with condition operators; TC-DS-01 through TC-DS-07
- **3.4.8** Interaction checking: `/dose/check` and `/interaction/check` endpoints
- **3.4.9** Reasoning service: `build_recommendation` with 9-step pipeline; no LLM in critical path; TC-REC-01 through TC-REC-04
- **3.4.10** Dose calculation: `build_dose_plans`, `dose_source_version`; TC-DC-01 through TC-DC-02 (Table 4.17)
- **3.4.11** GraphRAG: four-signal hybrid retrieval with RRF fusion and evidence filtering
- **3.4.12** Evidence linking: `enrich_recommendation_evidence`, `prioritize_context_chunks`
- **3.4.13** Citation validation: `validate_citations`, `source_link_for_chunk` with `#page=N` fragments; TC-CV-01 through TC-CV-03
- **3.4.14** Verification agents: six-agent pipeline with fail-closed behavior; TC-G-01 through TC-G-04
- **3.4.15** Explanation: deterministic card summarizer + LLM service with Redis cache, CJK strip for vi/en, `question_focus` follow-up anchoring; TC-CS-01 through TC-CS-10 (Table 4.12)
- **3.4.16** Chat orchestration: language auto-detect, parallel question planner + intake, clinical state, multi-question SSE, missing-field gate; TC-LG/QP/MF/CH series (Tables 4.13, 4.18–4.20)
- **3.4.17** Governance: diff engine, status transitions, role enforcement, chat audit search; TC-AD-01 through TC-AD-08 (Table 4.15); TC-AD-09 in Table 4.15 only
- **3.4.18** Auth: JWT + API key + cookie, RBAC, rate limiting, PHI echo prevention
- **3.4.19** Chat persistence and audit: PostgreSQL conversations, drafts, `search_chat_audit_events`; TC-AU-01 through TC-AU-02 (Table 4.21)

Section 3.5 documented all 19 API route modules registered under `/api/v1`. Sections 3.6–3.10 cover storage design (PostgreSQL governance catalogs, Redis cache, ChromaDB, Neo4j, S3), interface design (doctor dashboard, admin portal), deployment (Docker Compose, Nginx), and security (JWT, RBAC, threat model). Chapter 4 maps this design to concrete implementation, pipelines, and the full test case suite.