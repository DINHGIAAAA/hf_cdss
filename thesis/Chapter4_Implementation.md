# CHAPTER 4: IMPLEMENTATION AND DEPLOYMENT

## 4.1. Development Environment

Chapter 4 describes how the Chapter 3 designs became working software: evaluation hardware and tools, the pipeline from drug labels and guidelines to searchable knowledge, the FastAPI chat backend, React clinician and admin interfaces, and Docker-based deployment. For each technique, the text states what it does, why it exists, and how operators or clinicians use it.

### 4.1.1. Hardware Configuration

Implementation used ordinary development laptops and one dedicated application server. Development machines need at least eight CPU cores, 16 GB of RAM, and about 100 GB of SSD storage. A graphics processing unit (GPU) is helpful but not required on a laptop because overnight ingestion jobs can run on the CPU. The evaluation and demonstration server used sixteen CPU cores, 32 GB of RAM, a 500 GB SSD, and an NVIDIA RTX 3080 GPU with 10 GB of video memory.

That GPU matters for a practical reason. The system runs a local large language model through Ollama so that clinical vignettes do not need to leave the hospital network. The chosen generation model, Qwen2.5-7B-Instruct, needs enough video memory to answer within a few seconds. The embedding model BGE-M3 also uses the GPU when building or searching dense vector indexes. Without a GPU, chat still works, but latency grows and the sub-ten-second median target becomes harder to meet. The split between CPU-friendly development and GPU-backed interactive chat is therefore intentional: engineers can write and test code on modest laptops, while clinicians evaluate the system on hardware that matches a realistic hospital workstation.

### 4.1.2. Software Stack and Why Each Piece Exists

The backend is written in Python 3.11. Python was chosen because the scientific and medical-informatics ecosystem is mature, asynchronous networking is strong, and typed validation libraries such as Pydantic integrate cleanly with FastAPI. FastAPI is the web framework. It receives HTTP requests, validates JSON against schemas, and streams Server-Sent Events (SSE) to the browser. SSE is a simple one-way stream from server to client. It lets the doctor dashboard show a patient draft and recommendation cards while the conversational answer is still being written, which reduces perceived waiting time.

PostgreSQL 15 stores the governed clinical catalogs: constraint rules, dose rules, interaction rules, GDMT policies, dose-safety warnings, chat history, and audit events. PostgreSQL is used here as the source of truth for safety. Anything that can block or approve therapy must live in a transactional database that administrators can review, approve, or retire.

Redis 7 caches session data, rate-limit counters, and repeated language-model responses. Caching does not replace rules. It only speeds up repeated work such as loading the same constraint slice many times during a busy clinic hour.

Neo4j 5 stores the medical knowledge graph as nodes and relationships. GraphRAG uses Neo4j to answer multi-hop questions such as which drugs interact through a shared pathway. ChromaDB stores dense embeddings of evidence passages so that semantic search can find relevant paragraphs even when the doctor’s wording differs from the label text. LocalStack provides an S3-compatible object store during development. Raw FDA XML files and processed JSONL artifacts land in versioned buckets so pipeline runs remain reproducible.

Ollama hosts local models. Generation uses `qwen2.5:7b` for clinician-facing answers. Lightweight helpers such as HyDE expansion and verification prompts may use a smaller model such as `qwen2.5:1.5b`. Embeddings use `bge-m3`. Keeping inference local supports privacy-sensitive pilots and avoids per-token cloud costs.

The frontend uses Node.js 18 or later, React 18, and Vite. React builds interactive interfaces. Vite packages them quickly for development and production. Nginx sits in front of the stack as a reverse proxy: it serves the doctor dashboard, routes `/admin` to the governance portal, and forwards `/api` and SSE traffic to FastAPI.

### 4.1.3. Environment Setup

Local setup follows a fixed order so developers do not fight missing databases. First the repository is cloned. Next a Python virtual environment is created and backend dependencies are installed from `requirements.txt`. Frontend packages install with `npm` inside the doctor-dashboard directory. Docker Compose then starts PostgreSQL, Redis, Neo4j, ChromaDB, LocalStack, and Ollama. Application settings load from `infrastructure/.env` using names prefixed with `HF_CDSS_` so development, Docker, and pipeline runs share one configuration vocabulary.

After containers are healthy, Ollama pulls the required models once. Model weights persist in a Docker volume, so later restarts do not re-download them. The FastAPI service can then start with Uvicorn. In development, reload mode restarts the API when Python files change. The Vite development server proxies `/api` to the backend so browser code can call the same relative paths used in production.

## 4.2. Knowledge Construction Pipeline

### 4.2.1. Purpose and High-Level Stages

A clinical decision support system is only as trustworthy as its knowledge base. Manually typing thousands of label warnings into a database is slow and error-prone. The ingestion pipeline therefore automates four broad stages: acquire raw sources, load and normalize them, extract structured clinical artifacts, and store those artifacts into PostgreSQL, ChromaDB, and Neo4j.

The orchestrator lives in `scraper/orchestration/run_ingestion_pipeline.py`. Operators can run the full pipeline or resume from a named step such as `kg_base`, `constraints`, `dose_rules`, `interaction_rules`, or `gdmt_policies`. Checkpoints record completed steps so a failed overnight job can continue without repeating successful work. Artifacts publish to the processed S3 bucket while local workspace files remain available for debugging.

Idempotency is a first-class design goal. Content hashes and on-disk LLM response caches under `data/heart_failure/.ingestion_llm_cache/` prevent identical prompts from being sent to the model again during threshold tuning. The flag `HF_CDSS_INGESTION_SKIP_DOWNLOAD=true` lets operators reprocess staged files without hitting DailyMed again. These mechanisms matter because pipeline iteration is frequent during research, and repeated cloud or local LLM calls would otherwise dominate cost and time.

### 4.2.2. Acquisition: Bringing Sources Into the System

Acquisition downloads authoritative documents and stores them unchanged. For FDA Structured Product Labels, `scraper/acquisition/download_sources.py` queries the DailyMed API, resolves a drug name to an SPL set identifier, and downloads the XML label. Guidelines from ESC, AHA/ACC, and HFSA arrive as PDF or HTML according to the sources registry. Interaction supplements may arrive as curated JSON or CSV entries registered alongside labels.

Keeping raw files immutable is deliberate. If a later parsing bug is discovered, operators can re-parse the same bytes without guessing whether the upstream website changed. Asynchronous HTTP with `httpx` downloads many labels concurrently, which shortens wall-clock time when the manifest contains dozens of GDMT-relevant agents.

A practical limitation appears when local brand names or synonym spellings are missing from the acquisition registry. DailyMed then cannot resolve the product, and that drug never enters extraction. This gap is the same Vietnamese synonym problem later observed in chat intake evaluation. The implementation records registry coverage so operators know which agents still need mapping.

### 4.2.3. Loading and Document Processing

After acquisition, load and transform stages turn binaries into sectioned text. XML labels are parsed with section awareness so FDA headings such as dosage, warnings, contraindications, and drug interactions remain identifiable. PDF guidelines use layout-aware text extraction. HTML guidelines are cleaned of navigation chrome before section segmentation.

Each section receives a stable identifier, document provenance, and length statistics. Stable identifiers later connect a runtime citation back to the exact source passage a clinician can open. Drug names normalize toward RxNorm-style keys when possible. Laboratory units convert to canonical forms so a rule written against mmol/L potassium can compare fairly with patient values extracted from chat.

### 4.2.4. Chunking for Retrieval

Chunking splits long sections into passages suitable for vector search. The chunker in `scraper/transform/chunk_sections.py` uses a sentence-aware window of about 512 tokens with overlap. It accumulates whole sentences until the budget is nearly full, then carries the last sentences into the next chunk. Overlap exists because a contraindication often spans two sentences: the first names the drug, the second states the lab threshold. A hard cut between those sentences would leave each chunk incomplete.

Good chunks improve GraphRAG later. Dense retrieval ranks passages by meaning. Sparse BM25 ranks passages by exact words. Both need coherent local context. Overly large chunks dilute relevance. Overly small chunks lose conditional language. The 512-token overlapping window is the engineering compromise used throughout evaluation.

### 4.2.5. Three-Tier Section Filtering

Not every section in a drug label is clinically useful for heart-failure decision support. Storage instructions and packaging details rarely help GDMT reasoning. Sending every section to a language model would be expensive and slow. The section filter in `scraper/semantic/section_filter.py` therefore applies three tiers.

Tier one matches high-value headings with keywords such as dosage, warnings, contraindications, and drug interactions. Matching sections are kept immediately. Tier two embeds the title and opening text with BGE-M3 and compares them to prototype vectors for clinical section types. Scores at or above 0.52 are kept. Tier three reviews only the uncertain band from 0.40 to 0.52 with a short LLM keep-or-drop prompt. Scores below 0.40 drop without an LLM call. A hard cap of 400 borderline LLM calls per run bounds worst-case spend.

This cascade is the offline twin of hybrid chat intake. Fast deterministic methods handle clear cases. Embeddings handle paraphrases. The language model spends budget only where uncertainty is real. In evaluation, the filter retained about 95 percent of sections while invoking borderline LLM review on only about 6.6 percent of inputs.

### 4.2.6. Extraction of Structured Clinical Artifacts

Extraction converts kept text into objects the runtime can evaluate. Several specialized builders cooperate. Constraint rule extraction produces conditional avoid and caution statements. Dose rule extraction captures starting doses, target doses, renal bands, and titration schedules. Interaction extraction builds drug-set pairs with severity and management text. GDMT policy extraction encodes four-pillar coverage expectations for HFrEF. Dose-safety warning extraction captures label maxima that should fire when a planned dose exceeds safe limits for the patient’s renal band.

The hybrid strategy is regex first, LLM second. High-frequency SPL phrasing is cheap to match with patterns. When patterns are sparse, `scraper/semantic/rule_builder.py` calls the local Ollama chat API with a JSON schema validated by Pydantic. Invalid JSON is rejected before it enters the artifact stream. Prompt hashes feed the ingestion cache so identical sections do not re-spend tokens on every rerun.

Named entity recognition and relation linking attach drugs, classes, labs, and conditions to each claim. Evidence linking stores chunk identifiers so a later recommendation card can show the passage that motivated a rule. Deduplication collapses near-identical extractions from overlapping label sections.

### 4.2.7. Classification and Governance Gates

Classification assigns deployability before rules reach clinicians. Safety tiers include `hard_block` for absolute contraindications, `usable_rules` for complete executable conditions, and `needs_condition_refinement` for drafts that parse but still need human clarification. Action types include avoid, consider with caution, consider, and continue. These labels map directly to recommendation card badges in the doctor dashboard.

Rules marked for refinement sync into PostgreSQL for admin review rather than disappearing. Runtime loaders ignore unfinished drafts until a clinical lead promotes them. This gate is essential. Automated extraction is powerful, but heart-failure safety cannot depend on unreviewed model guesses.

### 4.2.8. Synchronization to Runtime Stores

The store stage upserts approved and draft catalogs into PostgreSQL, publishes processed JSONL to S3, and prepares artifacts for ChromaDB and Neo4j hydration. Backend bootstrap can pull processed artifacts on startup so a fresh container does not need to re-scrape DailyMed. Operators can also rebuild graph and vector indexes from `kg_base` without repeating acquisition when only embeddings or relationships need refresh.

PostgreSQL remains authoritative for executable rules. ChromaDB and Neo4j enrich explanation and verification. Redis is never treated as the long-term home of clinical truth. That separation keeps audit trails and admin workflows centered on one relational catalog.

## 4.3. Backend Implementation

### 4.3.1. Modular Monolith Layout

The backend is a modular monolith: one FastAPI process, many internal modules with clear boundaries. `app/main.py` wires routes and startup tasks. Domain packages under `app/modules/` include chat orchestration, clinical intake extraction, constraint building, dose calculation, dose safety, GraphRAG, reasoning, verification agents, explanation helpers, and datastore adapters. Schemas under `app/schemas/` define the contracts shared by SSE payloads, database mappings, and frontend TypeScript-facing JSON.

This layout matches Chapter 3 requirements. Intake owns patient profile analysis. Reasoning owns GDMT and interaction decisions. Dose modules own titration plans. Constraint and dose-safety modules own alerts. GraphRAG owns evidence assembly. Explanation modules own bilingual card labels and narrative generation. Datastore adapters isolate SQL, Redis, Chroma, and Neo4j details so clinical logic stays readable.

### 4.3.2. Chat Orchestration and SSE Event Order

The streaming chat entry point is `stream_chat` in `app/modules/chat/service.py`. It turns one clinician message into an ordered series of SSE events. The order is intentional and clinically meaningful.

First the service emits a status event acknowledging receipt and ensuring a conversation identifier exists. It appends the user message to history. It then extracts patient facts from the new message, merges them with any prior draft for that conversation, and builds a clinical state object that normalizes units and derives missing eGFR when creatinine, age, and sex are available. The merged draft is saved and streamed as `draft_ready`.

Next a missing-field checker decides whether critical labs are absent for the inferred intent. If potassium is missing and an MRA decision is in scope, the pipeline short-circuits. It asks for the missing value instead of guessing. That behavior protects patients from silent unsafe recommendations.

When required fields are present, GraphRAG prefetch starts as an asynchronous task while deterministic recommendation building runs in a worker thread. The thread offload keeps the FastAPI event loop free for other API traffic during PostgreSQL rule evaluation. After both complete, verification agents audit the recommendation against hard blocks and retrieved evidence. Plain-language summaries and deterministic simplified card fields attach next. The service then emits `recommendation_ready` and `verification_ready` before generating the conversational answer.

Answer generation streams `answer_delta` tokens grounded in the verified recommendation object. It does not invent a new dose status. A final `done` event carries the complete response payload for clients that prefer one snapshot at the end.

This implementation encodes Osheroff’s timing principle in software: critical structured information arrives before narrative prose finishes.

### 4.3.3. Hybrid Clinical Intake

Clinical intake converts messy chat into typed fields. Regular expressions capture numeric patterns such as “EF 30%”, “eGFR 45”, and “K+ 4.2”. Lexicons map medication strings, including Vietnamese aliases and brand names, onto internal drug keys. Negation handling prevents “not on ACE inhibitor” from becoming an active medication. Unit normalization converts related lab expressions into comparable values.

When regex confidence is low, a selective LLM extraction path proposes additional fields. Merge prefers measured regex values over model proposals. That preference is a clinical epistemology encoded in code: instrument-like numbers beat probabilistic guesses. Conversation history can also contribute previously stated facts so multi-turn chat accumulates a profile instead of forcing the doctor to retype everything.

Attachments such as pasted notes or uploaded text files append to the extraction message. Clinical documents provided in the request merge into the patient object when present. The result is a `PatientProfile` rich enough for rule evaluation yet still traceable to the words the clinician typed.

### 4.3.4. Deterministic Reasoning Engine

The reasoning service builds a structured recommendation object from PostgreSQL catalogs. It evaluates GDMT class coverage for ACE inhibitor or ARB or ARNI, beta blocker, MRA, and SGLT2 inhibitor. For each class it assigns a status such as start, continue, caution, or avoid. Constraint rules match patient risk flags and labs. Interaction rules compare normalized medication sets. Dose rules produce starting and target plans when the catalog contains complete rows for the agent and renal band.

No language model sits inside this critical path. Reproducibility and auditability require that the same patient state yield the same structured statuses. GraphRAG may later explain why a status appeared, but it cannot flip a hard block to an approval.

### 4.3.5. GraphRAG Service Implementation

GraphRAG assembly lives mainly in `app/modules/graphrag/service.py` with helpers for HyDE expansion, query decomposition, BM25 indexing, RRF fusion, and optional reranking.

Query construction collects terms from the clinician message, the patient profile, and clinical state. If the query is short or ambiguous, HyDE may generate a hypothetical answer document and embed that document instead of the raw short question. The purpose is vocabulary bridging: a physician typing “Start MRA?” should still retrieve passages that discuss spironolactone, eplerenone, potassium, and renal monitoring.

Dense retrieval queries ChromaDB for nearest evidence chunks. Sparse BM25 retrieval favors exact drug names and regulatory phrases. Neo4j neighborhood queries gather multi-hop graph facts around matched drugs and conditions. Reciprocal Rank Fusion merges the ranked lists with a stable formula that rewards passages appearing highly in more than one list. Optional semantic reranking can reorder the fused top candidates when latency budgets allow.

Metadata filters may restrict candidates by drug class or chunk type when clinical state already focuses the conversation. Quality scoring and evidence filtering remove weak or off-scope chunks before they reach the explanation model. Citation helpers attach source links so the Evidence panel can open DailyMed or guideline pages.

BM25 indexes rebuild in memory on backend startup from published chunk metadata. That choice favors low query latency over continuous incremental updates. After a knowledge refresh, restarting or reloading the backend rebuilds the sparse index from the new artifacts.

### 4.3.6. Verification Agents

Verification runs after recommendation and GraphRAG complete. Agents check consistency questions that neither rules nor retrieval alone fully cover. Does a hard block fire while the narrative would sound permissive? Did retrieval return any evidence for cited claims? Do recommended drugs match the normalized medication list? Lightweight models may assist with phrasing checks, but fail-closed hard blocks still come from deterministic catalogs.

Verification results stream to the UI as badges and structured payloads. They give clinicians a second signal besides the recommendation cards themselves.

### 4.3.7. Card Summarizer and Answer Generation

The card summarizer maps structured fields to Vietnamese and English plain-language labels without calling an LLM. Drug class codes become readable phrases. Status codes become badge text. Because this mapping is deterministic, cards stay stable across language switches and do not flicker when narrative tone changes.

Answer generation then writes a clinician-facing explanation grounded in the verified recommendation and retrieved evidence. Streaming tokens update the chat thread. The architectural rule remains constant: cards and safety statuses are authoritative; prose is explanatory.

### 4.3.8. Persistence, Caching, and Audit

Patient drafts, messages, and recommendation artifacts persist through datastore adapters. Redis can cache drafts and idempotent responses so repeated identical requests do not recompute everything. Audit events record missing-field stops, recommendation outcomes, and governance actions. These logs support later clinical review and debugging without reading raw application logs alone.

## 4.4. Frontend Implementation

### 4.4.1. Application Structure

The frontend monorepo under `frontend/` contains the doctor dashboard, the admin portal, and shared packages for API clients and display helpers. The doctor dashboard is the primary clinical surface. It includes chat runtime components, a clinical side panel, conversation sidebar controls, evidence browsing, and bilingual message catalogs.

State for conversations can persist locally so a clinician can return to a case. Creating a conversation captures a patient name and opens a welcome message. Deleting or clearing a conversation removes local history and returns the UI to a clean case setup when needed. These controls sound small, but they matter for usability during demonstrations and multi-case review sessions.

### 4.4.2. SSE Client and Progressive Rendering

The client module that consumes chat streams parses SSE frames and dispatches them by event type. When `draft_ready` arrives, the clinical panel can show extracted vitals and medications. When `recommendation_ready` arrives, GDMT cards render. When `verification_ready` arrives, verification badges update. Answer tokens append to the assistant message as they stream.

Progressive rendering is not cosmetic. It implements the same safety-first ordering as the backend. A doctor can begin reading structured advice before the full paragraph finishes, which is valuable on rounds where seconds matter.

### 4.4.3. Clinical Panel and Evidence Cards

The clinical panel shows patient context, recommendation cards, dose plans when available, and evidence snippets. Recommendation cards bind only to structured fields and simplified labels. They never infer avoid or continue status from free-text tokens. Evidence cards emphasize human-readable document titles, page numbers, publishers, and excerpts rather than technical chunk identifiers. “Open source” links take the clinician to the original label or guideline when a URL is present.

### 4.4.4. Language Switching

`LanguageProvider` stores the preferred locale, updates accessibility attributes, and supplies translation functions to components. Switching between Vietnamese and English regenerates card labels and UI chrome. Conversation identifiers and structured patient state remain unchanged. Because simplification is deterministic and cheap, language switching stays under two seconds in evaluation without re-running GraphRAG or reasoning.

### 4.4.5. Admin Portal Implementation

The admin portal exposes governance tables for constraints, dose rules, interactions, GDMT policies, and related catalogs. Clinical leads can open a record, inspect provenance, refine conditions, approve usable rules, or retire outdated ones. Evidence search pages help reviewers inspect retrieved passages during catalog curation. Sticky action columns and short display labels reduce visual clutter so reviewers focus on clinical meaning rather than raw identifiers.

Admin workflows close the loop with the ingestion pipeline. Extraction can draft thousands of rules, but only approved executable tiers affect chat recommendations. That human gate is part of the implementation, not an afterthought.

### 4.4.6. Admin Approve and Retire Flow

When a clinical lead opens a draft constraint in the admin portal, the UI shows the condition object, rationale, linked evidence, and current governance status. Approving the record updates PostgreSQL and can invalidate Redis caches that held older catalog slices. Retiring a rule keeps historical rows for audit but removes them from runtime loaders. Editing a condition may move a rule from `needs_condition_refinement` to `usable_rules` after validation. These operations sound administrative, yet they are the operational heart of maintainability: the chat service never needs a code deploy merely because a label added a new potassium warning.

Version diffs and detail panes help reviewers see what changed between pipeline runs. Condition panels surface structured predicates that would otherwise hide inside JSON. Catalog list pages use short clinical titles with technical identifiers kept secondary so reviewers scan by drug and action rather than by hash strings.

### 4.4.7. Shared Packages and API Clients

Shared frontend packages centralize HTTP helpers, evidence display formatting, and governance field rendering. Doctor and admin apps therefore show consistent labels for the same underlying catalogs. API clients encode paths such as chat stream, history, evidence search, and admin list endpoints once, reducing duplicated fetch logic and making authentication headers consistent across pages.

## 4.5. System Deployment

### 4.5.1. Docker Compose Topology

Docker Compose orchestrates PostgreSQL, Redis, Neo4j, ChromaDB, Ollama, LocalStack, the FastAPI backend, frontend services, and Nginx. Health checks delay backend startup until databases and model services are ready. GPU passthrough to the Ollama container is configured on hosts with the NVIDIA Container Toolkit.

Each service has a clear job. PostgreSQL persists governed truth. Redis accelerates hot reads. Neo4j answers relationship queries. ChromaDB answers semantic passage queries. Ollama runs embeddings and generation. LocalStack stores raw and processed artifacts. The backend performs clinical orchestration. Frontends present doctor and admin workflows. Nginx unifies access through one host port.

Compose was chosen over Kubernetes for the evaluation scale. A single-host pilot serving on the order of tens of concurrent users does not justify Kubernetes operational overhead. The modular monolith can later split GraphRAG or Ollama into separate services if load profiles demand it.

Volumes persist database files, model weights, and object-store data across restarts. Without volumes, every Compose reboot would force model re-downloads and empty catalogs, which is unacceptable for iterative clinical demos.

### 4.5.2. Nginx Routing

Nginx terminates HTTP and routes by path. The doctor dashboard is served at the site root. The admin portal is served under `/admin`. API and SSE traffic under `/api` proxy to FastAPI with buffering disabled so streams flush promptly. A single origin simplifies browser security by avoiding cross-origin complexity in production.

### 4.5.3. Configuration Management

Thresholds and model names live in environment variables. Examples include database URLs, Redis URLs, Ollama base URL, generation and embedding model names, Neo4j credentials, Chroma host, S3 endpoint and bucket names, JWT secrets, CORS origins, section-filter similarity thresholds, borderline LLM enablement, and retrieval top-k settings. Operators can tune cost and quality without editing Python source. This is important when a new guideline PDF uses unfamiliar headings and section-filter thresholds need adjustment.

### 4.5.4. Deployment Trade-offs

Local Ollama was preferred over cloud LLM APIs to keep vignettes on premises, control latency, and avoid per-token fees. The trade-off is GPU capital cost and model operations. LocalStack was preferred over cloud S3 during development for identical SDK behavior without cloud accounts. Production can switch to MinIO or AWS S3 without changing artifact layout. Neo4j Community and ChromaDB co-locate with the stack so embeddings and graph facts remain under institutional control; disaster recovery rebuilds indexes from processed S3 artifacts when needed.

## 4.6. Testing

### 4.6.1. Testing Philosophy

Testing follows the hybrid architecture. Deterministic modules must pass without depending on model randomness. Generative components are mocked in continuous integration so GPU hardware is not required for every pull request. Clinical accuracy still needs cardiologist review, reported in Chapter 5, because vignette judgment is not fully automatable.

### 4.6.2. Unit Tests

Unit tests cover card summarizer mappings, intake merge preference for measured values, negation detection, eGFR derivation, constraint matching, dose renal-band selection, RRF ranking invariants, and JWT role checks on admin routes. These tests fail fast when a safety mapping or merge policy changes accidentally.

### 4.6.3. Integration Tests

Integration tests drive the chat pipeline with mocked Ollama responses. They assert that a typical HFrEF vignette produces a patient draft and recommendation, that SSE events arrive in the required order, and that missing potassium suppresses recommendation emission when MRA evaluation is required. GraphRAG tests use fixture embeddings to verify fusion and filtering behavior.

### 4.6.4. Pipeline Tests

Ingestion tests check section-filter tier boundaries, hard-block classification for ACE inhibitor and ARNI washout patterns, PostgreSQL upsert idempotency, and cache invalidation after admin approval. A data-quality report compares catalog counts with golden baselines so silent pipeline regressions become visible.

### 4.6.5. Frontend Tests

Frontend tests cover SSE frame parsing, language preference persistence, and recommendation card fallbacks when simplified fields are absent. Recorded SSE fixtures replay progressive panel updates without a live backend.

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

The extract stage is not a single script. After a knowledge-base foundation (`kg_base`) produces sections, chunks, entities, and relationships, specialized phases build each catalog family. The constraints phase turns claims into conditional avoid and caution rules. The dose-rules phase builds starting and target dose objects with renal predicates. The dose-safety-warnings phase derives numeric maxima that later flag unsafe planned doses. The interaction-rules phase normalizes drug-pair claims into severity-tagged sets. The GDMT-policies phase encodes four-pillar coverage expectations. A finalize phase validates identifiers, repairs provenance links when needed, and prepares promotion packages for store.

Operators often re-run only one phase. For example, after improving the interaction prompt, they resume from `interaction_rules` without re-downloading DailyMed or re-embedding every section. Checkpoint files record which step finished, so interrupted overnight jobs continue cleanly. This phased design is what makes a research pipeline operable rather than a one-shot notebook.

### 4.8.2. Example Constraint Rule Shape

A constraint rule stored for runtime evaluation is a structured object, not free text. In simplified form it contains a stable rule identifier, one or more drug or class keys, an action such as avoid or consider with caution, a condition object that may require eGFR below a threshold or potassium above a threshold, a human-readable rationale, provenance pointing to a source chunk, a safety tier, and a governance status such as draft, approved, or retired. The reasoning engine evaluates the condition against the typed patient profile. If the condition matches and the tier is executable, the corresponding recommendation status updates.

This shape is why extraction must emit JSON that passes Pydantic validation. A beautiful paragraph that says “use caution in renal impairment” is not enough for software. The machine needs a predicate it can test. When extraction cannot build a complete predicate, classification marks `needs_condition_refinement` so a clinical lead can finish the logic instead of letting a half-rule execute.

### 4.8.3. Chat SSE Payload Sequence

The streaming protocol is easiest to understand as a timeline. After the browser sends a chat request, the server may emit status frames such as received, extracting patient, building recommendation, verifying evidence, and generating answer. Structured milestones then appear as typed events. `draft_ready` carries the merged patient draft and clinical state. `missing_check` reports whether required fields are absent. If the pipeline continues, `recommendation_ready` carries GDMT items, interactions, dose plans, and risk flags. `verification_ready` carries agent verdicts and citation checks. `answer_delta` frames append narrative text. `done` closes the turn with the full response object.

The frontend does not wait for `done` to become useful. As soon as `recommendation_ready` arrives, cards render. That is the practical benefit of SSE compared with a single JSON response at the end of a multi-second pipeline.

### 4.8.4. Parallelism Inside One Chat Turn

Two concurrency tools matter in the chat service. First, `asyncio.create_task` starts GraphRAG while reasoning runs. Second, `asyncio.to_thread` moves synchronous PostgreSQL rule evaluation off the event loop. Without the thread offload, a long rule scan would block unrelated API requests such as health checks or admin list queries. Without GraphRAG prefetch, verification would wait for retrieval to start only after reasoning finished, adding avoidable latency. The fork-join join point is verification: it awaits both the recommendation object and the prefetched GraphRAG context before streaming safety outcomes.

### 4.8.5. Dose Calculation Module

Dose calculation reads JSONB dose rules that describe starting dose, target dose, titration steps, and renal adjustment bands. Given a patient eGFR and a candidate drug, the module selects the matching band and returns a dose plan object for the card panel. If the catalog row is incomplete, the module returns no fabricated number. This honesty is important: evaluation noted dose-rule completeness lagged other catalogs, and the UI must not invent milligram strengths when the governed row is missing.

Dose-safety warnings complement dose plans. They fire when a planned dose exceeds a label-derived maximum for the patient’s renal status. Together, dose plans and dose-safety warnings turn label prose into executable numeric checks.

### 4.8.6. Frontend Conversation and Chat Runtime

The doctor dashboard keeps conversations in client state with optional local persistence. Creating a conversation opens a patient modal, builds an initial welcome message, and selects the new case as active. Selecting another conversation loads its messages into the assistant-ui runtime and may sync history from the backend when available. Clearing messages resets the thread while keeping patient context. Deleting a conversation removes it from the sidebar and selects another case, or reopens the create-patient flow when none remain.

The chat runtime adapter converts between stored message objects and the assistant-ui thread model. When the user sends a message, the adapter posts to the streaming endpoint, applies SSE updates to conversation state, and keeps the clinical panel synchronized. Errors become assistant messages rather than silent failures, so clinicians see that a turn did not complete.

### 4.8.7. Recommendation Display Helpers

Display helpers format recommendation objects for humans. They build short lead sentences, collect shared vital chips such as LVEF, eGFR, potassium, blood pressure, and heart rate, and avoid repeating the same vital on every card. Evidence display helpers repair hyphenation artifacts from PDF extraction, choose readable document titles, and hide technical chunk identifiers from clinician-facing cards. These helpers exist because raw JSON is correct for machines but hostile for busy clinicians.

### 4.8.8. Key API Surfaces

Besides streaming chat, the backend exposes history retrieval for a conversation, health endpoints for operations, evidence search for admin and clinical inspection, and CRUD-style governance routes for each catalog family. Admin routes require JWT authentication and role checks so only authorized clinical leads approve rules. Evidence search returns passages with metadata suitable for the redesigned evidence UI: title, page, publisher, and excerpt rather than internal hashes.

### 4.8.9. Repository Layout Summary

At repository level, `backend/` holds the FastAPI application. `frontend/doctor-dashboard/` holds the clinician UI. `frontend/admin/` holds governance screens. `frontend/shared/` holds shared API and display utilities. `scraper/` holds the ingestion pipeline. `infrastructure/` holds Docker Compose, Nginx, and environment templates. `data/heart_failure/` holds local caches and workspace outputs during development. This layout keeps research pipeline code separate from interactive serving code while still sharing clinical vocabulary and identifiers.

## 4.9. End-to-End Implementation Walkthrough

Consider a physician who types: “68-year-old man with HFrEF, LVEF 30%, eGFR 38, potassium 4.9, on lisinopril 10 mg and carvedilol 12.5 mg twice daily. Can we add MRA and SGLT2 inhibitor?”

The request reaches FastAPI and receives a conversation identifier. Intake regexes capture age, LVEF, eGFR, and potassium. The lexicon maps lisinopril to an ACE inhibitor key and carvedilol to an evidence-based beta blocker key. Clinical state records HFrEF and reduced kidney function. Because potassium and eGFR are present, missing-field checks pass and the UI receives `draft_ready`.

GraphRAG prefetch begins. HyDE may expand the short question into a richer hypothetical passage about MRA initiation and SGLT2 therapy in reduced ejection fraction. Dense search, BM25, and Neo4j neighborhood queries run, then RRF merges candidates. Meanwhile the reasoning engine compares GDMT pillars against current therapy, finds missing MRA and SGLT2 coverage, evaluates potassium and eGFR against MRA constraints, and checks interactions with the active ACE inhibitor. Dose modules attach plans when catalog rows exist.

Verification audits hard blocks and evidence presence. Simplified Vietnamese or English labels attach. The dashboard renders recommendation cards and verification badges, then streams the explanatory answer with evidence snippets in the side panel. If the clinician switches language, cards relabel immediately without repeating retrieval.

If the same physician had omitted potassium, the pipeline would stop after `missing_check`, ask for the value, and refuse to emit an MRA recommendation based on a guessed electrolyte. That branch is as important as the happy path because it shows fail-closed behavior implemented in code, not only described in design documents.

## 4.10. Lessons From Implementation

Several engineering lessons emerged while building the system. First, separating authoritative structured outputs from generative prose is not optional in pharmacotherapy. Whenever those layers were temporarily mixed during prototyping, debugging became harder and clinicians lost trust. Second, governance status fields are as important as extraction quality. A perfect extractor still needs draft, approved, and retired states. Third, progressive SSE delivery improves usability more than shaving a few hundred milliseconds from total latency, because doctors can act on cards while narrative continues. Fourth, bilingual support must begin at intake lexicons and deterministic card maps; translating only the final paragraph leaves drug identity errors untouched. Fifth, pipeline checkpointing and artifact buckets turn knowledge construction from a fragile script into an operable process that hospitals can re-run when labels change.

## 4.11. Chapter Summary

This chapter mapped system design to concrete implementation in greater depth. The ingestion pipeline acquires FDA labels and guidelines, filters sections with a three-tier cascade, extracts governed artifacts across specialized phases, and synchronizes PostgreSQL, ChromaDB, and Neo4j. The FastAPI backend orchestrates hybrid intake, deterministic reasoning, dose calculation, GraphRAG retrieval, verification, and SSE streaming so structured safety outcomes appear before narrative text. The React doctor dashboard and admin portal turn those events into clinical and governance workflows, including conversation management, evidence display, and language switching. Docker Compose, Nginx, environment configuration, testing, and operational procedures make the stack reproducible on modest hospital hardware. The walkthrough and implementation lessons show how these pieces cooperate on a real HFrEF vignette. Chapter 5 reports how this implementation behaved under curated evaluation.
