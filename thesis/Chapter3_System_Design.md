# CHAPTER 3: SYSTEM DESIGN

<link rel="stylesheet" href="figures/thesis-figures.css">

Chapter 3 specifies requirements, architecture, data models, and module boundaries. Purpose, scope, thesis statement, and offline/online approach are in Chapter 1 (Section 1.2). Theory is in Chapter 2; implementation and results are in Chapters 4 and 5.

## 3.1. System Requirements

Heart failure treatment is complex. Clinicians must track four pillars of guideline-directed medical therapy (GDMT), watch for dangerous drug combinations, adjust doses for kidney function, and explain decisions clearly to patients. Many chatbot-style tools can write fluent text but cannot reliably enforce safety rules or show where a recommendation came from. This chapter specifies how the heart failure Clinical Decision Support System (CDSS) is designed to meet those needs end to end: from offline knowledge construction, through query-time reasoning and retrieval, to bilingual clinician interfaces and governance.

### 3.1.1. Functional Requirements

The system must perform a connected set of clinical and operational jobs. Each job maps to modules described later in this chapter. Together they address incomplete GDMT, hard-to-remember interaction rules, individualized dosing, evidence grounding, bilingual communication, and maintainable rule catalogs.

**Patient profile analysis.** When a doctor types a message such as "65-year-old male, EF 30%, eGFR 45, K+ 4.2, on bisoprolol 5mg," the system must turn that free text into a structured patient profile. The profile includes demographics, heart failure phenotype, laboratory values, vital signs, medications, allergies, red flags, and care context. Downstream safety checks depend on typed numbers with known units. A wrong potassium value could wrongly block or approve a mineralocorticoid receptor antagonist (MRA).

Intake uses a hybrid design. Fast pattern matching extracts numbers such as ejection fraction, eGFR, and potassium. A medication lexicon maps brand names and Vietnamese aliases to standard drug keys. Negation detection prevents "not on ACEi" from being read as "on ACEi." When the message is long or ambiguous, a language model fills gaps. Measured values from pattern matching always win over model guesses during merge. This keeps speed high on structured notes while still handling narrative chart summaries.

**GDMT treatment recommendations.** The system must assess how completely the patient receives the four GDMT classes (ACE inhibitor, ARB, or ARNI; beta blocker; MRA; and SGLT2 inhibitor), identify gaps, and propose changes grounded in ESC and AHA/ACC/HFSA guidelines. Each recommendation must carry a clear status such as start, continue, caution, or avoid, plus linked evidence for explanation.

This requirement is handled by a deterministic reasoning engine, not by the language model alone. Guideline concordance must be auditable and reproducible. The reasoning service reads approved policies and constraint rules from PostgreSQL and produces a structured recommendation object. GraphRAG retrieval supplies explanatory passages and citations for the narrative layer but never overrides a hard avoid status.

**Drug interaction checking.** Dangerous combinations such as ACE inhibitors with recent ARNI use, triple RAAS blockade, or combinations that raise potassium must be detected automatically. Interaction rules live in PostgreSQL as drug-set pairs with severity and management text. Free-text medication names are normalized so that "Entresto" and "sacubitril/valsartan" resolve to the same substance key. Interaction checking stays rule-driven because safety enforcement must be exact and testable.

**Medication dose calculation and dose safety.** Starting doses, target doses, renal adjustments, and titration schedules must be computed from patient characteristics. Dose rules are stored as flexible JSON objects so new titration patterns from FDA labels can be added without schema migrations. Separately, dose-safety warnings flag planned doses that exceed label maxima for the patient's renal band. Together these modules turn label prose into executable numeric guidance.

**Safety alerts and missing-field gates.** The system must surface renal impairment, hyperkalemia, hypotension, bradycardia, and missing critical labs before recommendations are finalized. Hard constraints block unsafe actions. Soft constraints emit warnings with monitoring instructions. If required labs are absent for the inferred intent, for example potassium before MRA evaluation, the pipeline stops and asks for clarification instead of guessing. Safety outcomes stream to the clinician before the conversational answer finishes generating.

**Evidence retrieval and verification.** For every recommendation turn that proceeds past missing-field checks, the system must assemble citation-ready evidence from drug labels and guidelines and verify that structured recommendations remain consistent with hard blocks and retrieved context. Verification agents audit safety, missing data, and evidence presence before narrative generation completes.

**Multilingual interface.** The system must support Vietnamese and English. Doctors can switch language without losing conversation context. Intake handles Vietnamese diacritics and bilingual medication names. Plain-language labels on recommendation cards are generated in the selected locale. Language switching re-renders presentation fields without re-running expensive retrieval or reasoning.

**Knowledge construction and governance.** The system must ingest FDA Structured Product Labels and heart-failure guidelines into governed catalogs, vector indexes, and graph stores. Clinical leads must be able to review draft rules, refine conditions, approve usable rules, and retire outdated ones without redeploying application code. Only approved executable tiers affect chat recommendations.

**Operational observability.** The system must expose health, readiness, and dependency probes so operators can see whether PostgreSQL, Redis, ChromaDB, Neo4j, object storage, and local LLM services are available. Audit events must record recommendation and governance actions for later review.

### 3.1.2. Non-Functional Requirements

**Performance.** Recommendation response time should stay below ten seconds for typical interactive queries on modest hospital hardware, with support for on the order of fifty concurrent users in a pilot deployment. Server-Sent Events (SSE) streaming shows partial results before the full conversational answer completes. Redis caching and bounded retrieval pools prevent latency from growing linearly with catalog size.

**Accuracy and safety.** Treatment recommendation accuracy should reach at least ninety percent against ESC-aligned evaluation cases measured on structured recommendation objects, not LLM prose. Hard safety constraints must never be silently missed. The system may emit precautionary alerts rather than approve therapy when kidney function or electrolytes are uncertain.

**Security and privacy.** Patient data must be protected in transit and at rest according to institutional hosting policy. JWT authentication, role-based access control, TLS termination, and audit logging address baseline healthcare security expectations. Local LLM inference via Ollama supports pilots that prefer not to send vignettes to external cloud APIs.

**Scalability and maintainability.** Guideline and label updates must not require application redeployment. JSONL pipeline artifacts, PostgreSQL governance tables, ChromaDB embeddings, and Neo4j imports can be refreshed independently. Draft, approved, and retired lifecycles keep automation accountable to clinical leads.

**Explainability.** Clinicians must see why a status appeared. Structured cards, verification badges, and evidence excerpts with openable source links provide that trail without forcing doctors to trust opaque model text.

## 3.2. Overall Architecture

### 3.2.1. Design Principles

Four principles shape every architectural choice.

First, **authority separation**. Deterministic PostgreSQL-backed rules are authoritative for GDMT statuses, hard contraindications, interactions, and dose plans. Large language models help with intake fallback, borderline document review during ingestion, query expansion, and narrative explanation. They do not become the sole source of clinical truth.

Second, **safety before prose**. Structured outcomes such as patient drafts, missing-field checks, recommendations, and verification verdicts stream to the clinician before answer tokens finish. This encodes Osheroff’s timing principle in protocol design.

Third, **governed knowledge**. Automated extraction produces drafts. Humans promote executable rules. Runtime loaders ignore unfinished refinement rows.

Fourth, **on-premise friendliness**. The stack runs as a modular monolith with Docker Compose, local embeddings, and local generation so hospitals can pilot without mandatory cloud LLM dependency.

### 3.2.2. Three-Tier Runtime Architecture

The interactive system follows a classic three-tier layout.

The **presentation tier** is built with React and Vite. It includes a doctor dashboard for clinical chat and evidence review, an admin portal for rule governance, and an API explorer for development. Clients subscribe to SSE streams and update the clinical panel as structured events arrive.

The **application tier** is a FastAPI modular monolith. It orchestrates hybrid intake, clinical-state construction, missing-field checks, GraphRAG retrieval, deterministic reasoning, dose calculation, dose-safety checks, verification agents, card summarization, and streaming answer generation. Async design allows GraphRAG prefetch to run in parallel with rule-engine evaluation on a thread pool, so long chat turns do not starve admin or health requests.

The **data tier** uses several stores because no single database fits every access pattern. PostgreSQL holds governable rule catalogs, chat history, patient drafts, users, and audit events. Redis caches session slices, constraint lookups, rate limits, and repeated LLM response hashes. ChromaDB stores dense embeddings for semantic retrieval. Neo4j holds entity-relationship graphs for multi-hop clinical facts. S3-compatible object storage holds raw downloads and processed JSONL artifacts for reproducible pipeline runs. Ollama hosts local embedding and generation models.

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
| **LocalStack** | S3 Emulator | 4566 | Artifact storage |

Together, these processes form one deployable stack: the browser talks to FastAPI and static assets; FastAPI talks to the data tier and Ollama; batch ingestion (Chapter 4) writes the same artifact layout that bootstrap loads at backend startup. Port values may change in production behind Nginx, but the responsibility split in the table remains the contract for operations and security review.

Standalone HTML: [`tables/chapters/table-3-1-components.html`](tables/chapters/table-3-1-components.html).

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-2-datastores.html" title="Figure 3.2 Data stores"></iframe>
  <figcaption><strong>Figure 3.2.</strong> Persistence layer: PostgreSQL governance catalogs, Neo4j, ChromaDB, and Redis. Appendix A, Figure A.5.</figcaption>
</figure>

A single backend container was chosen over microservices because deployment simplicity matters more than independent scaling at pilot load. Internal module boundaries preserve testability and allow future extraction of GraphRAG or ingestion workers if needed.

### 3.2.3. Dual-Plane Architecture: Offline Knowledge and Online Reasoning

The complete system is not only the chat path. It has two cooperating planes.

The **offline knowledge plane** acquires FDA DailyMed labels and heart-failure guidelines, filters clinically relevant sections, chunks text, extracts claims and rules, classifies safety tiers, and synchronizes artifacts into PostgreSQL, ChromaDB, and Neo4j. This plane answers the question: how does medical knowledge enter the system and stay maintainable?

The **online reasoning plane** accepts clinician chat, builds a patient profile, evaluates governed rules, retrieves evidence, verifies consistency, and streams bilingual explanations. This plane answers the question: how does the system help a clinician for this patient now?

Without the offline plane, chat would have nothing trustworthy to enforce or cite. Without the online plane, catalogs would remain inert databases. Chapter 4 details implementation of both planes; this chapter specifies their design contracts and interactions.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-3-dual-plane.html" title="Figure 3.3 Dual-plane architecture"></iframe>
  <figcaption><strong>Figure 3.3.</strong> Dual-plane architecture: offline ingestion and governance feed governed catalogs that the online chat path enforces; dashed return path marks clinician review feedback. Appendix A, Figure A.8.</figcaption>
</figure>

### 3.2.4. End-to-End Online Data Flow

When a physician sends a chat message, processing follows a fixed safety-first sequence.

Authentication establishes the caller’s role. The chat service ensures a conversation identifier exists and appends the user message to history. Hybrid intake extracts and merges patient facts with any prior draft for that conversation. Clinical-state construction normalizes units, derives missing eGFR when creatinine, age, and sex are available, and attaches risk flags and focus medication classes. The service emits `draft_ready`.

A missing-field checker then decides whether critical labs are absent for the inferred intent. If so, the pipeline emits `missing_check`, asks for clarification, and returns without producing a recommendation. Guessing electrolytes or ejection fraction is intentionally forbidden.

When required fields are present, GraphRAG prefetch starts asynchronously while deterministic recommendation building runs in a worker thread. Reasoning evaluates GDMT policies, constraints, interactions, dose plans, and dose-safety warnings. Verification agents await both the recommendation and GraphRAG context, then audit hard blocks, missing data, and evidence presence. Plain-language summaries and deterministic simplified card fields attach next. The service emits `recommendation_ready` and `verification_ready`.

Finally, the explanation layer streams `answer_delta` tokens grounded in the verified recommendation and retrieved evidence, then emits `done`. Cards and safety statuses remain authoritative; narrative text remains explanatory.

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

Inside the FastAPI application, major components and their responsibilities are as follows.

The auth component issues and validates JWT tokens and enforces roles. The chat orchestrator owns conversation lifecycle and SSE event ordering. Clinical intake extraction owns hybrid profile building. Clinical-state and risk-extraction helpers compress profiles into flags used by reasoning and retrieval. The missing-fields component owns fail-closed clarification gates. The reasoning service owns RecommendationResponse construction. GDMT policy, constraint, interaction, dose-calculation, and dose-safety modules supply the rule families reasoning depends on. Drug normalization maps surface strings to substance keys. GraphRAG and semantic-retrieval modules assemble evidence. Citation validation and verification agents audit consistency. Explanation modules provide card summarization and LLM narrative generation. Governance modules support admin approve, retire, and diff workflows. Datastore adapters isolate PostgreSQL, Redis, ChromaDB, Neo4j, and artifact bootstrap details from clinical logic.

This map is intentionally wider than a simple “chatbot plus database” sketch. Each component exists because a known failure mode appears when it is missing: without normalization, interactions miss brand names; without missing-field gates, rules evaluate incomplete labs; without verification, fluent prose can contradict hard blocks; without governance, extracted drafts become silent runtime hazards.

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

This section details each module’s contract, the actual function signatures and classes that implement it, and the test cases that verify correctness. All paths reference concrete implementation files under `backend/app/`.

### 3.4.1. Patient Profile Extraction Module

**Module:** `app/modules/clinical_intake_extraction/service.py`

**Responsibility:** Convert free-form clinician chat into a typed `PatientProfile`.

**Design:** Three-stage pipeline.

Stage 1 — Regex extraction (`extract_patient_from_message_sync`). Patterns capture numeric labs: EF (`r”EF[:\s]*(\d+)”`), eGFR (`r”eGFR[:\s]*(\d+)”`), potassium (`r”K\+|kali[:\s]*(\d+\.?\d*)”`), SBP (`r”(?:Huyết áp|SBP|BP)[:\s/]*(\d+)”`), HR (`r”(?:mạch|HR)[:\s]*/?(\d+)”`), weight, and INR. A medication lexicon maps strings including Vietnamese aliases and brand names to standard drug keys using longest-token-first preference to prevent substring errors. Negation detection (phrases “no,” “not,” “denies,” Vietnamese “không”) suppresses false positives. Unit normalization converts related lab expressions to canonical forms (e.g., mg/dL → mmol/L for potassium) and preserves raw source spans for audit.

Stage 2 — Semantic matching (`semantic.py`). Embedding-based catalog matching for brand names not covered by the static lexicon, with thread-safe caching via a Lock-based cache.

Stage 3 — Selective LLM merge (`_call_llm_extractor`). Runs only when heuristics detect low confidence: long narratives, conflicting cues, or ambiguous intake. Merge prefers regex-sourced numeric labs over model guesses — an explicit clinical epistemology encoded in code: instrument-like numbers beat probabilistic guesses. Prompt injection defense (`_sanitize_llm_input()`) strips 13 attack patterns and normalizes Unicode to NFKC form before LLM dispatch.

**Output:** `PatientProfile` (Section 3.4.4) rich enough for downstream rule evaluation, traceable to the words the clinician typed.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-I-01 | Vietnamese vitals/labs extraction — EF 32%, eGFR 78, K+ 4.4, SBP 118, HR 74; brand-name medication “metoprolol 25 mg bid” parsed with dose_unit and frequency |
| TC-I-02 | Negation prevents false positives — “no CKD”, “not on spironolactone” do not create active conditions; NKDA → “no known drug allergies” |
| TC-I-03 | Brand-name resolution — Entresto → sacubitril/valsartan, Farxiga → dapagliflozin |
| TC-I-04 | Acute red flag detection — “active bleeding today” → red_flag status=present |
| TC-I-05 | LLM skipped when required fields complete — `_call_llm_extractor` never invoked |
| TC-I-06 | LLM enriches when confidence low — full_name, age, sex, weight_kg added from LLM response |

**Implementation file:** `backend/app/tests/test_clinical_intake_extraction.py`

---

### 3.4.2. Clinical Normalization Module

**Module:** `app/modules/clinical_normalization/service.py`

**Responsibility:** Classify patient observations into clinical status bands used by constraint matching.

**Design:** Pure functions — no side effects, no external calls. All are individually unit-testable.

| Function | Input | Output bands |
|---|---|---|
| `classify_hf_type(lvef)` | LVEF % | `HFrEF` ≤40, `HFmrEF` 41–49, `HFpEF` ≥50, `unknown` |
| `classify_renal_status(egfr)` | eGFR mL/min/1.73m² | `kidney_failure` <15, `severely_reduced` 15–29, `moderately_reduced` 30–44, `mildly_reduced` 45–59, `preserved` ≥60, `missing` |
| `classify_potassium_status(k)` | K⁺ mmol/L | `low` <3.5, `normal` 3.5–5.0, `elevated` 5.0–5.3, `high` ≥5.3, `missing` |
| `classify_bp_status(sbp)` | SBP mmHg | `hypotension` <90, `low` 90–99, `acceptable` 100–130, `elevated` >130, `missing` |
| `classify_hr_status(hr)` | HR bpm | `bradycardia` <60, `acceptable` ≤100, `tachycardia` >100, `missing` |
| `detect_polypharmacy(meds)` | medication list | `True` if ≥5 medications |
| `normalize_patient(patient)` | `PatientProfile` | `NormalizedPatientProfile` with normalized comorbidities, observations dict |

Whitespace normalization handles trailing spaces and mixed casing in comorbidity strings (“ Chronic_Kidney Disease “ → “chronic kidney disease”).

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-N-01 | HF type thresholds — LVEF 40→HFrEF, 45→HFmrEF, 55→HFpEF, None→unknown |
| TC-N-02 | Renal status bands — eGFR 12→kidney_failure, 28→severely_reduced, 38→moderately_reduced, 55→mildly_reduced, 90→preserved, None→missing |
| TC-N-03 | Potassium status — K+ 3.2→low, 4.9→normal, 5.2→elevated, 5.5→high |
| TC-N-04 | BP and HR status classification per thresholds above |
| TC-N-05 | Polypharmacy — 5+ medications → True, fewer → False |
| TC-N-06 | Comorbidity normalization — “ Chronic_Kidney Disease “ → “chronic kidney disease” |

**Implementation file:** `backend/app/tests/test_clinical_normalization.py`

---

### 3.4.3. Risk Extraction Module

**Module:** `app/modules/risk_extraction/service.py`

**Responsibility:** Derive binary risk flags from a normalized patient profile. Flags become inputs to constraint matching.

**Design:** `extract_risks(profile: NormalizedPatientProfile) → list[RiskFlag]`.

Flags include:

| Flag | Trigger condition |
|------|-------------------|
| `renal_impairment` | renal_status in {kidney_failure, severely_reduced, moderately_reduced} |
| `hyperkalemia` | potassium_status in {elevated, high} |
| `hypotension` | bp_status in {hypotension, low} |
| `bradycardia` | hr_status in {bradycardia} |
| `polypharmacy` | ≥5 current medications |
| `diabetes` | “diabetes” in normalized comorbidities |
| `ckd_history` | “chronic kidney disease” in comorbidities, even when eGFR not reduced |
| `missing_egfr` | eGFR not provided |
| `missing_potassium` | potassium not provided |
| `missing_lvef` | LVEF not provided |
| `missing_sbp` | SBP not provided |
| `missing_heart_rate` | HR not provided |

Separating risk derivation from rule evaluation keeps both testable in isolation.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-R-01 | Core risks — patient with egfr=28, k=5.6, sbp=88, hr=55, 5 meds → renal_impairment, hyperkalemia, hypotension, bradycardia, polypharmacy, diabetes all present |
| TC-R-02 | Missing LVEF → missing_lvef flag |
| TC-R-03 | Missing labs do not create false renal/hyperK risks |
| TC-R-04 | CKD history preserved when eGFR not reduced — ckd_history set, renal_impairment absent |

**Implementation file:** `backend/app/tests/test_risk_extraction.py`

---

### 3.4.4. Patient Schema Module

**Module:** `app/schemas/patient.py` — class `PatientProfile`

**Responsibility:** The canonical input schema for all downstream clinical modules. The model uses Pydantic `model_validator` to accept two payload shapes.

**Legacy flat payload:**

```python
PatientProfile(
    case_id=”CASE_001”,
    lvef=30, egfr=28, potassium=5.6,
    systolic_bp=88, heart_rate=55,
    comorbidities=[“CKD”],
    current_medications=[“spironolactone”],
    allergies=[“penicillin”],
)
```

**Nested domain payload:**

```python
PatientProfile(
    patient_identity={“case_id”: “CASE_NESTED”, “full_name”: “Nguyen Van A”},
    demographics={“age”: 68, “sex”: “male”},
    heart_failure_profile={“lvef”: {“value”: 32, “unit”: “%”}, “nyha_class”: “III”},
    labs={“egfr”: {“value”: 35}, “potassium”: {“value”: 4.9}},
    vitals={“systolic_bp”: {“value”: 105}, “heart_rate”: {“value”: 72}},
    conditions=[{“name”: “Diabetes”}],
    medications=[{“name”: “dapagliflozin”, “drug_class”: “SGLT2i”}],
)
```

Computed properties (`case_id`, `lvef`, `egfr`, `potassium`, `systolic_bp`, `heart_rate`, `weight_kg`, `comorbidities`, `current_medications`, `allergies`) normalize both shapes to flat values. Physiological range validation rejects impossible values (LVEF 0–100%, HR 20–300, SBP 40–300, K 1.0–10.0). `legacy_summary()` provides backward compatibility for older callers.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-S-01 | Legacy flat payload — all fields map correctly via computed properties |
| TC-S-02 | Nested domain payload — patient_identity.full_name, demographics, labs, vitals, conditions parsed |

**Implementation file:** `backend/app/tests/test_patient_schema.py`

---

### 3.4.5. Drug Normalization Module

**Module:** `app/modules/drug_normalization/service.py`

**Responsibility:** Resolve brand names, salts, and bilingual aliases to canonical pipeline IDs used by interaction and GDMT catalogs.

**Functions:**

- `normalize_drug_name(name: str) → str` — canonical key
- `expand_drug_search_terms(name: str) → set[str]` — includes brand + generic forms
- `resolve_pipeline_drug_id(name: str) → str | None` — primary brand-to-generic resolver

Examples: `Jardiance` → `empagliflozin`; `Entresto` → `sacubitril_and_valsartan`; `dapagliflozin` → `dapagliflozin`.

Without normalization, interaction rules written against substance identifiers would miss free-text mentions. The scraper-side version in `scraper/process/drug_normalization.py` is used during the ingestion pipeline; the runtime version in `app/modules/` serves query-time normalization.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-D-01 | Brand → pipeline ID — Jardiance→empagliflozin, entresto→sacubitril_and_valsartan |
| TC-D-02 | Search term expansion includes both brand and generic names |
| TC-D-03 | Chunk claim matching — document_id + section + text match returns matched chunk |
| TC-D-04 | Recommendation evidence enrichment uses constraint chunk_ids from `enrich_recommendation_evidence` |
| TC-D-05 | Context prioritization — `prioritize_context_chunks` ranks linked chunks above generic |

**Implementation files:** `backend/app/tests/test_drug_normalization_and_evidence_linking.py`, `scraper/process/drug_normalization.py`

---

### 3.4.6. Constraint Builder Module

**Module:** `app/modules/constraint_builder/service.py`

**Responsibility:** Evaluate approved constraint rules against the patient profile and risk flags to produce a set of `(target_drug_class, action)` constraints.

**Design:**

```python
load_constraint_rules() → list[dict]        # cached TTL (5 min), stale-on-DB-error
build_constraints(profile, risks) → list[Constraint]  # severity_any pair matching
invalidate_constraint_cache() → None
```

Constraint rules carry: `constraint_id`, `target_drug_class`, `action` (avoid/caution), `reason`, `risk_names` (list), `severity_any` (list), `evidence_ref`, `clinical_sources`, `metadata`. Matching uses AND across `risk_names` and OR across `severity_any`: a rule fires when every risk in `risk_names` is present AND at least one severity in `severity_any` matches.

**Cache design:** TTL cache with stale-on-DB-error fallback. When the database is unavailable, the last successful cache remains served rather than returning an empty list — fail-stale not fail-empty. Cache invalidation occurs on admin approve/retire operations via Redis TTL.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-C-01 | Rules loaded from PostgreSQL — list returned with constraint_id on each |
| TC-C-02 | TTL cache — repeated calls produce single DB read |
| TC-C-03 | Stale cache served on DB error — last good cache returned, not empty |
| TC-C-04 | Empty cache on fresh DB error — no prior cache → empty list returned |
| TC-C-05 | MRA hard constraint — eGFR 25 + K+ 4.8 → (“MRA”, “avoid”) |
| TC-C-06 | RAAS caution — SBP 96 + K+ 5.2 → (“ARNI/ACEi/ARB”, “caution”) |
| TC-C-07 | Beta blocker caution — HR 55 → (“beta_blocker”, “caution”) |
| TC-C-08 | No constraints for clean case — all labs normal → empty set |

**Implementation file:** `backend/app/tests/test_constraint_builder.py`

---

### 3.4.7. Dose Safety Module

**Module:** `app/modules/dose_safety/evaluator.py`, `app/modules/dose_safety/rule_loader.py`

**Responsibility:** Flag planned doses that exceed label-derived maxima for the patient’s current renal status.

**Design:**

```python
evaluate_dose_safety_warnings(patient, rules) → list[MedicationSafetyWarning]
load_executable_dose_safety_warnings() → list[DoseSafetyWarning]
```

Each warning has a `warning_id`, a `target_medications` list (drug keys), a condition evaluator, and severity rules. Condition operators: `always`, `missing`, `present`, `lt`, `lte`, `gt`, `gte`, `missing_or_lt`, `missing_or_lte`. Severity resolution picks the maximum applicable severity from a priority chain (critical > high > moderate > low).

Warning IDs include:

| warning_id | Trigger |
|------------|---------|
| `dose_digoxin_renal_review` | digoxin + reduced renal function |
| `dose_mra_renal_potassium_review` | MRA (spironolactone/eplerenone) + eGFR <45 or K⁺ ≥5.0 |
| `dose_loop_diuretic_lab_monitoring` | loop diuretic + CKD comorbidity |

When PostgreSQL is unavailable at runtime, `load_executable_dose_safety_warnings()` returns an empty list — no fabricated warnings.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-DS-01 | Digoxin + MRA + loop diuretic → all three warning IDs present |
| TC-DS-02 | Digoxin renal review has severity = critical |
| TC-DS-03 | PostgreSQL unavailable → empty warning list (no crash) |
| TC-DS-04 | RAAS dual therapy (lisinopril + losartan) → interaction warning |
| TC-DS-05 | RAAS + MRA hyperkalemia monitoring → interaction warning |
| TC-DS-06 | Anticoagulant + antiplatelet → bleeding interaction warning |
| TC-DS-07 | Recommendation includes dose + interaction warnings — `dose_mra_renal_potassium_review` attached to MRA recommendation |

**Implementation files:** `backend/app/tests/test_dose_safety_evaluator.py`, `backend/app/tests/test_medication_safety.py`

---

### 3.4.8. Medication Safety — Interaction Checking Module

**Module:** `app/modules/interaction_checking/`, `app/api/routes/medication_safety.py`

**Responsibility:** Detect drug-drug interactions at query time via `/interaction/check` and `/dose/check` API endpoints.

**Design:** Interaction rules store drug-set pairs with severity and management text. The evaluator compares the patient’s normalized medication list against approved interaction pairs. Normalization (Section 3.4.5) ensures brand names are resolved before comparison.

Interaction warning IDs include:

| warning_id | Description |
|------------|-------------|
| `interaction_acei_arb_combination` | ACE inhibitor + ARB → triple RAAS blockade |
| `interaction_raasi_mra_hyperkalemia_monitoring` | RAAS inhibitor + MRA → requires potassium monitoring |
| `interaction_anticoagulant_antiplatelet_bleeding` | Anticoagulant + antiplatelet → bleeding risk |

Dose checking (`/dose/check`) evaluates dose-safety rules independently of GDMT reasoning, supporting standalone medication review.

**Key test cases:** See TC-DS-04 through TC-DS-07 in Section 3.4.7.

---

### 3.4.9. Reasoning Service Module

**Module:** `app/modules/reasoning/service.py`

**Responsibility:** Produce the authoritative `RecommendationResponse` with no LLM in the critical path.

**Design:**

```python
build_recommendation(request: RecommendationRequest) → RecommendationResponse
```

Pipeline steps (all synchronous except where noted):

1. Normalize patient (`normalize_patient`)
2. Extract risks (`extract_risks`)
3. Build constraints (`build_constraints`) — thread-offloaded via `asyncio.to_thread`
4. Check dose safety (`evaluate_dose_safety_warnings`)
5. Check interactions (`check_interactions`)
6. Load GDMT policies (`gdmt_policy.policy_loader`)
7. Generate per-policy `MedicationRecommendation` (start/continue/caution/avoid/review)
8. Build dose plans (`dose_calculation.build_dose_plans`)
9. Compute `overall_status`: **blocked** if any hard avoid constraint or critical warning; **approved_with_warnings** if any risks or warnings; **approved** otherwise

**Invariants (never violated):**

- LLM output never modifies avoid statuses
- Hard-block rules override permissive retrieved prose
- No fabricated milligram strength when dose catalog row is incomplete

**Governance version string** (`constraint_rules_version`, `dose_rules_version`, `interaction_rules_version`) records which catalog generation produced the result, enabling audit trail reconstruction.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-REC-01 | Week 3 blocked — eGFR 28, K+ 5.4, SBP 92, HR 58 → overall_status=blocked; renal_impairment+hyperkalemia+hypotension+bradycardia risks; MRA avoid; SGLT2 consider_with_caution with constraint_ids |
| TC-REC-02 | Clean HFrEF — eGFR 78, K+ 4.4, SBP 118, HR 74 → overall_status=approved; no risks; all GDMT classes status=consider |
| TC-REC-03 | HFpEF case — LVEF 55 → HFpEF type; all GDMT classes status=review |
| TC-REC-04 | Missing safety data — no egfr/potassium/hr → approved_with_warnings; missing_egfr+missing_potassium+missing_heart_rate risks; all GDMT classes become consider_with_caution |

**Implementation file:** `backend/app/tests/test_recommendation.py`

---

### 3.4.10. Dose Calculation Module

**Module:** `app/modules/dose_calculation/`

**Responsibility:** Personalize starting dose, target dose, renal bands, and titration schedules from FDA label JSONB rules.

**Design:**

```python
build_dose_plans(patient, clinical_state) → list[DosePlan]
dose_source_version() → str
```

Rules are stored as JSONB in PostgreSQL governance catalogs. The evaluator resolves the drug key, selects the matching eGFR band, and returns a `DosePlan` with start dose, target dose, titration steps, and rationale. When a catalog row is incomplete, the module returns no fabricated number — an explicit honesty contract.

`dose_source_version()` returns the loaded artifact generation timestamp, included in the `RecommendationResponse` for traceability.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-DC-01 | Dose plans built from current medications — enalapril plan_id returned |
| TC-DC-02 | Recommendation includes label dose plans and `dose_rules_version` |

**Implementation file:** `backend/app/tests/test_dose_calculation_integration.py`

---

### 3.4.11. GraphRAG and Evidence Retrieval Module

**Module:** `app/modules/graphrag/service.py`, `app/modules/evidence_filter.py`, `app/modules/evidence_quality.py`

**Responsibility:** Assemble citation-ready evidence from ChromaDB, Neo4j, and BM25 into ranked context for verification and explanation.

**Design:** Hybrid retrieval with four complementary signals:

1. **HyDE expansion** (`hyde_expansion.py`) — generates a hypothetical evidence passage from a short query, then embeds that passage. Bridges vocabulary gaps between clinical shorthand and label prose.
2. **Dense retrieval** — ChromaDB nearest-neighbor search using BGE-M3 embeddings
3. **Sparse retrieval** — BM25 keyword search favoring exact drug names and regulatory phrases
4. **Graph retrieval** — Neo4j neighborhood traversal seeded by patient medication and condition entities, merging multi-hop relationships

**Fusion:** Reciprocal Rank Fusion (RRF) merges ranked lists without brittle hand-tuned score calibration.

**Evidence filtering** (`filter_evidence_chunks`, `evidence_filter.py`):

- `passes_negative_evidence_filter()` — drops chunks with low quality scores, irrelevant sections (e.g., “CONTACT”, “PACKAGING”), or generic wellness text lacking patient-specific terms
- `patient_profile_entities()` — extracts entities from the patient profile (medications, abnormal labs) to score relevance
- `enrich_evidence_chunk()` — annotates each chunk with patient-specific entities and quality signals
- Constraint-pinned chunks (`metadata.constraint_pinned=True`) are always retained regardless of score
- **Backfill behavior**: when fewer than `evidence_negative_filter_min_results` chunks remain, fallback chunks are included to meet the top_k floor

Post-fusion, clinical entity boosting elevates passages mentioning the patient’s current medications.

**Outputs:** ranked `evidence_chunks` with scores, `graph_facts` with source links, `retrieval_sources` list (`local_chunks`, `local_relationships`).

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-E-01 | Patient entities include medications and abnormal labs |
| TC-E-02 | Negative filter drops low-quality/noisy chunks — score threshold + irrelevant section |
| TC-E-03 | Constraint-pinned chunks always kept regardless of score |
| TC-E-04 | Backfill when too few results — fallback chunks added to meet top_k |

**Implementation file:** `backend/app/tests/test_evidence_filter.py`

---

### 3.4.12. Evidence Linking and Citation Module

**Module:** `app/modules/evidence_linking/service.py`

**Responsibility:** Map recommendation constraint references to retrieved evidence chunks and prioritize context for display.

**Design:**

- `find_chunk_for_claim(claim, chunks)` — matches on `document_id` + `section` + `text` substring. Returns the matched chunk with its `chunk_id`.
- `enrich_recommendation_evidence(response)` — attaches constraint `evidence_ref` chunk IDs to each `MedicationRecommendation`. The recommendation’s `evidence` field then contains the full chunk text and metadata.
- `prioritize_context_chunks(context, linked_chunk_ids)` — reorders the evidence chunk list so chunks matching recommendation evidence links appear first. Linked chunks surface above generic high-score chunks.

Citation helpers construct source links with PDF page fragments: `source_url + “#page=” + str(page)`. This enables clinicians to open the exact citation location in the original document.

**Key test cases:** TC-D-03 through TC-D-05 (Section 3.4.5).

**Implementation file:** `backend/app/tests/test_drug_normalization_and_evidence_linking.py`

---

### 3.4.13. Citation Validation Module

**Module:** `app/modules/citation_validation/service.py`

**Responsibility:** Verify that cited evidence is actually present in the retrieved context, and construct clickable source links.

**Design:**

```python
validate_citations(recommendation, context) → CitationValidationResult
source_link_for_chunk(chunk) → str  # appends #page=N
```

`validate_citations()` cross-checks each constraint’s `evidence_ref` against the retrieved `evidence_chunks`. It produces:
- `supports` — list of validated citations with evidence verdict (`supported`/`weakly_supported`/`unsupported`) and confidence score
- `status` — `strong` (all cited, high confidence), `weak` (some cited, mixed confidence), `missing` (none cited)

`source_link_for_chunk()` constructs `https://example.org/hf.pdf#page=42` from chunk metadata.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-CV-01 | Citation with matching chunk → supported verdict with evidence_refs |
| TC-CV-02 | Source link includes PDF page fragment — `#page=42` appended |
| TC-CV-03 | Confidence score > 0 for supported items |

**Implementation file:** `backend/app/tests/test_citation_validation.py`

---

### 3.4.14. GraphRAG Verification Agents Module

**Module:** `app/modules/verification_agents/` (six agent implementations)

**Responsibility:** Independent cross-checks of the deterministic recommendation before narrative generation.

**Design:** Six agents run after the recommendation and GraphRAG context are both available:

| Agent | Role | Fail-closed behavior |
|-------|------|---------------------|
| `safety_agent` | Verifies hard avoid constraints are respected | Fails the verdict if hard block fires while narrative sounds permissive |
| `missing_data_agent` | Checks required labs are present for the inferred intent | Warns if critical labs remain unset |
| `evidence_agent` | Confirms evidence was retrieved for cited claims | Fails if no usable chunks returned |
| `guideline_alignment_agent` | Checks recommendation against guideline policy | Passes if within guideline bounds |
| `citation_validator_agent` | Validates citation-to-chunk linkage | Sets citation status (strong/weak/missing) |
| `final_reviewer_agent` | Aggregates all agent verdicts | Sets final verdict: `pass`, `warning`, or `fail` |

The join point is at verification: agents await both the `RecommendationResponse` object and the `GraphRAGContextResponse` before streaming safety outcomes. Fail-closed means any `fail` verdict cascades to `final_verdict = “fail”` regardless of other agents passing.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-G-01 | GraphRAG context returns graph_facts + evidence_chunks + retrieval_sources |
| TC-G-02 | All 6 agents produce results on a typical HFrEF case |
| TC-G-03 | Final verdict is one of pass/warning/fail |
| TC-G-04 | Citation validation status is strong/weak/missing |

**Implementation file:** `backend/app/tests/test_graphrag_agents.py`

---

### 3.4.15. Explanation and Card Summarizer Module

**Module:** `app/modules/explanation/card_summarizer.py`, `app/modules/explanation/llm_service.py`

**Responsibility:** Produce bilingual plain-language recommendation summaries — deterministic and LLM-assisted.

**Design:** Two layers.

**Layer 1 — Deterministic card summarizer** (`card_summarizer.py`):

```python
deterministic_card_summary(item, language) → str
deterministic_card_details(item, language) → CardDetails
apply_deterministic_summaries(response, language) → RecommendationResponse
```

Drug class codes map to readable phrases. Status codes map to badge text. Language toggling regenerates labels in under two seconds without re-running GraphRAG or reasoning. `merge_summaries()` combines LLM-generated per-item summaries with deterministic fallbacks: if the LLM does not provide a summary for a given drug class, the deterministic version is used instead.

**Layer 2 — LLM answer service** (`llm_service.py`):

```python
attach_plain_language_summaries(response, language) → RecommendationResponse
_compact_recommendation(request) → dict
fallback_answer(request) → str
```

When enabled, an LLM call generates natural language summaries per drug class using a structured JSON response validated by Pydantic. Responses are cached in Redis (24 h TTL) keyed by recommendation hash. When the LLM is disabled or the cache misses, `fallback_answer()` prefers `plain_language_summary` over generated text — the structured field is authoritative.

The system prompt (`CLINICAL_EXPLANATION_SYSTEM_PROMPT`) instructs the model to: cite plain-language summaries, not soft-pedal hard blocks, acknowledge uncertainty, and defer final treatment decisions to the clinician.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-CS-01 | Vietnamese deterministic summary contains ARNI/RAAS — no English “No clear current” text |
| TC-CS-02 | Vietnamese card details next_steps are plain language, not clinical English |
| TC-CS-03 | Unknown drug classes ignored in LLM summary map — not included in output |
| TC-CS-04 | Merge falls back per-item — missing LLM summary for one class, deterministic used for that class |
| TC-CS-05 | Fallback answer prefers plain_language_summary over generated text |
| TC-CS-06 | Compact recommendation includes plain_language_summary |
| TC-CS-07 | LLM disabled → deterministic text used, no LLM call made |
| TC-CS-08 | LLM JSON response correctly mapped to drug class summaries |

**Implementation file:** `backend/app/tests/test_card_summarizer.py`

---

### 3.4.16. Chat Orchestration and SSE Module

**Module:** `app/modules/chat/service.py` — `stream_chat()`

**Responsibility:** Orchestrate the full chat pipeline from clinician message to SSE stream, with patient draft persistence and multi-turn conversation continuity.

**Design:** `stream_chat()` is the primary entry point. Processing follows a fixed safety-first sequence:

1. **Authenticate** — validate JWT, establish role
2. **Ensure conversation** — create or append to `chat_conversations`
3. **Hybrid intake** — call `extract_patient_from_message_sync` with conversation history context
4. **Merge draft** — combine extracted fields with prior draft for this conversation; save and emit `draft_ready`
5. **Missing-field gate** — if critical labs are absent for inferred intent → emit `missing_check` with clarification prompt; **do not** produce a recommendation
6. **Parallel execution** (asyncio):
   - `create_task` — GraphRAG prefetch runs async
   - `to_thread` — PostgreSQL rule evaluation runs in worker thread (keeps event loop free)
7. **Verification** — fork-join point; await both recommendation and GraphRAG context
8. **Summarization** — deterministic card labels + LLM plain-language summaries
9. **Streaming** — emit `recommendation_ready`, `verification_ready`, `answer_delta` tokens, then `done`

**SSE event contract:**

| Event | Payload | When |
|-------|---------|------|
| `status` | stage name | Progress updates |
| `draft_ready` | `PatientDraft` | After intake merge |
| `missing_check` | `MissingFieldCheck` | When required labs absent |
| `recommendation_ready` | `RecommendationResponse` | After reasoning |
| `verification_ready` | `VerificationResult` | After agents |
| `answer_delta` | token string | LLM streaming |
| `done` | full response snapshot | End of turn |

**Multi-turn continuity:** Conversation history contributes previously stated facts to intake extraction, so clinicians do not retype lab values on every message. Patient drafts are persisted in PostgreSQL (Redis cache, 30 min TTL) for reload across sessions.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-CH-01 | Missing systolic_bp → status=needs_more_information with missing_check event listing systolic_bp |
| TC-CH-02 | SSE stream contains draft_ready + missing_check + answer_delta + done events |
| TC-CH-03 | Nested patient payload fully merged — weight_kg 70 from nested payload |
| TC-CH-04 | Chat uses intake extractor — Entresto → sacubitril/valsartan, no false CKD |
| TC-CH-05 | Chat history persisted — GET /chat/{id}/history returns 2 messages |

**Implementation file:** `backend/app/tests/test_chat.py`

---

### 3.4.17. Governance and Admin Module

**Module:** `app/modules/governance/`, `app/api/routes/admin/` (6 admin route modules)

**Responsibility:** Human-in-the-loop review and lifecycle management of clinical decision rules.

**Design:**

- **Diff engine** (`governance/diff.py`): `diff_field_map(before, after, field_list) → list[Change]`. Each catalog family has a field list: `CONSTRAINT_DIFF_FIELDS` (9 fields), `DOSE_DIFF_FIELDS` (8), `INTERACTION_DIFF_FIELDS` (9), `GDMT_DIFF_FIELDS` (8), `DOSE_SAFETY_DIFF_FIELDS` (8). Changes are typed as `added`, `removed`, or `modified` with field path.
- **Status transitions:** `draft` → `approved` → `retired`. Invalid transitions return HTTP 400.
- **Role enforcement:** `clinical_lead` can approve and retire rules; `viewer` can read active rules only; `admin` has full access. Bulk approve helpers exist for trusted batches, still under role checks.

Admin routes (registered under `/admin/`):

| Route | Method | Role required | Description |
|-------|--------|-------------|-------------|
| `/admin/constraints` | GET | clinical_lead/admin | List constraint rules by status |
| `/admin/constraints/rules/{id}` | PATCH | clinical_lead/admin | Approve/retire a rule |
| `/admin/evidence/search` | GET | admin | Evidence passage search |
| `/admin/users` | GET/POST | admin | User management |
| `/admin/dose_rules` | GET | clinical_lead/admin | List dose rules |
| `/admin/interaction_rules` | GET | clinical_lead/admin | List interaction rules |
| `/admin/gdmt_policies` | GET | clinical_lead/admin | List GDMT policies |
| `/admin/audit` | GET | clinical_lead/admin | Audit log |

Cache invalidation (`invalidate_constraint_cache()`) runs synchronously on approve/retire operations to ensure the next chat request sees updated rules.

**Key test cases:**

| TC | Description |
|----|-------------|
| TC-AD-01 | Admin routes require JWT — 401 without token |
| TC-AD-02 | Clinical lead can access active rules — 200 with list |
| TC-AD-03 | Viewer role forbidden — 403 on admin constraint routes |
| TC-AD-04 | Admin role required for user management — 403 for clinical_lead |
| TC-AD-05 | JWT bearer token works for clinical routes without API key |
| TC-AD-06 | Rule status approve/retire requires clinical_lead role |
| TC-AD-07 | Invalid transition (draft → retired) → HTTP 400 |
| TC-AD-08 | Diff field map detects reason change, ignores unchanged fields |

**Implementation files:** `backend/app/tests/test_governance.py`, `backend/app/tests/test_admin_routes.py`

---

### 3.4.18. Auth and Security Module

**Module:** `app/core/jwt.py`, `app/core/passwords.py`, `app/core/middleware.py`

**Responsibility:** Authenticate clinicians and authorize governance operations.

**Design:**

- **JWT access tokens** (15-minute expiry): encode `sub` (user ID) and `roles` list. Validated on every protected route.
- **JWT session cookies**: cookie-based alternative to bearer token, cleared on logout.
- **API key**: `X-API-Key` header accepted for machine clients and tests.
- **Role-based access control** (RBAC): three roles — `clinical_lead` (chat + rule approval), `clinician`/`doctor` (chat only), `admin` (full access), `viewer` (read-only active catalogs).
- **Login rate limiting** via sliding window in `app/core/middleware.py` — blocks after N failed attempts within a time window.
- **PHI echo prevention**: validation error responses do not echo input strings that could contain PHI; only field names and structured error codes are returned.
- **Request ID propagation**: every request tagged with a unique ID propagated through logs and error responses.
- **Token revocation**: inactive users rejected even with a valid signature.

**Key test cases:** TC-AD-01 through TC-AD-05 (Section 3.4.17). Additional production hardening tests in `test_production_hardening.py` cover rate limiting on `/chat` and `/chat/stream`, Prometheus metrics, and degraded-dependency 503 responses.

**Implementation files:** `backend/app/tests/test_admin_routes.py`, `backend/app/tests/test_security_hardening.py`, `backend/app/tests/test_production_hardening.py`





Governance supports list, detail, diff, approve, retire, and history operations for constraint, dose, interaction, GDMT, and dose-safety catalogs. Clinical leads refine conditions that extraction could not fully encode. Bulk approve helpers may exist for trusted batches, still under role checks. Diff views help reviewers see what changed between pipeline runs before promotion.

### 3.4.11. Chat Persistence and Audit Modules

Conversations, messages, and patient drafts persist in PostgreSQL so history can be reloaded across sessions. Redis may cache hot drafts for latency. Audit events record missing-field stops, recommendation outcomes, and governance actions with timestamps and actor identity. The CDSS is still not an EHR system of record for the whole hospital chart, but conversation and recommendation audit trails are first-class design artifacts.

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

S3-compatible storage (LocalStack in development, AWS S3 in production) hosts two primary bucket families:

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
| `admin/users_router` | `/admin/users` | JWT (admin) | User management |

Legacy aliases mount `/api/auth/*` alongside versioned auth routes. A `/routes` endpoint catalogs all public routes for API explorer tooling.

### 3.5.1. Chat APIs

The primary clinician path is streaming chat at `POST /api/v1/chat/stream`. A non-streaming version exists at `POST /api/v1/chat`. History endpoints (`GET /api/v1/chat/{conversation_id}/history`) reload messages and drafts. Requests carry JWT credentials, message text, conversation identifier, optional pre-seeded patient fields, language preference, and optional attachments.

SSE event order is a hard API contract: status frames, `draft_ready`, `missing_check` when needed, then either early `done` or the sequence `recommendation_ready`, `verification_ready`, `answer_delta` tokens, and `done`. Clients must render GDMT grids from recommendation payloads, not from answer tokens.

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

Section 3.4 detailed 18 functional modules with actual function signatures and test case references:
- **3.4.1** Clinical intake: `extract_patient_from_message_sync` with three-stage regex→semantic→LLM pipeline; prompt injection defense; negation detection; TC-I-01 through TC-I-06
- **3.4.2** Normalization: pure classification functions `classify_hf_type`, `classify_renal_status`, `classify_potassium_status`, `classify_bp_status`, `classify_hr_status`, `detect_polypharmacy`; TC-N-01 through TC-N-06
- **3.4.3** Risk extraction: `extract_risks` producing 12 risk flags including `ckd_history` preservation invariant; TC-R-01 through TC-R-04
- **3.4.4** Patient schema: `PatientProfile` with Pydantic `model_validator` accepting legacy flat and nested domain payloads; TC-S-01 through TC-S-02
- **3.4.5** Drug normalization: `normalize_drug_name`, `expand_drug_search_terms`, `resolve_pipeline_drug_id`; TC-D-01 through TC-D-05
- **3.4.6** Constraint builder: `build_constraints` with TTL cache and stale-on-DB-error fallback; TC-C-01 through TC-C-08
- **3.4.7** Dose safety: `evaluate_dose_safety_warnings` with condition operators; TC-DS-01 through TC-DS-07
- **3.4.8** Interaction checking: `/dose/check` and `/interaction/check` endpoints
- **3.4.9** Reasoning service: `build_recommendation` with 9-step pipeline; no LLM in critical path; TC-REC-01 through TC-REC-04
- **3.4.10** Dose calculation: `build_dose_plans`, `dose_source_version`
- **3.4.11** GraphRAG: four-signal hybrid retrieval with RRF fusion and evidence filtering
- **3.4.12** Evidence linking: `enrich_recommendation_evidence`, `prioritize_context_chunks`
- **3.4.13** Citation validation: `validate_citations`, `source_link_for_chunk` with `#page=N` fragments; TC-CV-01 through TC-CV-03
- **3.4.14** Verification agents: six-agent pipeline with fail-closed behavior; TC-G-01 through TC-G-04
- **3.4.15** Explanation: deterministic card summarizer + LLM service with Redis cache; TC-CS-01 through TC-CS-08
- **3.4.16** Chat orchestration: `stream_chat` with SSE contract (7 event types); TC-CH-01 through TC-CH-05
- **3.4.17** Governance: diff engine, status transitions, role enforcement; TC-AD-01 through TC-AD-08
- **3.4.18** Auth: JWT + API key + cookie, RBAC, rate limiting, PHI echo prevention

Section 3.5 documented all 19 API route modules registered under `/api/v1`. Sections 3.6–3.10 cover storage design (PostgreSQL governance catalogs, Redis cache, ChromaDB, Neo4j, S3), interface design (doctor dashboard, admin portal), deployment (Docker Compose, Nginx), and security (JWT, RBAC, threat model). Chapter 4 maps this design to concrete implementation, pipelines, and the full test case suite.