# CHAPTER 4: IMPLEMENTATION AND DEPLOYMENT

<link rel="stylesheet" href="figures/thesis-figures.css">

This chapter describes how Chapter 3 designs became working software: environment, ingestion pipeline, FastAPI backend, React interfaces, tests, and Docker Compose. Measured results are in Chapter 5.

## 4.1. Development Environment

### 4.1.1. Hardware Configuration

Implementation used development laptops and a dedicated server that later served Chapter 5 evaluation runs. Development machines need at least eight CPU cores, 16 GB of RAM, and about 100 GB of SSD storage. A GPU is optional on a laptop when ingestion runs on CPU overnight. The evaluation server (Chapter 5, Section 5.1.1) used sixteen CPU cores, 32 GB of RAM, a 500 GB SSD, and an NVIDIA RTX 3080 GPU with 10 GB of video memory. The system runs a local large language model through Ollama so that clinical vignettes do not need to leave the hospital network. The chosen generation model, Qwen2.5-7B-Instruct, needs enough video memory to answer within a few seconds. The embedding model BGE-M3 also uses the GPU when building or searching dense vector indexes. Without a GPU, chat still works, but latency grows and the sub-ten-second median target becomes harder to meet. Engineers can write and test code on modest laptops; clinicians evaluate the system on hardware that matches a realistic hospital workstation.

### 4.1.2. Software Stack and Why Each Piece Exists

The backend is written in Python because the scientific and medical-informatics ecosystem is mature and asynchronous networking is strong. FastAPI receives HTTP requests, validates data against schemas, and streams Server-Sent Events (SSE) to the browser so the doctor dashboard can show a patient draft and recommendation cards while the conversational answer is still being written. PostgreSQL stores the governed clinical catalogs: constraint rules, dose rules, interaction rules, GDMT policies, dose-safety warnings, chat history, and audit events. Anything that can block or approve therapy must live in a transactional database that administrators can review, approve, or retire. Redis caches session data, rate-limit counters, and repeated language-model responses without replacing rules. Neo4j stores the medical knowledge graph for multi-hop GraphRAG queries. ChromaDB stores dense embeddings of evidence passages for semantic search when the doctor's wording differs from label text. Object storage provides versioned buckets for raw FDA files and processed artifacts so pipeline runs remain reproducible.

Ollama hosts local models: a 7-billion-parameter instruction-tuned model for clinician-facing answers, a smaller distilled model for HyDE expansion and verification prompts, and a multilingual embedding model for retrieval. Keeping inference local supports privacy-sensitive pilots and avoids per-token cloud costs. The frontend uses Node.js and React with a modern build tool. Nginx sits in front of the stack as a reverse proxy: it serves the doctor dashboard, routes admin traffic to the governance portal, and forwards API and streaming traffic to the backend.

### 4.1.3. Environment Setup

Local setup follows a fixed order so developers do not fight missing databases. First the repository is cloned. Next the Python virtual environment is created and backend dependencies are installed. Frontend packages install inside the doctor-dashboard directory. Docker Compose then starts PostgreSQL, Redis, Neo4j, ChromaDB, object storage, and Ollama. Application settings load from environment variables so development, Docker, and pipeline runs share one configuration vocabulary.

After containers are healthy, Ollama pulls the required models once. Model weights persist in a Docker volume, so later restarts do not re-download them. The FastAPI service starts with its ASGI server. In development, reload mode restarts the API when Python files change. The Vite development server proxies API calls to the backend so browser code can call the same relative paths used in production.

## 4.2. Knowledge Construction Pipeline

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-4-1-kb-pipeline.html" title="Figure 4.1 KB pipeline"></iframe>
  <figcaption><strong>Figure 4.1.</strong> Medical knowledge-base construction pipeline (acquire → extract → store → bootstrap). Appendix A, Figure A.3.</figcaption>
</figure>

### 4.2.1. Purpose and High-Level Stages

A clinical decision support system is only as trustworthy as its knowledge base. Manually typing thousands of label warnings into a database is slow and error-prone. The ingestion pipeline therefore automates four broad stages: acquire raw sources, load and normalize them, extract structured clinical artifacts, and store those artifacts into PostgreSQL, ChromaDB, and Neo4j. The orchestrator supports running the full pipeline or resuming from a named step such as knowledge-base foundation, constraint extraction, dose rules, interaction rules, or GDMT policies. Checkpoints record completed steps so a failed overnight job can continue without repeating successful work. Artifacts publish to the processed object-storage bucket while local workspace files remain available for debugging. Content hashes and on-disk LLM response caches prevent identical prompts from being sent to the model again during threshold tuning. An environment flag lets operators reprocess staged files without re-downloading from upstream sources. These mechanisms matter because pipeline iteration is frequent during research, and repeated cloud or local LLM calls would otherwise dominate cost and time.

### 4.2.2. Acquisition: Bringing Sources Into the System

Acquisition downloads authoritative documents and stores them unchanged. For FDA Structured Product Labels, the system queries the DailyMed API, resolves a drug name to an SPL set identifier, and downloads the XML label. Guidelines from ESC, AHA/ACC, and HFSA arrive as PDF or HTML according to the sources registry. Interaction supplements may arrive as curated JSON or CSV entries registered alongside labels.

Keeping raw files immutable is deliberate. If a later parsing bug is discovered, operators can re-parse the same bytes without guessing whether the upstream website changed. Asynchronous HTTP downloads many labels concurrently, which shortens wall-clock time when the manifest contains dozens of GDMT-relevant agents.

A practical limitation appears when local brand names or synonym spellings are missing from the acquisition registry. DailyMed then cannot resolve the product, and that drug never enters extraction. This gap is the same Vietnamese synonym problem later observed in chat intake evaluation. The implementation records registry coverage so operators know which agents still need mapping.

### 4.2.3. Loading and Document Processing

After acquisition, load and transform stages turn binaries into sectioned text. XML labels are parsed with section awareness so FDA headings such as dosage, warnings, contraindications, and drug interactions remain identifiable. PDF guidelines use layout-aware text extraction. HTML guidelines are cleaned of navigation chrome before section segmentation.

Each section receives a stable identifier, document provenance, and length statistics. Stable identifiers later connect a runtime citation back to the exact source passage a clinician can open. Drug names normalize toward RxNorm-style keys when possible. Laboratory units convert to canonical forms so a rule written against mmol/L potassium can compare fairly with patient values extracted from chat.

### 4.2.4. Chunking for Retrieval

Chunking splits long sections into passages suitable for vector search. The chunker uses a sentence-aware window of about 512 tokens with overlap. It accumulates whole sentences until the budget is nearly full, then carries the last sentences into the next chunk. Overlap exists because a contraindication often spans two sentences: the first names the drug, the second states the lab threshold. A hard cut between those sentences would leave each chunk incomplete.

Good chunks improve GraphRAG later. Dense retrieval ranks passages by meaning. Sparse BM25 ranks passages by exact words. Both need coherent local context. Overly large chunks dilute relevance. Overly small chunks lose conditional language. The 512-token overlapping window is the engineering compromise used throughout evaluation.

### 4.2.5. Three-Tier Section Filtering

Not every section in a drug label is clinically useful for heart-failure decision support. Storage instructions and packaging details rarely help GDMT reasoning. Sending every section to a language model would be expensive and slow. The section filter therefore applies three tiers.

Tier one matches high-value headings with keywords such as dosage, warnings, contraindications, and drug interactions. Matching sections are kept immediately. Tier two embeds the title and opening text with BGE-M3 and compares them to prototype vectors for clinical section types. Scores at or above 0.52 are kept. Tier three reviews only the uncertain band from 0.40 to 0.52 with a short LLM keep-or-drop prompt. Scores below 0.40 drop without an LLM call. A hard cap of 400 borderline LLM calls per run bounds worst-case spend.

This cascade is the offline twin of hybrid chat intake. Fast deterministic methods handle clear cases. Embeddings handle paraphrases. The language model spends budget only where uncertainty is real. In evaluation, the filter retained about 95 percent of sections while invoking borderline LLM review on only about 6.6 percent of inputs.

### 4.2.6. Extraction of Structured Clinical Artifacts

Extraction converts kept text into objects the runtime can evaluate. Several specialized builders cooperate. Constraint rule extraction produces conditional avoid and caution statements. Dose rule extraction captures starting doses, target doses, renal bands, and titration schedules. Interaction extraction builds drug-set pairs with severity and management text. GDMT policy extraction encodes four-pillar coverage expectations for HFrEF. Dose-safety warning extraction captures label maxima that should fire when a planned dose exceeds safe limits for the patient’s renal band.

The hybrid strategy is regex first, language model second. High-frequency SPL phrasing is cheap to match with patterns. When patterns are sparse, the system calls the local chat API with a schema-validated prompt. Invalid responses are rejected before they enter the artifact stream. Prompt hashes feed the ingestion cache so identical sections do not re-spend tokens on every rerun.

Named entity recognition and relation linking attach drugs, classes, labs, and conditions to each claim. Evidence linking stores chunk identifiers so a later recommendation card can show the passage that motivated a rule. Deduplication collapses near-identical extractions from overlapping label sections.

### 4.2.7. Classification and Governance Gates

Classification assigns deployability before rules reach clinicians. Safety tiers include hard_block for absolute contraindications, usable_rules for complete executable conditions, and needs_condition_refinement for drafts that parse but still need human clarification. Action types include avoid, consider with caution, consider, and continue. These labels map directly to recommendation card badges in the doctor dashboard.

Rules marked for refinement sync into PostgreSQL for admin review rather than disappearing. Runtime loaders ignore unfinished drafts until a clinical lead promotes them. This gate is essential. Automated extraction is powerful, but heart-failure safety cannot depend on unreviewed model guesses.

### 4.2.8. Synchronization to Runtime Stores

The store stage upserts approved and draft catalogs into PostgreSQL, publishes processed artifacts to object storage, and prepares artifacts for ChromaDB and Neo4j hydration. Backend bootstrap can pull processed artifacts on startup so a fresh container does not need to re-scrape DailyMed. Operators can also rebuild graph and vector indexes from the knowledge-base foundation step without repeating acquisition when only embeddings or relationships need refresh.

PostgreSQL remains authoritative for executable rules. ChromaDB and Neo4j enrich explanation and verification. Redis is never treated as the long-term home of clinical truth. That separation keeps audit trails and admin workflows centered on one relational catalog.

## 4.3. Backend Implementation

### 4.3.1. Modular Monolith Layout

The backend is a single FastAPI process organized as a modular monolith. The main entry point registers routes at startup and runs the bootstrap sequence. Route modules cover chat streaming, recommendations, clinical normalization and risks, dosing evaluation, medication safety checking, graph-augmented retrieval, evidence search, knowledge graph queries, LLM interaction, audit logging, authentication, health probes, metrics, and administrative governance. A central router assembles these modules under a versioned API prefix.

Core utilities provide configuration from environment variables, JWT encoding and role extraction, password hashing, and request middleware for rate limiting and request identification. Internal modules implement clinical intake extraction using regex, lexicon matching, and selective language-model merge; pure classification functions for normalization; binary risk flag extraction; constraint rule evaluation with a TTL cache; dose ceiling evaluation; FDA label dose planning; drug-drug interaction detection; the full recommendation pipeline; graph-augmented retrieval combining dense, sparse, and graph methods; negative evidence filtering; chunk-to-claim linking; evidence quality scoring; citation-to-chunk verification; a six-agent verification pipeline; card summarization and plain-language answer generation; chat orchestration with server-sent events; and a governance diff engine for bulk approval. Datastore adapters isolate SQL, Redis, vector, and graph details from clinical logic. Each module has a dedicated test file covering its public interface.

### 4.3.2. Chat Orchestration and SSE Event Order

The SSE pipeline is the primary clinical interaction surface. The stream function processes one clinician message into an ordered event stream. The sequence begins with authentication and conversation setup. Intake extraction merges extracted patient fields with prior draft and streams the draft immediately. A missing-field gate halts the pipeline if critical labs are absent. Otherwise, graph-augmented retrieval and rule evaluation run concurrently. After both complete, verification agents audit the recommendation and evidence. Deterministic card labels are merged with language-model summaries. Recommendation and verification events stream to the client, followed by incremental answer tokens and a final snapshot.

The thread offload moves synchronous PostgreSQL rule evaluation off the event loop. Without it, a long constraint scan would block unrelated requests such as health checks or admin list queries. With it, concurrent API traffic is unaffected. GraphRAG prefetch starts as soon as the draft is saved so that total latency equals the maximum of reasoning time and retrieval time rather than their sum.

The fail-closed gate ensures the pipeline stops when critical labs are absent rather than emitting an unsafe recommendation based on incomplete information.

The intake pipeline is three-stage, as designed in Section 3.4.1.

**Stage 1 — Regex extraction.** Patterns cover:
- Numeric labs: LVEF, eGFR, potassium, systolic blood pressure, heart rate, weight, INR
- Vietnamese unit support: “kali máu 4.4”, “huyết ap 118/74”, “mạch 74 lần/phút”
- Medication with dose and frequency

**Stage 2 — Semantic matching.** Embedding-based catalog lookup for brand names absent from the static lexicon. Thread-safe, Lock-protected cache avoids repeated embedding calls.

**Stage 3 — Selective LLM merge.** A decision engine calls the LLM only when input is vague or conflicts exist; simple structured text skips this stage entirely. Prompt injection defense strips attack patterns before the LLM call. Retry logic uses exponential backoff.

**Conversation context contribution:** Prior messages in the conversation are passed as context to extraction, so multi-turn chat accumulates a profile without forcing the doctor to retype lab values.

**Output:** PatientProfile — legacy flat or nested domain. The LLM enriches with full_name, age, sex, weight_kg when extraction confidence is low.

### 4.3.4. Clinical Normalization and Risk Extraction

Normalization functions (Section 3.4.2) are pure — no I/O, no randomness. **Table 4.2** lists the numeric bands the implementation uses when classifying renal function, potassium, blood pressure, and heart rate from typed labs and vitals. These thresholds are fixed constants in code (not learned), so unit tests can assert exact labels for boundary values.

**Table 4.2. Clinical normalization thresholds**

| Classification | Thresholds |
|---|---|
| Renal status | <15 kidney_failure · 15–29 severely_reduced · 30–44 moderately_reduced · 45–59 mildly_reduced · ≥60 preserved |
| Potassium status | <3.5 low · 3.5–5.0 normal · 5.0–5.3 elevated · ≥5.3 high |
| Blood pressure status | <90 hypotension · 90–99 low · 100–130 acceptable · >130 elevated |
| Heart rate status | <60 bradycardia · ≤100 acceptable · >100 tachycardia |

Normalization applies whitespace trimming and lowercase normalization to comorbidities.

Risk extraction (Section 3.4.3) feeds the constraint builder. Tests verify all flag logic, including the ckd_history preservation invariant: when CKD appears in comorbidities but eGFR is not in a reduced band, ckd_history is set but renal_impairment is not — the comorbidity context is preserved without double-counting the risk.

### 4.3.5. Constraint Builder Implementation

Constraint building follows three steps:

1. **Load approved rules** from PostgreSQL. TTL cache (5 min) reduces repeated DB reads. On DB error: stale cache is served if available; empty list is returned if no prior cache exists. This fail-stale design prevents cache poisoning while maintaining availability.
2. **Build constraints** by iterating over rules; match when every risk_name in the rule is present AND at least one severity matches the patient’s band. Result is a set of drug-class and action tuples.
3. **Cache management:** invalidation called synchronously from admin approve/retire routes.

Tests verify rule loading, cache hit behavior, stale cache on DB error, empty list on fresh DB error, and constraint firing for MRA, RAAS, and beta blocker risk profiles.

### 4.3.6. Dose Calculation and Dose Safety Implementation

Dose calculation reads structured rules from the PostgreSQL governance catalog. Given a patient and a drug, it selects the matching eGFR band and returns a dose plan with start dose, target dose, titration steps, and rationale. If the catalog row is incomplete, the function returns no fabricated number.

Dose safety evaluation iterates all approved warning rules. For each rule:
- Drug key matching: rule target medications intersect patient’s medication list
- Condition evaluation: each condition group supports operators always, missing, present, lt, lte, gt, gte, missing_or_lt, missing_or_lte
- Severity resolution: highest applicable severity from severity_rules chain (critical > high > moderate > low)

Tests verify that digoxin with reduced renal function triggers a critical warning. Tests also verify graceful degradation when the database is unavailable.

### 4.3.7. Medication Safety — Interaction Checking

Interaction checking normalizes the patient’s medication list through the drug normalization pipeline before comparing against approved interaction pairs. Tests verify that triple RAAS (ACE + ARB), RAAS + MRA hyperkalemia, and anticoagulant + antiplatelet bleeding interactions all fire with correct warning IDs.

Tests confirm that when a recommendation is built, the resulting objects carry safety warning IDs from both dose safety and interaction checks, and the warnings list is non-empty for affected classes.

### 4.3.8. Reasoning Service Implementation

The reasoning service orchestrates nine pipeline steps in order. It normalizes the patient, extracts risk flags, builds constraints (thread-offloaded to avoid blocking), evaluates dose safety warnings from the cache, checks interactions against a normalized medication list, loads GDMT policies, generates per-pillar recommendations, builds dose plans from FDA label data, and computes an overall status of blocked, approved with warnings, or approved.

The overall_status logic: **blocked** if any avoid constraint or any critical warning; **approved_with_warnings** if any risk or warning is present; **approved** otherwise. Governance version strings are attached to the response, enabling post-hoc reconstruction of which catalog generation produced a given result.

### 4.3.9. GraphRAG and Evidence Retrieval Implementation

Query construction collects terms from the clinician message, patient profile, and clinical state (Section 3.4.11). Query decomposition may emit sub-queries for complex turns.

The retrieval pipeline begins with query term collection from the message, patient profile, and clinical state. Optional HyDE expansion enriches short queries. Dense retrieval via BGE-M3 embeddings, sparse BM25 keyword matching, and Neo4j multi-hop neighborhood queries run in parallel. Reciprocal Rank Fusion merges candidates, which then pass through evidence filtering and clinical entity boosting before ranking.

BM25 indexes rebuild in memory at backend startup from published chunk metadata. This favors low query latency at the cost of requiring a restart after knowledge refresh.

Evidence filtering drops chunks where the score falls below 0.40, the section belongs to an irrelevant category such as contact or packaging information, or the text lacks any patient-specific entity such as medication names, lab terms, or condition names. Constraint-pinned chunks bypass this filter entirely. When fewer than the minimum results threshold remain, fallback chunks are included to reach the top_k floor.

### 4.3.10. Verification Agents Implementation

Six agents run after both RecommendationResponse and GraphRAGContextResponse are available. Each agent produces a typed verdict:

- **Safety agent**: Fails if any avoid constraint is present and the narrative does not explicitly block. Warns if caution constraints fire.
- **Missing data agent**: Warns if any missing_* risk flag is present and the recommendation affected that drug class.
- **Evidence agent**: Fails if evidence_chunks is empty.
- **Guideline alignment agent**: Passes if all GDMT pillar statuses are within guideline-allowed bounds.
- **Citation validator agent**: Validates citations against retrieved chunks; sets citation status.
- **Final reviewer agent**: Aggregates verdicts — final verdict is fail if any agent fails, warning if any warns, else pass.

Tests verify both graph facts and evidence chunks appear in the GraphRAG response. Tests confirm all six agents produce results. Tests verify final verdict and citation status range.

### 4.3.11. Citation Validation Implementation

Citation validation cross-checks each constraint’s evidence_ref (a chunk ID) against the retrieved evidence_chunks list. Matched constraints gain a CitationSupport object with evidence_refs, source_links constructed with page fragments, evidence_verdict (supported / weakly_supported / unsupported), and confidence score (0.0–1.0).

Tests verify supported citations carry evidence references and page fragments with confidence greater than zero.

### 4.3.12. Explanation and Card Summarizer Implementation

Deterministic card summarizer maps structured fields to Vietnamese and English labels without LLM calls. The merge function fills in LLM-generated summaries where available, falling back to deterministic for each item independently. The parse function ignores drug classes not in the recommendation.

LLM answer service:
- Attaches plain language summaries — async, calls Ollama with JSON-schema prompt; response cached in Redis with 24-hour TTL keyed by recommendation hash
- Falls back to structured plain_language_summary when LLM is disabled or unavailable
- Compacts recommendation payload to fit the context window

Tests verify Vietnamese deterministic output contains ARNI/RAAS and excludes placeholder text. Tests verify no language model call is made when completions are disabled.

### 4.3.13. Governance and Admin API Implementation

Governance diff engine compares before and after states, returning a list of Change objects with path, change_type (added/removed/modified), before_value, and after_value. Separate field lists cover constraints, dose rules, interactions, GDMT policies, and dose safety warnings.

**Status transition enforcement** (Section 3.4.17): Tests verify HTTP 400 on invalid draft-to-retired transitions (must pass through approved first).

**Cache invalidation:** invalidation called synchronously from every approve/retire route, ensuring the next chat request loads fresh rules.

**Bulk approve:** dry-run mode available so clinical leads can preview what would be approved before committing.

### 4.3.14. Auth and Security Implementation

JWT encoding: 15-minute expiry, HS256, payload with user_id, roles, and expiry. Both cookie and bearer token modes supported.

Production hardening:
- API key required on all unversioned chat paths; deprecated without API key returns 401
- Request ID propagated on success and error responses
- PHI not echoed in validation errors (only field names)
- Degraded dependency state returns HTTP 503
- Rate limiting: sliding window on chat and chat/stream endpoints
- Prometheus metrics exposed at /metrics
- Bearer JWT accepted as fallback authentication for clinical routes

Token revocation: inactive users rejected even with a valid signature. Login rate limiting: sliding window tracked in middleware; blocks after N failures within the window.

## 4.4. Frontend Implementation

<figure class="thesis-archify-figure">
  <iframe src="figures/chapters/figure-4-2-frontend-routes.html" title="Figure 4.2 Frontend routes"></iframe>
  <figcaption><strong>Figure 4.2.</strong> Doctor dashboard routing: home, chat, and admin governance pages. Appendix A, Figure A.6.</figcaption>
</figure>

Table 4.1 maps URLs in the Vite mono-app to React pages. The split between `/chat` and `/admin/*` mirrors the design boundary in Chapter 3: clinicians stay on the chat and evidence surfaces, while clinical leads use nested admin routes to approve or retire governed catalogs without redeploying the backend. The table is the authoritative route list for integration testing and for Nginx path rules described in Section 4.5.2.

**Table 4.1. Frontend routes** (Appendix A, Table A.2)

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | HomePage | Landing page |
| `/chat` | ChatPage | Main chat interface |
| `/admin` | AdminLayout | Admin portal (redirects to /admin/rules) |
| `/admin/rules` | RulesPage | Constraint rules management |
| `/admin/dose-rules` | DoseRulesPage | Dose rules management |
| `/admin/dose-safety-warnings` | DoseSafetyWarningsPage | Safety warnings |
| `/admin/interaction-rules` | InteractionRulesPage | Drug interactions |
| `/admin/gdmt-policies` | GdmtPoliciesPage | GDMT policies |
| `/admin/evidence` | EvidencePage | Evidence management |
| `/admin/audit` | AuditPage | Audit logs |
| `/admin/system` | SystemPage | System health |
| `/admin/api` | ApiExplorerPage | API testing |
| `/admin/users` | UsersPage | User management (admin only) |

In practice, most clinical traffic hits `/` and `/chat`, while governance workflows fan out under `/admin` with one page per catalog family (constraints, dose, interactions, GDMT, evidence, audit). Shared packages keep field labels consistent across those admin screens and the doctor dashboard cards fed by the same API types.

Standalone HTML: [`tables/chapters/table-4-1-frontend-routes.html`](tables/chapters/table-4-1-frontend-routes.html).

### 4.4.1. Application Structure

The frontend monorepo contains the doctor dashboard, the admin portal, and shared packages for API clients and display helpers. The doctor dashboard is the primary clinical surface. It includes chat runtime components, a clinical side panel, conversation sidebar controls, evidence browsing, and bilingual message catalogs.

State for conversations can persist locally so a clinician can return to a case. Creating a conversation captures a patient name and opens a welcome message. Deleting or clearing a conversation removes local history and returns the UI to a clean case setup when needed. These controls sound small, but they matter for usability during demonstrations and multi-case review sessions.

### 4.4.2. SSE Client and Progressive Rendering

The client module that consumes chat streams parses SSE frames and dispatches them by event type. When the patient draft arrives, the clinical panel can show extracted vitals and medications. When recommendations arrive, GDMT cards render. When verification data arrives, badges update. Answer tokens append to the assistant message as they stream.

Progressive rendering is not cosmetic. It implements the same safety-first ordering as the backend. A doctor can begin reading structured advice before the full paragraph finishes, which is valuable on rounds where seconds matter.

### 4.4.3. Clinical Panel and Evidence Cards

The clinical panel shows patient context, recommendation cards, dose plans when available, and evidence snippets. Recommendation cards bind only to structured fields and simplified labels. They never infer avoid or continue status from free-text tokens. Evidence cards emphasize human-readable document titles, page numbers, publishers, and excerpts rather than technical chunk identifiers. “Open source” links take the clinician to the original label or guideline when a URL is present.

### 4.4.4. Language Switching

A language provider stores the preferred locale, updates accessibility attributes, and supplies translation functions to components. Switching between Vietnamese and English regenerates card labels and UI chrome. Conversation identifiers and structured patient state remain unchanged. Because simplification is deterministic and fast, language switching completes without re-running retrieval or reasoning.

### 4.4.5. Admin Portal Implementation

The admin portal exposes governance tables for constraints, dose rules, interactions, GDMT policies, and related catalogs. Clinical leads can open a record, inspect provenance, refine conditions, approve usable rules, or retire outdated ones. Evidence search pages help reviewers inspect retrieved passages during catalog curation. Sticky action columns and short display labels reduce visual clutter so reviewers focus on clinical meaning rather than raw identifiers.

Admin workflows close the loop with the ingestion pipeline. Extraction can draft thousands of rules, but only approved executable tiers affect chat recommendations. That human gate is part of the implementation, not an afterthought.

### 4.4.6. Admin Approve and Retire Flow

When a clinical lead opens a draft constraint in the admin portal, the UI shows the condition object, rationale, linked evidence, and current governance status. Approving the record updates PostgreSQL and can invalidate caches that held older catalog slices. Retiring a rule keeps historical rows for audit but removes them from runtime loaders. Editing a condition may move a rule from the refinement-needed tier to the usable tier after validation. These operations sound administrative, yet they are the operational heart of maintainability: the chat service never needs a code deploy merely because a label added a new potassium warning.

Version diffs and detail panes help reviewers see what changed between pipeline runs. Condition panels surface structured predicates that would otherwise hide inside JSON. Catalog list pages use short clinical titles with technical identifiers kept secondary so reviewers scan by drug and action rather than by hash strings.

### 4.4.7. Shared Packages and API Clients

Shared frontend packages centralize HTTP helpers, evidence display formatting, and governance field rendering. Doctor and admin apps therefore show consistent labels for the same underlying catalogs. API clients encode paths such as chat stream, history, evidence search, and admin list endpoints once, reducing duplicated fetch logic and making authentication headers consistent across pages.

## 4.5. System Deployment

### 4.5.1. Docker Compose Topology

Docker Compose orchestrates PostgreSQL, Redis, Neo4j, ChromaDB, Ollama, MinIO, the FastAPI backend, frontend services, and Nginx. Health checks delay backend startup until databases and model services are ready. GPU passthrough to the Ollama container is configured on hosts with the NVIDIA Container Toolkit.

Each service has a clear job. PostgreSQL persists governed truth. Redis accelerates hot reads. Neo4j answers relationship queries. ChromaDB answers semantic passage queries. Ollama runs embeddings and generation. MinIO stores raw and processed artifacts with a persistent Docker volume. The backend performs clinical orchestration. Frontends present doctor and admin workflows. Nginx unifies access through one host port.

Compose was chosen over Kubernetes for the evaluation scale. A single-host pilot serving on the order of tens of concurrent users does not justify Kubernetes operational overhead. The modular monolith can later split GraphRAG or Ollama into separate services if load profiles demand it.

Volumes persist database files, model weights, and object-store data across restarts. Without volumes, every Compose reboot would force model re-downloads and empty catalogs, which is unacceptable for iterative clinical demos.

### 4.5.2. Nginx Routing

Nginx terminates HTTP and routes by path. The doctor dashboard is served at the site root. The admin portal is served under a dedicated path. API and streaming traffic proxy to the backend with buffering disabled so streams flush promptly. A single origin simplifies browser security by avoiding cross-origin complexity in production.

### 4.5.3. Configuration Management

Thresholds and model names live in environment variables. Examples include database URLs, Redis URLs, Ollama base URL, generation and embedding model names, Neo4j credentials, Chroma host, S3 endpoint and bucket names, JWT secrets, CORS origins, section-filter similarity thresholds, borderline LLM enablement, and retrieval top-k settings. Operators can tune cost and quality without editing Python source. This is important when a new guideline PDF uses unfamiliar headings and section-filter thresholds need adjustment.

### 4.5.4. Deployment Trade-offs

Local Ollama was preferred over cloud LLM APIs to keep vignettes on premises, control latency, and avoid per-token fees. The trade-off is GPU capital cost and model operations. MinIO was chosen for development S3 compatibility with durable volume-backed buckets; production can use AWS S3 without changing artifact layout. Neo4j Community and ChromaDB co-locate with the stack so embeddings and graph facts remain under institutional control; disaster recovery rebuilds indexes from processed S3 artifacts when needed.

## 4.6. Testing

Test case identifiers (`TC-I-01`, `TC-CH-06`, and so on) match the design contracts in **Chapter 3, Section 3.4**. Chapter 3 states what each module must verify; this section documents the pytest input and expected-output specifications. Tables 4.3–4.16 cover the original clinical pipeline; Tables 4.17–4.21 cover chat orchestration features added after the baseline implementation (language detection, question planner, missing-field gate extensions, multi-question SSE, chat audit).

### 4.6.1. Test Philosophy

The test suite follows the same authority separation as the production system. Deterministic modules — normalization, constraint matching, dose evaluation, clinical classification — are unit-tested with no mocks. Their correctness depends only on their input, making failures fast and reproducible. Generative components — LLM extraction, LLM summarization, verification agents — are mocked in CI so GPU hardware is not required for every pull request. Clinical accuracy of recommendations on vignettes still requires cardiologist review (Chapter 5), because judgment about therapeutic trade-offs is not fully automatable.

The test infrastructure is designed so that all 69 test files run without live PostgreSQL, Redis, ChromaDB, Neo4j, or Ollama instances. Fixture data lives in the fixtures directory. Session-level monkey-patching isolates the application from external services. This enables developers to run the full suite on a laptop.

### 4.6.2. Test Infrastructure

The test setup establishes the test environment with the following mechanisms:

**Session fixtures:**
- Authenticated test client with API key header
- Unauthenticated client for testing auth failures

**Auto-use fixtures (every test):**
- Configures test auth and patches session dependencies
- Disables HyDE retrieval in tests
- Stubs LLM extraction with a no-op except for intake-specific test files
- Resets in-memory caches before and after each test
- Isolates session clients by clearing cookies between tests

**Helper fixtures:**
- Standard HFrEF patient with typical lab values and comorbidities
- API path helper that adds the versioned prefix

**Dependency isolation:**
- Fakes bootstrap completion
- Patches GraphRAG loaders to return sample data
- Patches rule readers to return fixture data
- Patches datastore status to return healthy responses
- Patches chat persistence to use in-memory structures instead of PostgreSQL

**Fixture data:**
- Sample constraint rule rows for tests
- Sample dose safety warning rules with condition-based triggers

### 4.6.3. Unit Tests — Clinical Intake and Normalization

**Table 4.3** documents pytest cases for the three-stage intake extractor: Vietnamese free text, brand-name medications, red flags, structured bypass of the LLM, and merge behavior when regex and model disagree.

**Table 4.3. Intake extraction test cases**

| TC | Input | Expected output |
|----|-------|----------------|
| TC-I-01 | Full Vietnamese patient description with labs, vitals, medications, and allergy | LVEF, eGFR, potassium, blood pressure, heart rate extracted; metoprolol dose and frequency parsed; allergy recorded |
| TC-I-02 | No CKD, no diabetes, no spironolactone, NKDA | Comorbidities empty; spironolactone not in medications; no known drug allergies |
| TC-I-03 | Taking Entresto and Farxiga | Current medications normalized correctly |
| TC-I-04 | Active bleeding today | Red flag for active bleeding present |
| TC-I-05 | Structured input with all required fields | Language model extractor not invoked |
| TC-I-06 | Vague request with mock language model | Patient identity populated; pattern-extracted values override model guesses |

**Table 4.4** verifies heart-failure typing from LVEF, renal and electrolyte bands, blood pressure and heart rate classes, polypharmacy detection, and comorbidity string normalization—each row is a boundary or regression check on the pure functions in §4.3.4.

**Table 4.4. Normalization classification test cases**

| TC | Classification | Input | Expected |
|----|----------|-------|---------|
| TC-N-01 | Heart failure type | 40 | HFrEF |
| TC-N-01 | Heart failure type | 45 | HFmrEF |
| TC-N-01 | Heart failure type | 55 | HFpEF |
| TC-N-01 | Heart failure type | None | unknown |
| TC-N-02 | Renal status | 12 | kidney failure |
| TC-N-02 | Renal status | 28 | severely reduced |
| TC-N-02 | Renal status | 38 | moderately reduced |
| TC-N-02 | Renal status | 55 | mildly reduced |
| TC-N-02 | Renal status | 90 | preserved |
| TC-N-03 | Potassium status | 3.2 | low |
| TC-N-03 | Potassium status | 4.9 | normal |
| TC-N-03 | Potassium status | 5.2 | elevated |
| TC-N-03 | Potassium status | 5.5 | high |
| TC-N-04 | Blood pressure status | 88 | hypotension |
| TC-N-04 | Blood pressure status | 120 | acceptable |
| TC-N-05 | Polypharmacy | Five medications | True |
| TC-N-05 | Polypharmacy | Empty list | False |
| TC-N-06 | Normalize patient | " Chronic_Kidney Disease " | "chronic kidney disease" in normalized comorbidities |

### 4.6.4. Unit Tests — Risk Extraction

**Table 4.5** covers binary risk flags derived after normalization: combined high-risk profiles, missing-lab flags, and the invariant that documented CKD history does not double-count as renal impairment when eGFR is preserved.

**Table 4.5. Risk extraction test cases**

| TC | Patient profile | Expected risk flags |
|----|----------------|--------------------|
| TC-R-01 | eGFR=28, K=5.6, SBP=88, HR=55, five medications, diabetes | Renal impairment, hyperkalemia, hypotension, bradycardia, polypharmacy, diabetes |
| TC-R-02 | No LVEF provided | Missing LVEF flag in risk names |
| TC-R-03 | LVEF=35 only | Renal impairment not present; hyperkalemia not present; missing eGFR, potassium, blood pressure, heart rate in risk names |
| TC-R-04 | LVEF=35, eGFR=70, CKD comorbidity | CKD history present; renal impairment not present |

### 4.6.5. Unit Tests — Patient Schema

**Table 4.6** ensures the Pydantic patient model accepts both legacy flat payloads and nested demographics/labs while exposing the same computed properties to downstream reasoning.

**Table 4.6. Patient schema compatibility test cases**

| TC | Payload shape | Assertions |
|----|-------------|-----------|
| TC-S-01 | Legacy flat fields | All flat fields map via computed properties |
| TC-S-02 | Nested fields with demographics and labs | Patient identity populated; eGFR and medications correctly parsed |

### 4.6.6. Unit Tests — Drug Normalization and Evidence Linking

**Table 4.7** exercises brand-to-generic resolution, search-term expansion for retrieval, and chunk linking so recommendation cards carry stable evidence identifiers and ranked context.

**Table 4.7. Drug normalization and evidence linking test cases**

| TC | Call | Expected |
|----|------|---------|
| TC-D-01 | Resolve "Jardiance" | empagliflozin |
| TC-D-01 | Resolve "entresto" | sacubitril and valsartan |
| TC-D-02 | Expand drug search terms for "entresto" | Set includes both brand name and generic form |
| TC-D-03 | Find chunk for matching document, section, and text | Returns matched chunk with correct document prefix |
| TC-D-04 | Enrich recommendation evidence | Recommendation evidence field contains the linked chunk ID |
| TC-D-05 | Prioritize context chunks with high linked score | Linked chunk appears first in evidence chunks |

### 4.6.7. Unit Tests — Constraint Builder

**Table 4.8** validates PostgreSQL rule loading, TTL cache hit and fail-stale behavior, and firing of MRA avoid, RAAS caution, and beta-blocker caution constraints on representative lab profiles.

**Table 4.8. Constraint builder test cases**

| TC | Patient | Expected |
|----|---------|---------|
| TC-C-01 | Any | Returns list of constraint rules; each has rule identifier |
| TC-C-02 | — | Call load twice; database read function called exactly once |
| TC-C-03 | — | Database errors after first successful load; second call returns cached result |
| TC-C-04 | — | Database errors with no prior cache; returns empty list |
| TC-C-05 | eGFR=25, potassium=4.8 | MRA avoid constraint fires |
| TC-C-06 | eGFR=80, potassium=5.2, systolic BP=96 | ARNI/ACEi/ARB caution constraint fires |
| TC-C-07 | Heart rate=55 | Beta blocker caution constraint fires |
| TC-C-08 | eGFR=75, potassium=4.2, BP=118, HR=72 | No constraints |

### 4.6.8. Unit Tests — Dose Safety and Interaction Checking

**Table 4.9** checks dose-safety warning rules and interaction pairs (ACE+ARB, RAAS+MRA, anticoagulant+antiplatelet), including graceful empty results when the governance database is unavailable.

**Table 4.9. Dose safety and interaction test cases**

| TC | Patient medications | Expected warnings |
|----|--------------------|--------------------|
| TC-DS-01 | Digoxin, spironolactone, furosemide | Digoxin renal review, MRA renal potassium review, loop diuretic lab monitoring present |
| TC-DS-02 | Same as above | Any warning with critical severity |
| TC-DS-03 | Any | Database unavailable returns empty list |
| TC-DS-04 | Lisinopril, losartan | ACEi-ARB combination warning fires |
| TC-DS-05 | Lisinopril, spironolactone | RAAS plus MRA hyperkalemia monitoring warning fires |
| TC-DS-06 | Apixaban, aspirin | Anticoagulant-antiplatelet bleeding warning fires |
| TC-DS-07 | Lisinopril, spironolactone, digoxin | MRA recommendation carries appropriate warnings |

### 4.6.9. Unit Tests — Recommendation Engine

**Table 4.10** summarizes end-to-end recommendation engine outcomes: blocked versus approved status, GDMT class actions, HF type classification, and warning paths when critical labs are missing.

**Table 4.10. Recommendation engine integration test cases**

| TC | Patient profile | Expected |
|----|----------------|---------|
| TC-REC-01 | LVEF=30, eGFR=28, K=5.4, SBP=92, HR=58, CKD | Overall status blocked; risk flags include renal impairment, hyperkalemia, hypotension, bradycardia; MRA status avoid; SGLT2i status consider with caution |
| TC-REC-02 | LVEF=32, eGFR=78, K=4.4, SBP=118, HR=74, hypertension | Overall status approved; no risk flags; no constraints; all GDMT classes status consider |
| TC-REC-03 | LVEF=55 | Overall status approved; heart failure type is HFpEF; all GDMT classes status review |
| TC-REC-04 | LVEF=30, SBP=96; missing eGFR, K, HR | Overall status approved with warnings; risk flags include missing eGFR, potassium, heart rate; all GDMT classes status consider with caution |

### 4.6.10. Unit Tests — Evidence Filter and Citation Validation

**Table 4.11** tests GraphRAG entity extraction for retrieval queries, evidence filtering (score floors, irrelevant sections, pinned chunks), and citation support objects attached to governed constraints.

**Table 4.11. Evidence filter and citation validation test cases**

| TC | Setup | Expected |
|----|-------|---------|
| TC-E-01 | Patient with eGFR, spironolactone, CKD | Patient entities include spironolactone, eGFR, hyperkalemia |
| TC-E-02 | Three chunks: renal, contact, generic | With top_k=1 returns only renal chunk |
| TC-E-03 | Chunk with pinned flag, low score | Passes evidence filter regardless of score |
| TC-E-04 | Two chunks: renal and generic; min_results=2 | Both chunks included; renal first |
| TC-CV-01 | Recommendation with evidence reference; matching chunk | Citations validated; verdict is supported or weakly supported |
| TC-CV-02 | Chunk with source URL, page number | Page fragment constructed correctly |
| TC-CV-03 | Any supported citation | Confidence score greater than zero |

### 4.6.11. Unit Tests — Card Summarizer and Explanation

**Table 4.12** covers deterministic Vietnamese card text, LLM merge fallbacks, unknown-class rejection, and behavior when completions are disabled—ensuring displayed status always mirrors structured recommendation fields.

**Table 4.12. Card summarizer and explanation test cases**

| TC | Input | Expected |
|----|-------|---------|
| TC-CS-01 | Vietnamese language; ARNI consider item | Output contains ARNI or RAAS; no placeholder text |
| TC-CS-02 | Vietnamese; card details | All lines plain language; no technical phrases |
| TC-CS-03 | Language model response with unknown drug class | Ignored; output contains only known classes |
| TC-CS-04 | Two-item recommendation; LLM summary only for first | Second item falls back to deterministic; no empty summary |
| TC-CS-05 | Item with plain language summary populated | Summary included verbatim |
| TC-CS-06 | Compact recommendation payload | Output includes plain language summary |
| TC-CS-07 | Language model disabled | Returns result with plain language summary; no model call made |
| TC-CS-08 | Mock language model JSON with RAAS/ARNI summary | Mapped summary attached to correct drug class |
| TC-CS-09 | Vietnamese or English locale; streamed token or compact payload contains Han script | CJK characters stripped before display |
| TC-CS-10 | Follow-up message after assistant discussed MRA; `build_clinical_state` with prior excerpt | `focus_class_ids` includes MRA/beta_blocker from prior assistant text |

**Implementation file:** `backend/app/tests/test_card_summarizer.py`, `test_explanation.py`

### 4.6.12. Integration Tests — Chat and SSE

**Table 4.13** lists HTTP and SSE integration tests for the chat API: missing-field gates, event ordering on the stream, medication normalization in drafts, conversation history persistence, and multi-question batch handling.

**Table 4.13. Chat and SSE integration test cases**

| TC | Request | Expected |
|----|---------|---------|
| TC-CH-01 | Message with LVEF, eGFR, K, no SBP | HTTP 200; status indicates missing information; missing fields includes systolic blood pressure |
| TC-CH-02 | Same message, stream endpoint | SSE body contains `draft_ready`, `missing_check`, and early `done` (or full recommendation sequence) |
| TC-CH-03 | Nested patient payload with weight | Weight preserved in patient draft |
| TC-CH-04 | Patient taking Entresto and Farxiga | Medications normalized correctly |
| TC-CH-05 | Full chat flow with persistent store patched | History endpoint returns messages after stream completes |
| TC-CH-06 | Two-part question ("start MRA? And SGLT2i?"), stream endpoint | SSE body contains `multi_question_ready`; both sub-questions listed |
| TC-CH-07 | `multi_question_action=stop` after first answer | `pending_multi_question` cleared; flow ends |
| TC-CH-08 | `multi_question_action=continue` after first answer | Next sub-question processed; confirmation footer appended |

**Implementation file:** `backend/app/tests/test_chat.py`

### 4.6.13. Integration Tests — GraphRAG and Verification

**Table 4.14** confirms that a full GraphRAG request returns graph facts and evidence chunks, runs all six verification agents, and produces aggregated verdict and citation status fields.

**Table 4.14. GraphRAG and verification integration test cases**

| TC | Request | Expected |
|----|---------|---------|
| TC-G-01 | HFrEF patient with multiple conditions | HTTP 200; graph facts and evidence chunks non-empty; retrieval sources include relationships and chunks |
| TC-G-02 | Same patient | All six verification agents produce results |
| TC-G-03 | Same patient | Final verdict is pass, warning, or fail |
| TC-G-04 | Same patient | Citation status is strong, weak, or missing |

### 4.6.14. Integration Tests — Admin and Governance

**Table 4.15** maps role-based access, constraint approval, invalid governance transitions, and diff-engine behavior for admin APIs used by the governance portal.

**Table 4.15. Admin and governance integration test cases**

| TC | Action | Expected |
|----|--------|---------|
| TC-AD-01 | Request without token | HTTP 401 |
| TC-AD-02 | Login as clinical lead; get active constraints | HTTP 200; response is a list |
| TC-AD-03 | Login as viewer; get all constraints | HTTP 403 |
| TC-AD-04 | Login as lead; get users | HTTP 403 |
| TC-AD-05 | Bearer token without API key; recommend | HTTP 200; valid recommendation response |
| TC-AD-06 | Login as lead; approve a constraint | HTTP 200; status is approved |
| TC-AD-07 | Attempt invalid status transition | HTTP 400 |
| TC-AD-08 | Diff map with changed field | One change reported with correct path and type |
| TC-AD-09 | Diff map with identical payload | Empty list returned |

**Table 4.16** lists seeded JWT users exercised in auth tests; passwords are shared test secrets with bcrypt hashes loaded at bootstrap.

**Table 4.16. Seeded test users for auth testing**

| Username | Roles | Test purpose |
|----------|-------|-------------|
| lead | clinical_lead | Rule approval, governance read |
| viewer | viewer | Read-only active catalogs only |
| adminonly | admin | Full access including user management |

All seed users use the same test password. Tests verify password verification against seeded bcrypt hashes.

### 4.6.15. Unit Tests — Dose Calculation

**Table 4.17** verifies that label-derived dose rules produce `DosePlan` objects and attach to `RecommendationResponse` with a traceable rules version string.

**Table 4.17. Dose calculation integration test cases**

| TC | Setup | Expected |
|----|-------|---------|
| TC-DC-01 | Patient on enalapril; `build_dose_plans(patient, clinical_state)` | Non-empty plan list; enalapril `plan_id` present |
| TC-DC-02 | Same patient; `build_recommendation()` | Response includes `dose_plans` and `dose_rules_version` matching loaded catalog |

**Implementation file:** `backend/app/tests/test_dose_calculation_integration.py`

### 4.6.16. Unit Tests — Chat Language Detection

**Table 4.18** covers heuristic locale inference applied before intake and card summarization (Chapter 3, §3.4.16).

**Table 4.18. Chat language detection test cases**

| TC | Input message | UI language | Expected resolved locale |
|----|---------------|-------------|-------------------------|
| TC-LG-01 | "Nên dùng ARNI không?" | vi | vi |
| TC-LG-02 | "Should I start ARNI for this patient?" | vi | en |
| TC-LG-03 | "Co nen them beta blocker khong?" (ASCII Vietnamese) | en | vi |
| TC-LG-04 | "What about ARNI?" / "Nên dùng ARNI?" | opposite UI toggle | detected locale wins over UI default |

**Implementation file:** `backend/app/tests/test_chat_language.py`

### 4.6.17. Unit Tests — Question Planner

**Table 4.19** documents multi-question splitting, per-question required fields, LLM skip for obvious single questions, and fallback when the planner model is disabled.

**Table 4.19. Question planner test cases**

| TC | Input | Expected |
|----|-------|---------|
| TC-QP-01 | "MRA or SGLT2i? What about ARNI? Should I add beta blocker?" | `is_multi_question=true`; three `PlannedQuestion` rows; first intent `choice_question`; `egfr` in required fields |
| TC-QP-02 | "What about ARNI?" on patient with active ACEi | `acei_last_dose_hours_ago` in required fields |
| TC-QP-03 | Multi-question message; `question_planner_enabled=false` | Plan source is `fallback`; at least two sub-questions |
| TC-QP-04 | LLM returns one question; rule split finds two | Merged plan preserves rule-based split count |

**Implementation file:** `backend/app/tests/test_question_planner.py`

### 4.6.18. Unit Tests — Missing Fields Gate

**Table 4.20** extends the fail-closed missing-field checker with dose-personalization fields and multi-question prompt context (Chapter 3, §3.4.16).

**Table 4.20. Missing fields gate test cases**

| TC | Patient / intent | Expected |
|----|------------------|---------|
| TC-MF-01 | Dose-adjustment intent; eGFR present; no creatinine | Check status `complete`; creatinine not listed as missing |
| TC-MF-02 | Start-medication intent; eGFR and creatinine both absent | `creatinine` (or renal lab) listed as missing |
| TC-MF-03 | ARNI focus; patient on lisinopril (ACEi) | `acei_last_dose_hours_ago` missing; EN/VI prompt mentions washout |
| TC-MF-04 | Missing eGFR; `question_index=1`, `total_questions=2`, active sub-question text | Prompt contains "question 1/2" and sub-question echo |

**Implementation file:** `backend/app/tests/test_missing_fields.py`

### 4.6.19. Integration Tests — Chat Audit API

**Table 4.21** verifies searchable chat audit records exposed to the admin portal (Chapter 3, §3.4.19).

**Table 4.21. Chat audit API test cases**

| TC | Action | Expected |
|----|--------|---------|
| TC-AU-01 | Admin JWT; `GET /admin/audit/chat?q=ARNI` | HTTP 200; `items[0].event_type` is chat recommendation event; query matches payload |
| TC-AU-02 | Same response item | Payload includes `user_question`, patient snapshot fields, and assistant answer metadata |

**Implementation file:** `backend/app/tests/test_chat_audit_api.py`

## 4.7. Operations and Maintenance

### 4.7.1. Health Monitoring

Health routes expose liveness, readiness, and dependency probes. Liveness confirms the process accepts requests. Readiness confirms startup hydration finished. Dependency checks report PostgreSQL, Redis, ChromaDB, Neo4j, S3, and Ollama connectivity separately so operators can see which subsystem failed. Structured logs include conversation identifiers and stage timings, which later support latency decomposition in evaluation.

### 4.7.2. Backup and Restore

PostgreSQL dumps protect governance catalogs and chat records. Neo4j and Chroma volumes can be snapshotted, but indexes can also rebuild from processed artifacts. Recovery planning therefore treats relational catalogs as primary and vector or graph stores as rebuildable derivatives. That stance matches the authority model used at runtime.

### 4.7.3. Refreshing Medical Knowledge

When FDA labels or guidelines change, operators re-run ingestion from the appropriate step, sync catalogs to PostgreSQL, review draft rules in the admin portal, approve promotions, and reload retrieval indexes. Monitoring borderline LLM call counts during re-ingestion helps detect document-layout drift. Prefer adjusting keyword lexicons or similarity thresholds over disabling borderline review entirely, because the uncertain band exists precisely for unfamiliar headings.

### 4.7.4. Routine Clinical Operations

Day-to-day clinical use needs little pipeline work. Doctors create conversations, chat about cases, inspect cards and evidence, and switch language as needed. Administrators periodically clear retired rules, investigate refinement queues, and confirm that newly approved interactions appear in chat. Separating these roles keeps research engineering work from blocking ordinary clinical demonstration sessions.

## 4.8. Concrete Implementation Details

### 4.8.1. Pipeline Extract Phases in Practice

The extract stage is not a single script. After a knowledge-base foundation produces sections, chunks, entities, and relationships, specialized phases build each catalog family. The constraints phase turns claims into conditional avoid and caution rules. The dose-rules phase builds starting and target dose objects with renal predicates. The dose-safety-warnings phase derives numeric maxima that later flag unsafe planned doses. The interaction-rules phase normalizes drug-pair claims into severity-tagged sets. The GDMT-policies phase encodes four-pillar coverage expectations. A finalize phase validates identifiers, repairs provenance links when needed, and prepares promotion packages for store.

Operators often re-run only one phase. For example, after improving the interaction prompt, they resume from that phase without re-downloading DailyMed or re-embedding every section. Checkpoint files record which step finished, so interrupted overnight jobs continue cleanly. This phased design is what makes a research pipeline operable rather than a one-shot notebook.

### 4.8.2. Example Constraint Rule Shape

A constraint rule stored for runtime evaluation is a structured object, not free text. In simplified form it contains a stable rule identifier, one or more drug or class keys, an action such as avoid or consider with caution, a condition object that may require eGFR below a threshold or potassium above a threshold, a human-readable rationale, provenance pointing to a source chunk, a safety tier, and a governance status such as draft, approved, or retired. The reasoning engine evaluates the condition against the typed patient profile. If the condition matches and the tier is executable, the corresponding recommendation status updates.

This shape is why extraction must emit validated structured data. A beautiful paragraph that says “use caution in renal impairment” is not enough for software. The machine needs a predicate it can test. When extraction cannot build a complete predicate, classification marks the needs_condition_refinement tier so a clinical lead can finish the logic instead of letting a half-rule execute.

### 4.8.3. Chat SSE Payload Sequence

The streaming protocol is easiest to understand as a timeline. After the browser sends a chat request, the server resolves locale from message text, then may emit status frames such as received, planning question, extracting patient, building recommendation, verifying evidence, and generating answer. Structured milestones then appear as typed events. The question plan event carries split sub-questions when the planner runs. The patient draft event carries merged draft and clinical state. The missing check reports whether required fields are absent (with sub-question index when applicable). The multi-question ready event exposes pending batches. If the pipeline continues, recommendation events carry GDMT items, interactions, dose plans, and risk flags. Verification events carry agent verdicts and citation checks. Answer frames append narrative text. A done event closes the turn with the full response object.

The frontend does not wait for the final event to become useful. As soon as recommendations arrive, cards render. That is the practical benefit of streaming compared with a single response at the end of a multi-second pipeline.

### 4.8.4. Parallelism Inside One Chat Turn

Three concurrency tools matter in the chat service. On the first draft of a conversation, question planning and patient intake may run in parallel via `asyncio.gather`. Asynchronous tasks start graph-augmented retrieval while reasoning runs in a worker thread. Thread offload moves synchronous rule evaluation off the event loop. Without thread offload, a long rule scan would block unrelated API requests such as health checks or admin list queries. Without retrieval prefetch, verification would wait for retrieval to start only after reasoning finished, adding avoidable latency. The fork-join point is verification: it awaits both the recommendation object and the prefetched context before streaming safety outcomes.

### 4.8.5. Dose Calculation Module

Dose calculation reads dose rules that describe starting dose, target dose, titration steps, and renal adjustment bands. Given a patient eGFR and a candidate drug, the module selects the matching band and returns a dose plan object for the card panel. If the catalog row is incomplete, the module returns no fabricated number. This honesty is important: evaluation noted dose-rule completeness lagged other catalogs, and the UI must not invent milligram strengths when the governed row is missing.

Dose-safety warnings complement dose plans. They fire when a planned dose exceeds a label-derived maximum for the patient’s renal status. Together, dose plans and dose-safety warnings turn label prose into executable numeric checks.

### 4.8.6. Frontend Conversation and Chat Runtime

The doctor dashboard keeps conversations in client state with optional local persistence. Creating a conversation opens a patient modal, builds an initial welcome message, and selects the new case as active. Selecting another conversation loads its messages into the assistant-ui runtime and may sync history from the backend when available. Clearing messages resets the thread while keeping patient context. Deleting a conversation removes it from the sidebar and selects another case, or reopens the create-patient flow when none remain.

The chat runtime adapter converts between stored message objects and the assistant-ui thread model. When the user sends a message, the adapter posts to the streaming endpoint, applies SSE updates to conversation state, and keeps the clinical panel synchronized. Errors become assistant messages rather than silent failures, so clinicians see that a turn did not complete.

### 4.8.7. Recommendation Display Helpers

Display helpers format recommendation objects for humans. They build short lead sentences, collect shared vital chips such as LVEF, eGFR, potassium, blood pressure, and heart rate, and avoid repeating the same vital on every card. Evidence display helpers repair hyphenation artifacts from PDF extraction, choose readable document titles, and hide technical chunk identifiers from clinician-facing cards. These helpers exist because raw JSON is correct for machines but hostile for busy clinicians.

### 4.8.8. Key API Surfaces

Besides streaming chat, the backend exposes history retrieval for a conversation, health endpoints for operations, evidence search for admin and clinical inspection, and CRUD-style governance routes for each catalog family. Admin routes require JWT authentication and role checks so only authorized clinical leads approve rules. Evidence search returns passages with metadata suitable for the redesigned evidence UI: title, page, publisher, and excerpt rather than internal hashes.

### 4.8.9. Repository Layout Summary

At repository level, the backend directory holds the FastAPI application. The frontend directory holds the clinician dashboard, admin portal, and shared API and display utilities. A scraper directory holds the ingestion pipeline. Infrastructure directory holds Docker Compose, Nginx configuration, and environment templates. Data directories hold local caches and workspace outputs during development. This layout keeps research pipeline code separate from interactive serving code while still sharing clinical vocabulary and identifiers.

## 4.9. End-to-End Implementation Walkthrough

Consider a physician who types: “68-year-old man with HFrEF, LVEF 30%, eGFR 38, potassium 4.9, on lisinopril 10 mg and carvedilol 12.5 mg twice daily. Can we add MRA and SGLT2 inhibitor?”

The request reaches the backend and receives a conversation identifier. Intake patterns capture age, LVEF, eGFR, and potassium. The lexicon maps lisinopril to an ACE inhibitor key and carvedilol to an evidence-based beta blocker key. Clinical state records HFrEF and reduced kidney function. Because potassium and eGFR are present, missing-field checks pass.

Retrieval prefetch begins. Hypothetical document expansion may enrich the short question into a richer passage about MRA initiation and SGLT2 therapy in reduced ejection fraction. Dense search, sparse keyword matching, and graph neighborhood queries run, then reciprocal rank fusion merges candidates. Meanwhile the reasoning engine compares GDMT pillars against current therapy, finds missing MRA and SGLT2 coverage, evaluates potassium and eGFR against MRA constraints, and checks interactions with the active ACE inhibitor. Dose modules attach plans when catalog rows exist.

Verification audits hard blocks and evidence presence. Simplified Vietnamese or English labels attach. The dashboard renders recommendation cards and verification badges, then streams the explanatory answer with evidence snippets in the side panel. If the clinician switches language, cards relabel immediately without repeating retrieval.

If the same physician had omitted potassium, the pipeline would stop after the missing check, ask for the value, and refuse to emit an MRA recommendation based on a guessed electrolyte. That branch is as important as the happy path because it shows fail-closed behavior implemented in code, not only described in design documents.

## 4.10. Lessons From Implementation

Several engineering lessons emerged while building the system. Separating authoritative structured outputs from generative prose is not optional in pharmacotherapy; whenever those layers were temporarily mixed during prototyping, debugging became harder and clinicians lost trust. Governance status fields are as important as extraction quality: a perfect extractor still needs draft, approved, and retired states. Progressive SSE delivery improves usability more than shaving a few hundred milliseconds from total latency, because doctors can act on cards while narrative continues. Bilingual support must begin at intake lexicons and deterministic card maps; translating only the final paragraph leaves drug identity errors untouched. Pipeline checkpointing and artifact buckets turn knowledge construction from a fragile script into an operable process that hospitals can re-run when labels change.

## 4.11. Chapter Summary

This chapter mapped system design to concrete implementation. The ingestion pipeline acquires FDA labels and guidelines, filters sections with a three-tier cascade, extracts governed artifacts across specialized phases, and synchronizes PostgreSQL, ChromaDB, and Neo4j. The FastAPI backend implements the modular monolith. The SSE pipeline encodes Osheroff's timing principle in software: patient drafts arrive before recommendations; structured cards precede narrative. Concurrent design keeps the event loop free for concurrent clinical traffic. Each module has a dedicated test file. Section 4.6 documents pytest specifications for every module in the clinical pipeline, using the same TC identifiers as Chapter 3. Tables 4.3–4.16 cover the baseline pipeline; Tables 4.17–4.21 cover chat language detection, question planning, extended missing-field gates, multi-question SSE, dose-calculation integration, and chat audit search. The test infrastructure uses fixture data and session-level mocking so all 69 test files run without live databases or GPU hardware. The end-to-end walkthrough and implementation lessons show how these pieces cooperate on a real HFrEF vignette. Chapter 5 reports how this implementation behaved under curated evaluation.
