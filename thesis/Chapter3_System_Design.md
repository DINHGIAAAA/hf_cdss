# CHAPTER 3: SYSTEM DESIGN

<link rel="stylesheet" href="figures/thesis-figures.css">

## 3.0 Research Purpose, Scope, and Approach

### 3.0.1 Purpose of the Study

The purpose of this study is to design, implement, and evaluate a Clinical Decision Support System specialized for heart failure that integrates a medical Knowledge Graph, hybrid GraphRAG retrieval, deterministic clinical rule engines, verification agents, and a locally hosted large language model. The system helps clinicians apply Guideline-Directed Medical Therapy more consistently and safely by transforming authoritative sources, including FDA DailyMed SPL/XML, ESC and AHA/ACC/HFSA clinical guidelines, and curated interaction knowledge, into governed, queryable artifacts that support both structured reasoning and evidence-grounded explanation.

Scientifically, the study pursues four interconnected objectives. First, it investigates how an automated knowledge-construction pipeline can extract constraint rules, dose rules, interaction rules, GDMT policies, and dose-safety warnings from heterogeneous medical documents with sufficient precision to populate PostgreSQL governance catalogs, ChromaDB vector indexes, and Neo4j graph stores. Second, it examines how hybrid retrieval, combining dense embedding search, BM25 sparse search, graph neighborhood traversal, HyDE query expansion, and Reciprocal Rank Fusion (RRF), can supply citation-ready context for heart-failure queries where neither lexical nor semantic retrieval alone is reliable [12]-[14]. Third, it evaluates whether separating deterministic recommendation logic from LLM-mediated narrative reduces hallucination risk while preserving conversational usability. Fourth, it measures end-to-end behavior on recommendation accuracy, latency, safety-alert sensitivity, bilingual usability, and clinician satisfaction using predefined success criteria developed before implementation (Chapter 5, Section 5.0).

Practically, the study delivers a working prototype for cardiologist-supervised use. The implementation targets automated ingestion of SPL and guideline content; conversion of free-text clinical chat into a structured patient profile via hybrid intake; personalized GDMT gap analysis governed by PostgreSQL-backed rules; enforcement of interaction, contraindication, renal, electrolyte, and dose-safety checks; parallel GraphRAG assembly of explanatory evidence; multi-agent verification; and streaming delivery of bilingual plain-language summaries through a React doctor dashboard using Server-Sent Events (SSE).

The study does not aim to replace electronic health record systems, automate prescribing without human approval, or manage acute decompensated heart failure requiring emergent intervention. Its purpose is to show that a hybrid CDSS can operationalize a substantial fraction of outpatient HFrEF GDMT knowledge in a form clinicians can interact with through chat, trust through deterministic safety tiers, and evaluate through transparent metrics. Methodologically, the study follows design-science research: articulate a grounded problem (Chapter 1), propose an artifact with testable claims, implement with reproducible engineering practices, and evaluate against predefined criteria using expert review and structured safety suites.

### 3.0.2 Scope and Delimitations

The primary clinical scope is HFrEF GDMT pharmacotherapy: ACE inhibitors, ARBs, ARNIs, evidence-based beta blockers, MRAs, and SGLT2 inhibitors, including initiation, uptitration, contraindication checking, and major interaction and dose-safety warnings. HFpEF, acute decompensated HF requiring intravenous vasoactives, device therapy, transplantation, and palliative pathways are largely out of scope. Knowledge sources center on FDA DailyMed SPL/XML, ESC and AHA/ACC/HFSA guidelines, and curated interaction knowledge in PostgreSQL. Full Vietnamese formulary integration is future work.

Patient data enter through chat-based intake rather than HL7/FHIR feeds. Recommendations are advisory: hard avoid constraints flag unsafe actions in structured outputs, but prescribing authority remains with the clinician. Deployment assumes local hosting with JWT authentication and Docker-based infrastructure. The doctor dashboard supports Vietnamese and English with context preserved across language toggles. Evaluation uses curated vignettes and structured safety suites, not prospective randomized trials.

### 3.0.3 Thesis Statement

The central claim is that a hybrid CDSS, coupling deterministic GDMT and safety rules with Knowledge Graph-augmented retrieval (GraphRAG) and locally hosted LLM explanation, can deliver accurate, timely, and bilingual heart-failure treatment support suitable for clinical workflow while keeping clinicians in the loop. Accuracy means guideline-concordance of structured recommendation objects on expert-reviewed cases. Timeliness means sub-10-second typical end-to-end latency. Safety means fail-closed behavior on hard contraindications in governed catalogs, supplemented by verification agents. The thesis rejects both unconstrained generative chat and rigid rule-only alerting without evidence-grounded explanation.

### 3.0.4 Knowledge Engineering Approach (Offline)

Knowledge engineering spans offline ingestion into synchronized stores. FDA DailyMed SPL XML labels and HF guideline documents are acquired into versioned object storage. A three-tier section filter retains clinically relevant content while minimizing LLM cost: keyword matching on high-precision headings, BGE-M3 semantic similarity scoring, and borderline LLM review only for ambiguous sections. Surviving text undergoes sentence-aware chunking, claim extraction, and safety classification into hard_block, usable_rules, and needs_condition_refinement tiers. Artifacts sync to PostgreSQL for governance, ChromaDB for vector search, and Neo4j for graph retrieval. PostgreSQL remains authoritative for executable rules; vector and graph stores enrich explanation without overriding hard blocks.

### 3.0.5 Query-Time Approach (Online)

At query time, hybrid intake converts free-text chat into a structured patient profile using regular expressions for labs and vitals, lexicons for medications and conditions with negation handling, and selective LLM parsing when deterministic confidence is low. The reasoning engine evaluates GDMT coverage, applies constraint and interaction rules, and computes dose plans synchronously from governed catalogs without depending on LLM generation for core statuses.

In parallel, GraphRAG assembles explanatory context. HyDE expands the query into a hypothetical evidence passage before embedding. Retrievers run in parallel: ChromaDB dense search, BM25 sparse search, and Neo4j neighborhood traversal seeded by profile-linked entities. Ranked lists fuse through RRF. Retrieved chunks feed verification agents and the explanation LLM with citation metadata.

A large language model (LLM) is a neural network trained on vast text to generate human-like language [18], [19]. Here the LLM is not the clinical authority. It parses ambiguous intake, expands queries via HyDE, and generates readable narrative conditioned on structured outputs and retrieved context. Verification agents check that hard avoid constraints are respected and that cited evidence was actually retrieved. Responses stream to the React dashboard over Server-Sent Events (SSE), a protocol that pushes structured safety cards to the browser before narrative text finishes generating.

### 3.0.6 Design Principle: LLM as Explanation Layer, Rules as Authority

Deterministic rules and governed catalogs are the authority for recommendation statuses, hard blocks, and dose calculations. Retrieved evidence is the authority for what passages may be cited. LLMs serve as interface and explanation only. They cannot override hard_block tiers or invent medications absent from rule-engine outputs. Clinicians receive structured cards first, followed by streaming explanation. Post-hoc review can trace each recommendation to PostgreSQL rule identifiers and each cited claim to retrieved chunk metadata. Section 3.2.1 restates these principles in the context of the full runtime architecture.

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

```
 Offline plane                         Online plane
 ┌──────────────────────┐              ┌──────────────────────────┐
 │ Acquire labels/PDFs  │              │ Chat + attachments       │
 │ Filter + chunk       │              │ Hybrid intake            │
 │ Extract + classify   │─────────────▶│ Reasoning + dose/safety  │
 │ Sync PG/Chroma/Neo4j │   catalogs   │ GraphRAG + verification  │
 │ Admin approve/retire │◀─────────────│ SSE cards + narrative    │
 └──────────────────────┘   feedback   └──────────────────────────┘
```

### 3.2.4. End-to-End Online Data Flow

When a physician sends a chat message, processing follows a fixed safety-first sequence.

Authentication establishes the caller’s role. The chat service ensures a conversation identifier exists and appends the user message to history. Hybrid intake extracts and merges patient facts with any prior draft for that conversation. Clinical-state construction normalizes units, derives missing eGFR when creatinine, age, and sex are available, and attaches risk flags and focus medication classes. The service emits `draft_ready`.

A missing-field checker then decides whether critical labs are absent for the inferred intent. If so, the pipeline emits `missing_check`, asks for clarification, and returns without producing a recommendation. Guessing electrolytes or ejection fraction is intentionally forbidden.

When required fields are present, GraphRAG prefetch starts asynchronously while deterministic recommendation building runs in a worker thread. Reasoning evaluates GDMT policies, constraints, interactions, dose plans, and dose-safety warnings. Verification agents await both the recommendation and GraphRAG context, then audit hard blocks, missing data, and evidence presence. Plain-language summaries and deterministic simplified card fields attach next. The service emits `recommendation_ready` and `verification_ready`.

Finally, the explanation layer streams `answer_delta` tokens grounded in the verified recommendation and retrieved evidence, then emits `done`. Cards and safety statuses remain authoritative; narrative text remains explanatory.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-4-chat-workflow.html" title="Figure 3.4 Chat pipeline"></iframe>
  <figcaption><strong>Figure 3.4.</strong> Chat message processing from dashboard input through backend stages to SSE clinical panel. Appendix A, Figure A.2.</figcaption>
</figure>

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-5-chat-sequence.html" title="Figure 3.5 Chat sequence"></iframe>
  <figcaption><strong>Figure 3.5.</strong> Sequence of one chat turn (doctor, dashboard, API, services, Ollama). Appendix A, Figure A.7.</figcaption>
</figure>

### 3.2.5. Knowledge Graph and Hybrid Retrieval Architecture

The knowledge graph centers on heart-failure entities linked to GDMT drug classes and agents. Entity types include drugs, drug classes, diseases, laboratory concepts, and related clinical nodes. Relationship types include treats, contraindicated with, indicated for, interacts with, and related monitoring edges. At runtime, GraphRAG binds patient medication terms to graph nodes, retrieves neighboring facts, and merges graph-derived evidence with textual chunks.

Hybrid retrieval combines four complementary signals. HyDE expansion can turn a short clinician question into a hypothetical answer document before embedding, bridging vocabulary gaps. Dense ChromaDB search with BGE-M3 finds paraphrased guideline language. BM25 sparse search favors exact drug names and regulatory phrases. Neo4j neighborhood traversal surfaces multi-hop facts that may be split across chunk boundaries. Reciprocal Rank Fusion merges ranked lists without brittle hand-tuned score calibration. Optional reranking can refine the top pool when latency budgets allow.

PostgreSQL rules provide executable enforcement. The graph and vector indexes provide evidentiary context for verification and explanation. This split is the architectural heart of the thesis: retrieval grounds language; rules govern safety.

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-3-3-graphrag.html" title="Figure 3.3 GraphRAG"></iframe>
  <figcaption><strong>Figure 3.3.</strong> GraphRAG hybrid retrieval (HyDE, multi-retriever fusion, reranking). Appendix A, Figure A.4.</figcaption>
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

### 3.4.1. Patient Profile Extraction Module

This module converts free-form physician chat and optional attachments into a typed PatientProfile. Regex numeric extraction captures LVEF, eGFR, potassium, blood pressure, heart rate, weight, and related values, including bilingual cues after Unicode normalization. Lexicon-based matching maps medication strings to substance keys with longest-token-first preference to reduce substring errors. Negation detection suppresses false positives near phrases such as “no,” “not,” “denies,” and Vietnamese “không.” Unit normalization attaches standard units and preserves raw spans for audit.

Selective LLM merge runs only when heuristics detect low confidence, such as long narratives or conflicting cues. Merge retains regex-sourced numeric labs over model guesses. Output feeds clinical-state construction, which compresses the profile into intent, focus classes, and key values for GraphRAG query building.

### 3.4.2. Missing-Fields and Risk Modules

The missing-fields module decides whether the current intent can be evaluated safely. If critical labs are absent, it returns a clarification prompt and prevents recommendation emission. The risk-extraction helpers derive flags such as renal impairment, hyperkalemia, hypotension, bradycardia, and missing critical data. Those flags become inputs to constraint matching. Separating risk derivation from rule evaluation keeps both testable.

### 3.4.3. Drug Normalization Module

Drug normalization resolves brand names, salts, and bilingual aliases to canonical keys used by interaction and GDMT logic. Without this module, rule catalogs written against substance identifiers would miss many free-text mentions. Normalization is therefore a linking step between language and governed catalogs.

### 3.4.4. Reasoning Service Module

The reasoning service produces the authoritative RecommendationResponse with no LLM in the critical path. It normalizes patient status bands, derives risks, evaluates GDMT policies per pillar, matches approved constraints, evaluates interaction sets, attaches dose plans, and applies dose-safety warnings. Overall status becomes blocked if any hard avoid exists, approved with warnings when moderate risks remain, or approved otherwise. Governance version strings record which catalog generation produced the result.

Three invariants govern the module. LLM output never modifies avoid statuses. Hard-block rules override permissive retrieved prose. Later modules cannot undo a hard constraint once fired.

### 3.4.5. Dose Calculation and Dose-Safety Modules

Dose calculation personalizes starting dose, target dose, renal bands, and titration schedules from JSONB rules. The evaluator resolves drug keys, applies eGFR bands, and emits suggested dose plans with units, frequency, and rationale. If a catalog row is incomplete, the module returns no fabricated milligram strength.

Dose safety complements dose plans by flagging planned doses that exceed label-derived maxima for the patient’s renal status. This separation keeps “what dose is typical” distinct from “what dose is too high for this patient now.”

### 3.4.6. Safety Constraint and Interaction Modules

Constraint rules carry target classes, actions, condition predicates, severity, risk names, and evidence references. Hard constraints are non-violable. Soft constraints warn without automatic blocking. Interaction rules store symmetric or directed drug sets with severity and management text. Both families load only approved rows at runtime and may be cached by class in Redis with invalidation on admin writes.

### 3.4.7. GraphRAG and Semantic Retrieval Module

GraphRAG assembles explanatory context for verification and answer generation. Query construction collects terms from the clinician message, patient profile, and clinical state. HyDE may expand short queries. Query decomposition may emit sub-queries for complex turns. Dense, sparse, and graph retrievers run with bounded top-k pools. RRF merges rankings. Post-fusion window expansion restores local sentence context. Evidence filtering and quality scoring remove weak chunks. Clinical entity boosting elevates passages that mention the patient’s medications. Outputs include ranked evidence chunks, graph facts, and scope metadata.

### 3.4.8. Verification and Citation Modules

Verification agents cross-check the deterministic recommendation before narrative completion. The safety agent fails on hard avoids and warns on cautions. The missing-data agent warns when critical labs remain unset. The evidence agent fails when retrieval returns no usable chunks or facts. Citation validation maps evidence references to retrieved chunk identifiers and source links. Aggregated verdicts appear in `verification_ready` payloads and UI badges.

### 3.4.9. Explanation Module

Explanation has two layers. The card summarizer deterministically maps structured fields to Vietnamese and English plain-language labels without calling an LLM. This keeps GDMT cards stable across language switches. The LLM answer service then writes clinician-facing narrative grounded in the verified recommendation and retrieved evidence, streamed as token deltas. Separating these layers prevents decorative language generation from rewriting safety status.





Governance supports list, detail, diff, approve, retire, and history operations for constraint, dose, interaction, GDMT, and dose-safety catalogs. Clinical leads refine conditions that extraction could not fully encode. Bulk approve helpers may exist for trusted batches, still under role checks. Diff views help reviewers see what changed between pipeline runs before promotion.

### 3.4.11. Chat Persistence and Audit Modules

Conversations, messages, and patient drafts persist in PostgreSQL so history can be reloaded across sessions. Redis may cache hot drafts for latency. Audit events record missing-field stops, recommendation outcomes, and governance actions with timestamps and actor identity. The CDSS is still not an EHR system of record for the whole hospital chart, but conversation and recommendation audit trails are first-class design artifacts.

## 3.5. Database and Storage Design

### 3.5.1. PostgreSQL as Governance and Conversation Store

PostgreSQL holds versioned rule catalogs. Constraint rules store identifiers, target class, action, reason, risk names, severity, evidence references, clinical source JSON, and draft/approved/retired lifecycle metadata. Dose rules store drug keys, starting and target dose JSON, renal adjustments, titration schedules, and safety tiers. Interaction rules store drug sets, type, severity, description, and management text. GDMT policies store executable class definitions. Dose-safety warnings store numeric maxima and related predicates. History tables retain change trails for governance review.

Chat tables store conversations, messages, and patient drafts keyed by conversation identifier, with cascade deletes for cleanup. Users and roles support authentication. Audit event tables support case-level review.

This schema is governance-centric rather than a full hospital EMR. Authoritative clinical decision logic lives in approved catalogs. Patient state for decision support may be ephemeral across turns yet still persisted enough for continuity and audit.

### 3.5.2. Redis Cache Design

Redis caches constraint slices by drug class, draft profiles and recent messages by conversation, rate-limit counters, and hashed LLM or HyDE responses. Cache entries are never the source of clinical truth. Admin approve or retire operations invalidate relevant keys so stale rules cannot continue executing after governance changes. TTL bounds limit how long patient narratives remain in cache.

### 3.5.3. ChromaDB Vector Store Design

ChromaDB collections store chunk identifiers, BGE-M3 embeddings, passage text, and metadata such as source type, drug class, section, and chunk type. Metadata enables pre-filtering and citation linking. Embeddings are computed offline during ingestion so interactive GraphRAG remains a nearest-neighbor query rather than an embedding-training job.

### 3.5.4. Neo4j Graph Store Design

Neo4j stores entities and typed relationships imported from pipeline artifacts. Runtime queries expand from matched drug or condition nodes into bounded neighborhoods used as graph facts. The graph is optimized for explanatory multi-hop retrieval, not for replacing PostgreSQL enforcement. After catalog refresh, graph import or backend bootstrap reloads relationships from processed artifacts.

### 3.5.5. Object Storage Design

Raw and processed buckets separate immutable downloads from normalized JSONL outputs. Content-addressed caches and checkpoints make pipeline reruns affordable. Backend bootstrap can hydrate runtime indexes from processed artifacts without re-scraping upstream sources.

## 3.6. API Design

### 3.6.1. Chat APIs

The primary clinician path is streaming chat under the versioned API prefix. A non-streaming chat endpoint may exist for simpler clients. History endpoints reload messages and drafts for a conversation. Requests carry JWT credentials, message text, conversation identifier, optional pre-seeded patient fields, language preference, and optional attachments.

SSE event order is an API contract: status frames, `draft_ready`, `missing_check` when needed, then either early `done` or the sequence `recommendation_ready`, `verification_ready`, `answer_delta` tokens, and `done`. Clients must render GDMT grids from recommendation payloads, not from answer tokens.

### 3.6.2. Supporting Clinical APIs

Dedicated endpoints expose recommendation building, GraphRAG context assembly, verification, dosing calculation, medication safety checks, clinical normalization helpers, evidence search, retrieval search, knowledge-graph lookups, and case audit history. These endpoints support the doctor dashboard, admin tooling, API explorer demos, and automated tests. They also make architecture inspectable: each concern can be exercised without running the full SSE chat path.

### 3.6.3. Auth, Health, and Admin APIs

Auth routes handle login, current user, and logout with cookie or bearer token patterns as configured. Health routes expose liveness, readiness, version, and dependency status for PostgreSQL, Redis, ChromaDB, Neo4j, object storage, and Ollama. Admin routes manage governance catalogs under role checks. Metrics endpoints may expose operational counters for monitoring.

### 3.6.4. Error and Idempotency Design

Missing-field short circuits are successful clinical outcomes, not server crashes. They return structured clarification. True failures emit terminal error status in the stream or HTTP error codes for non-stream routes. Idempotency keys may cache identical chat responses to reduce duplicate GPU load during retries.

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

This chapter specified the complete system design of the heart-failure CDSS. Requirements cover clinical decision support, evidence grounding, bilingual use, governance, and operations. The architecture combines a three-tier online stack with an offline knowledge-construction plane. Authority stays with governed PostgreSQL rules; GraphRAG and language models support retrieval and explanation; SSE ordering delivers safety artifacts before prose. Module designs span intake, missing-field gates, normalization, reasoning, dose and dose safety, constraints and interactions, GraphRAG, verification, explanation, governance, persistence, and audit. Storage, API, interface, deployment, and security sections show how those modules are exposed and protected. Chapter 4 maps this design to concrete implementation, pipelines, and operations.