# CHAPTER 4: IMPLEMENTATION AND DEPLOYMENT

## 4.1. Development Environment

### 4.1.1. Hardware Configuration

The implementation was carried out on development workstations and a dedicated application server sized to support local large-language-model inference, vector embedding generation, and concurrent clinical chat sessions. Development machines require sufficient CPU parallelism for pipeline orchestration and frontend hot-reload, while production deployment additionally depends on GPU-backed Ollama containers for BGE-M3 embedding and Qwen2.5 generation without external API dependency.

**Minimum Requirements:**

| Component | Development Machine | Server |
|-----------|---------------------|--------|
| CPU | 8 cores | 16 cores |
| RAM | 16 GB | 32 GB |
| Storage | 100 GB SSD | 500 GB SSD |
| GPU | Optional | NVIDIA GPU (8GB VRAM) |

Development machines require at least eight CPU cores, 16 GB RAM, and 100 GB SSD storage, with GPU optional. Production servers target 16 cores, 32 GB RAM, 500 GB SSD, and an NVIDIA GPU with at least 8 GB VRAM for local LLM inference. The server configuration used in evaluation (Chapter 5) employed a 16-core CPU, 32 GB RAM, 500 GB SSD, and an NVIDIA RTX 3080 with 10 GB VRAM, which comfortably hosted Qwen2.5-7B-Instruct alongside BGE-M3 embedding workloads within the Docker Compose stack described in Section 4.5.

The hardware split between development and production reflects a deliberate cost strategy: ingestion pipeline development and unit testing can proceed on CPU-only laptops because BGE-M3 embedding during batch ingestion is amortized over hours, whereas interactive chat requires sub-10-second responses that GPU-accelerated Ollama inference makes achievable. The RTX 3080's 10 GB VRAM accommodates Qwen2.5-7B in quantized form with headroom for concurrent embedding requests during GraphRAG query-time encoding, a configuration validated by the 8.1-second mean end-to-end latency reported in Section 5.3.2.

### 4.1.2. Required Software

The backend is implemented in Python 3.11 or later and relies on FastAPI for asynchronous HTTP and Server-Sent Events (SSE) delivery via `sse-starlette`, Pydantic for request/response validation and structured LLM output schemas, and SQLAlchemy-compatible drivers for PostgreSQL governance catalogs. PostgreSQL 15 or later stores constraint rules, dose rules, GDMT policies, interaction rules, and audit logs. Redis 7 or later provides session caching, rate-limit counters, and idempotent LLM response caching. Neo4j 5 Community Edition holds the clinical knowledge graph consumed by GraphRAG neighborhood traversal. ChromaDB stores dense evidence embeddings indexed with BGE-M3 (1024 dimensions). Ollama serves both the embedding model (`bge-m3`) and generation models (`qwen2.5:7b` for explanation, `qwen2.5:1.5b` for lightweight verification agents). The ingestion pipeline uses `httpx` for asynchronous HTTP acquisition and the AWS SDK against LocalStack S3 for raw and processed artifact staging.

The frontend requires Node.js 18 or later, npm or pnpm, React 18, and Vite as the development server and production bundler. Infrastructure dependencies include Docker, Docker Compose, and Nginx as a reverse proxy terminating HTTP and forwarding `/api` traffic to the FastAPI backend while serving the doctor dashboard and admin portal as static or proxied frontends.

Python 3.11 was selected for its improved asyncio performance and structural pattern matching utilities used in intake parsing. FastAPI's native async support enables the fork-join parallelism between GraphRAG prefetch and deterministic reasoning described in Chapter 3. Pydantic v2 models enforce JSON schema validation on LLM structured outputs during ingestion, a critical guardrail preventing malformed extraction artifacts from entering PostgreSQL catalogs.

### 4.1.3. Environment Setup

Local development follows a staged bootstrap: clone the monorepo, create an isolated Python virtual environment for the backend, install frontend dependencies for the doctor dashboard, and start core infrastructure containers before launching application services natively or within Compose.

```bash
# Clone repository
git clone https://github.com/your-repo/hf-cdss.git
cd hf-cdss

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend/doctor-dashboard
npm install

# Start infrastructure
cd ../infrastructure
docker-compose up -d postgres redis neo4j chromadb localstack ollama
```

After cloning the repository, developers create a Python virtual environment for the backend, install frontend dependencies, and start PostgreSQL, Redis, Neo4j, ChromaDB, LocalStack S3, and Ollama via Docker Compose before running application services locally. Environment variables governing section-filter thresholds, embedding dimensions, and S3 bucket names are loaded from `infrastructure/.env` (see Section 4.5.3), ensuring that development, Docker, and Airflow-orchestrated pipeline runs share consistent configuration keys prefixed with `HF_CDSS_`.

The staged bootstrap separates infrastructure longevity from application iteration: datastore containers persist across backend code changes, while `uvicorn --reload` enables hot reload during chat service development. Ollama model pulls (`ollama pull qwen2.5:7b`, `ollama pull bge-m3`) occur once per machine and are cached in the `ollama_data` Docker volume.

## 4.2. Knowledge Construction Pipeline Architecture

### 4.2.1. Pipeline Overview

The knowledge construction pipeline is an automated, idempotent system that extracts, processes, classifies, and synchronizes medical knowledge from heterogeneous raw sources into PostgreSQL governance catalogs, ChromaDB vector indexes, and Neo4j graph stores consumed at query time by GraphRAG. Pipeline orchestration is implemented in `scraper/orchestration/run_ingestion_pipeline.py` and may be invoked manually from the command line or scheduled through an optional Airflow profile within Docker Compose. Each stage emits versioned JSONL artifacts to LocalStack S3 (`hf-cdss-raw` for raw downloads, `hf-cdss-processed` for normalized outputs), enabling reproducible re-runs and backend startup hydration without re-scraping upstream sources.

The pipeline applies a deliberate separation of concerns across acquisition (I/O-bound HTTP/S3 staging), deterministic parsing and chunking (CPU-bound NLP preprocessing), semantic filtering and extraction (embedding and LLM-assisted structured parsing), and classification (rule-based safety labeling before human-governed sync). This architecture ensures that expensive LLM calls are reserved for ambiguous sections and sparse regex extractions rather than applied uniformly across all document content.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE PIPELINE ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────────────────┘

Data Sources                    Pipeline Steps                    Output
─────────────                   ─────────────                    ──────

FDA Drug Labels                 ┌─────────────┐
  (XML/SPL)                    │  Acquisition │  Raw Data
         │                     └──────┬──────┘        ↓
         └──────────────────────────▶│             ┌─────────┐
                                    │             │  JSONL  │
Guidelines (PDF/HTML)              │             │  Files  │
         │                         │             └────┬────┘
         └────────────────────────▶├─────────────────┘
                                    │
                                    ▼
                              ┌─────────────┐
                              │  Processing  │
                              │  & Chunking  │────────▶ Chunks
                              └──────┬──────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │  Extraction  │────────▶ Extracted Rules
                              │  & Matching   │
                              └──────┬──────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │ Classification│────────▶ Classified Rules
                              │  & Validation │
                              └──────┬──────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │   Sync to    │────────▶ PostgreSQL
                              │  Postgres    │         Neo4j / Chroma
                              └─────────────┘
```

Raw data from FDA drug labels and clinical guidelines flows through acquisition, processing and chunking, extraction and matching, classification and validation, and finally synchronization to PostgreSQL, with parallel indexing into ChromaDB (dense retrieval) and Neo4j (entity-relation graph). The `--from-step kg_base` re-sync entry point (Section 4.7.3) allows operators to rebuild graph and vector indexes from processed artifacts without repeating upstream download and parse stages when only governance catalogs or embeddings require refresh.

Pipeline idempotency is implemented through content-addressed cache keys: ingestion LLM responses persist in `data/heart_failure/.ingestion_llm_cache/` keyed by SHA-1 hashes of prompts, and `HF_CDSS_INGESTION_SKIP_DOWNLOAD=true` enables reprocessing of staged S3 artifacts without redundant DailyMed HTTP calls. These mechanisms reduced operational cost during iterative threshold tuning that produced the 95.0% section retention and 6.6% borderline LLM rates reported in Section 5.2.2.

### 4.2.2. Acquisition Module

The acquisition module collects authoritative medical sources and stages immutable raw blobs into object storage before any parsing occurs. For FDA Structured Product Labels (SPL), the `DrugLabelAcquirer` class in `scraper/acquisition/download_sources.py` performs asynchronous HTTP retrieval against the DailyMed REST API (`https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json`), resolving each drug name to an SPL set identifier and downloading the canonical XML label. Clinical guidelines in PDF or HTML form are acquired from organizations such as ESC, AHA/ACC, and HFSA (including, for example, the 2022 ESC HF Guidelines). Drug interaction databases in JSON or CSV format supplement label-derived constraints with curated entries from DrugBank, RxNorm, and Micromedex-style sources registered in the sources manifest.

Acquisition is intentionally decoupled from parsing: downloaded XML, PDF, and HTML files are written to the LocalStack S3 raw bucket (`hf-cdss-raw`) under a versioned prefix (`heart_failure/`), preserving provenance and enabling pipeline idempotency when `HF_CDSS_INGESTION_SKIP_DOWNLOAD=true` is set for reprocessing of already-staged artifacts. The module uses `httpx.AsyncClient` for non-blocking concurrent downloads, which materially reduces wall-clock time when acquiring labels for dozens of GDMT-relevant agents in parallel.

The 94.2% extraction success rate reported in Section 5.2.1 traces partially to acquisition quality: DailyMed lookup mismatches for synonym drug names not present in the acquisition registry cause downstream parse failures. The planned Vietnamese synonym lexicon (Section 5.6) will extend both the sources manifest and acquisition string normalization, closing a gap between US-centric DailyMed identifiers and local formulary names.

**Code Implementation:**

```python
# scraper/acquisition/download_sources.py

class DrugLabelAcquirer:
    """Acquire FDA drug labels from DailyMed."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.session = httpx.AsyncClient()

    async def download_drug_labels(self, drug_names: list[str]):
        """Download SPL labels for specified drugs."""
        for drug_name in drug_names:
            spl_id = await self._find_spl_id(drug_name)
            xml_content = await self._download_spl(spl_id)
            self._save_xml(drug_name, xml_content)

    async def _find_spl_id(self, drug_name: str) -> str:
        """Find SPL set ID from DailyMed."""
        search_url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
        response = await self.session.get(search_url, params={"name": drug_name})
        data = response.json()
        return data["data"][0]["setid"]
```

### 4.2.3. Processing Module

The processing module transforms raw documents into normalized, section-identified text suitable for downstream NER, claim extraction, and embedding. XML SPL labels are parsed with section-aware XPath or tag-walking logic that preserves FDA section identifiers (for example, `34068-7` for dosage and administration, `34071-1` for warnings). PDF guidelines are processed with layout-aware text extraction; HTML guidelines are cleaned of navigational boilerplate before section segmentation. Each surviving section receives a stable section ID, document provenance metadata, and token-length statistics used later by the section filter and chunker.

Section identification is clinically motivated: dosing, warnings, contraindications, drug interactions, and patient counseling sections carry disproportionate decision-support value and are prioritized by both keyword lists and semantic prototype matching (Section 4.2.6). Drug names are normalized to RxNorm Concept Unique Identifiers (CUIs) where possible, and laboratory units are standardized to canonical forms (mg, mEq/L, mg/dL for creatinine, and so on) so that downstream constraint rules compare patient values consistently.

Chunking employs a sentence-aware sliding window with overlap rather than naive fixed-character splits. The `SectionChunker` in `scraper/transform/chunk_sections.py` accumulates sentences until an approximate token budget of 512 tokens is reached, then rolls back the final two sentences into the next chunk to preserve cross-sentence clinical context (for example, a contraindication stated across two adjacent sentences). Token estimation uses a lightweight heuristic compatible with embedding model context limits. Overlap prevents boundary artifacts where a dosing table header appears in one chunk and numeric limits in the next without shared context.

Average 68.9 sections per drug (Section 5.2.1) reflects SPL verbosity: each label contains dozens of sections, most filtered before chunking. Sentence-aware overlap directly supports GraphRAG chunk window expansion at query time, adjacent chunk indices referenced in metadata enable context restoration without re-embedding entire documents.

**Chunking Strategy:**

```python
# scraper/transform/chunk_sections.py

class SectionChunker:
    """Split clinical documents into semantically coherent chunks."""

    def chunk_guideline(self, text: str, max_tokens: int = 512) -> list[Chunk]:
        """Split guideline into chunks with overlap."""
        sentences = self._split_sentences(text)
        chunks = []
        current_chunk = []
        current_size = 0

        for sentence in sentences:
            sentence_size = self._estimate_tokens(sentence)

            if current_size + sentence_size > max_tokens:
                if current_chunk:
                    chunks.append(self._create_chunk(current_chunk))
                current_chunk = current_chunk[-2:] if len(current_chunk) > 2 else current_chunk
                current_size = sum(self._estimate_tokens(s) for s in current_chunk)

            current_chunk.append(sentence)
            current_size += sentence_size

        if current_chunk:
            chunks.append(self._create_chunk(current_chunk))

        return chunks
```

### 4.2.4. Extraction Module

The extraction module converts normalized text into structured clinical artifacts through a hybrid of deterministic pattern matching and LLM-assisted structured extraction. Named entity recognition (NER) identifies drug names, drug classes, dosage strengths, laboratory values, vital signs, and clinical conditions using lexicon-backed matchers supplemented by regex templates tuned to SPL and guideline phrasing. Relation and claim extraction links entities into actionable statements, for example, drug → contraindication, drug → interaction partner, drug class → initiation threshold, producing intermediate claim objects with evidence spans and source document references.

Constraint rule extraction follows an IF-conditions THEN-action template aligned with the governance catalog schema. A regex-first claim extractor handles high-frequency labeling patterns at high throughput during `kg_base` runs; when pattern coverage is sparse (fewer than a configurable minimum of regex matches per section), an optional LLM claim pass enriches the section using structured JSON output. The `ClinicalRuleExtractor` in `scraper/semantic/rule_builder.py` invokes the local Ollama chat-completions API with a Pydantic-validated response schema (`ClinicalRuleList`), enforcing typed fields for `drug_class`, `action`, `conditions`, `rationale`, and `evidence_ref`. JSON schema / Pydantic validation rejects malformed model output before it enters the artifact stream, and ingestion LLM responses are cached on disk (`data/heart_failure/.ingestion_llm_cache/`) to avoid redundant API cost on pipeline re-runs.

The 6,032 constraint rules and 1,096 interaction rules in the evaluation catalog (Section 5.1.2) originate from this module's JSONL output stream. Regex-first extraction achieves the 45-second average per-drug extraction time (Section 5.2.1) by avoiding LLM calls on high-frequency SPL phrasing; LLM enrichment activates only on sparse sections, mirroring query-time hybrid intake.

**LLM-Based Extraction:**

```python
# scraper/semantic/rule_builder.py

class ClinicalRuleExtractor:
    """Extract clinical decision rules using LLM."""

    SYSTEM_PROMPT = """
    You are a medical expert. Extract clinical rules from the text.
    Each rule must include:
    - drug_class: Drug class (e.g., ACE inhibitor, Beta blocker)
    - action: Action (e.g., avoid, consider, continue)
    - conditions: Applicable conditions (e.g., eGFR < 30)
    - rationale: Brief explanation
    - evidence_ref: Evidence reference
    """

    async def extract_rules(self, text: str) -> list[ClinicalRule]:
        """Extract rules from clinical text."""
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract rules from:\n{text}"}
            ],
            response_format=ClinicalRuleList
        )
        return response.rules
```

Extracted artifacts include constraint rules, dose rules, interaction rules, GDMT policies, and dose-safety warnings, each serialized as JSONL records with stable identifiers suitable for PostgreSQL upsert and admin governance review.

### 4.2.5. Classification Module

The classification module assigns each extracted rule a safety tier and action type before sync to production catalogs, implementing a governance gate that prevents incomplete or ambiguous rules from executing automatically at query time. Safety tiers encode deployability: `hard_block` marks absolute contraindications that must never be violated by the reasoning engine (for example, concurrent ACE inhibitor and ARNI initiation within the mandated washout window); `usable_rules` denotes rules with complete conditions and actionable dosing or status semantics ready for immediate runtime evaluation; `needs_condition_refinement` flags rules whose condition objects are missing, underspecified, or require LLM-assisted condition refinement (`HF_CDSS_CONDITION_REFINE_LLM_MODEL`) before promotion to `usable_rules`.

Action types align with clinician-facing recommendation cards: `avoid` signals that initiation or continuation is contraindicated; `consider_with_caution` indicates eligibility only under monitoring or with dose adjustment; `consider` supports initiation or uptitration when GDMT gaps exist; `continue` affirms maintenance of an appropriate existing therapy. The `RuleClassifier` in `scraper/process/classify_rules.py` combines structural heuristics (presence of complete condition objects, absolute contraindication patterns, dosing metadata completeness) with confidence scoring; rules classified as `needs_condition_refinement` are synced to PostgreSQL for admin review rather than silently dropped, preserving auditability of extraction quality.

The classification distribution, 53.9% usable, 35.2% needs refinement, 11.1% hard block (Section 5.2.3), demonstrates that automated extraction produces a governable draft catalog rather than production-ready rules without human review. Runtime loaders filter to approved `usable_rules` and `hard_block` tiers only.

**Classification Logic:**

```python
# scraper/process/classify_rules.py

class RuleClassifier:
    """Classify extracted rules by safety tier and action type."""

    def classify(self, rule: ClinicalRule) -> ClassificationResult:
        safety_tier = self._determine_safety_tier(rule)
        action_type = self._determine_action_type(rule)
        confidence = self._calculate_confidence(rule)

        return ClassificationResult(
            safety_tier=safety_tier,
            action=action_type,
            confidence=confidence,
            needs_review=safety_tier == "needs_condition_refinement"
        )

    def _determine_safety_tier(self, rule: ClinicalRule) -> str:
        if not rule.conditions:
            return "needs_condition_refinement"
        if self._has_absolute_contraindication(rule):
            return "hard_block"
        if self._has_complete_dosing_info(rule):
            return "usable_rules"
        return "needs_condition_refinement"
```

### 4.2.6. Section Filtering Module

The section filtering module implements a cost-aware three-tier cascade to retain clinically relevant document sections while minimizing unnecessary LLM calls during ingestion, a design directly reflected in the evaluation metrics of Section 5.2.2, where only 6.6% of sections required borderline LLM review. Tier 1 applies keyword matching against curated clinical heading lexicons (for example, "DOSAGE", "WARNINGS", "DRUG INTERACTIONS", "CONTRAINDICATIONS"); any section whose title or lead text matches is kept immediately without embedding computation. Tier 2 embeds the section title and opening text with BGE-M3 and computes cosine similarity against prototype embeddings for heart-failure-relevant section types; sections scoring ≥ 0.52 (`HF_CDSS_SECTION_SIMILARITY_THRESHOLD`) are kept. Tier 3 handles the borderline band [0.40, 0.52): an LLM reviewer (`HF_CDSS_SECTION_BORDERLINE_LLM_ENABLED`) reads a truncated section preview and answers a binary keep/drop prompt; sections scoring < 0.40 are dropped without LLM invocation. A hard cap (`HF_CDSS_SECTION_BORDERLINE_LLM_MAX=400`) bounds worst-case LLM spend on noisy documents.

This cascade mirrors the query-time hybrid intake philosophy (Chapter 1): apply fast deterministic or embedding methods first, and invoke the LLM only when signal strength is uncertain. The result is high coverage (95.0% of sections retained overall) with 96.6% of inputs never reaching the borderline LLM tier.

Implementation stores prototype embeddings precomputed offline for each clinical section type (dosing, warnings, interactions, contraindications, indications), avoiding repeated embedding of prototypes during pipeline runs. Borderline LLM prompts truncate section text to 500 characters, sufficient for heading-plus-lead classification while bounding token cost.

**Filtering Flow:**

```
Input: All parsed sections from documents
         │
         ▼
┌─────────────────┐
│  Keyword Match │──── Match found ────▶ KEEP
└────────┬────────┘
         │ No match
         ▼
┌─────────────────┐
│ Embedding Score│──── Score ≥ 0.52 ────▶ KEEP
│   (BGE-M3)     │
└────────┬────────┘
         │ Score < 0.52
         ▼
┌─────────────────┐
│ Borderline Zone │─── Score ∈ [0.40, 0.52) ───┐
│    (LLM Call)  │                              │
└────────┬────────┘                              │
         │                                        ▼
         │                              ┌─────────────────┐
         │                              │  LLM Review     │
         │                              │  Keep/Drop?     │
         │                              └────────┬────────┘
         │                                        │
         └──── Score < 0.40 ────▶ DROP            │
                                           ┌──────┴──────┐
                                           │             │
                                           ▼             ▼
                                        KEEP          DROP
```

**Implementation:**

```python
# scraper/semantic/section_filter.py

class SectionFilter:
    """Filter important clinical sections using multi-tier approach."""

    async def _llm_review(self, section: Section) -> bool:
        """Ask LLM whether borderline section is important."""
        prompt = f"""
        Is the following section important for heart failure treatment?

        Title: {section.title}
        Content: {section.text[:500]}

        Answer YES if the section contains:
        - Heart failure medication information
        - Dosing and administration
        - Warnings and interactions
        - Contraindications

        Answer NO if:
        - Not related to heart failure
        - Administrative information only
        """
        response = await self.llm.chat(prompt)
        return "YES" in response.upper()
```

## 4.3. Backend Implementation

### 4.3.1. Backend Project Structure

The backend follows a modular monolith pattern: a single FastAPI application (`app/main.py`) exposes versioned REST and SSE endpoints while domain logic resides in cohesive modules with explicit datastore adapters. This structure keeps deployment simple (one backend container) yet preserves boundaries between chat orchestration, deterministic reasoning, GraphRAG retrieval, verification agents, and governance admin routes.

```
backend/
├── app/
│   ├── api/routes/
│   │   ├── admin/          # constraint_rules, dose_rules, gdmt_policies, etc.
│   │   ├── chat.py
│   │   └── health.py
│   ├── modules/
│   │   ├── chat/           # service.py, clinical_state.py
│   │   ├── clinical_intake_extraction/
│   │   ├── constraint_builder/
│   │   ├── dose_calculation/
│   │   ├── dose_safety/
│   │   ├── explanation/    # card_summarizer.py, llm_service.py
│   │   ├── graphrag/
│   │   ├── reasoning/
│   │   ├── verification_agents/
│   │   └── datastores/     # postgres.py, redis_client.py
│   ├── schemas/
│   ├── prompts/
│   └── core/
├── tests/
├── requirements.txt
└── main.py
```

The backend organizes API routes, domain modules (chat, GraphRAG, reasoning, verification, dose calculation, explanation), shared schemas and prompts, and datastore adapters under a single FastAPI application entry point. Async database and HTTP clients are used throughout so that GraphRAG retrieval, verification agent fan-out, and LLM calls can overlap within a single chat request without blocking the event loop.

Module boundaries map directly to Chapter 3 functional modules: `clinical_intake_extraction` implements FR-1, `reasoning` implements FR-2 and FR-3, `dose_calculation` implements FR-4, `constraint_builder` and `dose_safety` implement FR-5, and `explanation/card_summarizer` implements FR-6 presentation aspects. Shared `schemas/` Pydantic models enforce contract consistency between SSE payloads, PostgreSQL ORM mappings, and frontend TypeScript types generated or mirrored manually.

### 4.3.2. Chat Service Implementation

The chat service (`app/modules/chat/service.py`) orchestrates the end-to-end clinical decision support flow as an ordered pipeline with deliberately separated deterministic and generative stages. First, the hybrid clinical-intake module extracts a structured `PatientProfile` from free text using regex numerics, medication lexicons, semantic embedding matchers, and selective LLM extraction when regex confidence is insufficient; measured values from regex take precedence over LLM guesses in the merge step. Second, `build_clinical_state` normalizes units, computes derived fields such as eGFR from creatinine/age/sex when direct eGFR is absent, and attaches risk flags. Third, GraphRAG assembles explanatory retrieval context in parallel with the deterministic reasoning engine, which evaluates GDMT coverage, PostgreSQL-backed constraints, interactions, and dose rules. Fourth, verification agents audit the recommendation bundle against hard blocks and retrieved evidence. Fifth, the card summarizer attaches plain-language Vietnamese and English labels. Finally, the LLM answer builder produces a streaming clinician-facing narrative grounded in the verified recommendation object, not as the source of truth for dosing or safety status.

The HTTP layer exposes this flow through FastAPI async route handlers; the streaming variant emits typed SSE events (`patient_draft`, `recommendation`, `verification`, `answer_token`, `done`) using `sse-starlette`'s `EventSourceResponse`, allowing the React dashboard to render partial results incrementally while the 8.1-second mean end-to-end latency (Section 5.3.2) is dominated by LLM answer token generation.

Implementation detail: GraphRAG prefetch is launched as an `asyncio.create_task` immediately after intake completes, while reasoning executes in `asyncio.to_thread` to avoid blocking the event loop during synchronous PostgreSQL rule evaluation. Verification awaits both the recommendation future and GraphRAG task before proceeding, a join point ensuring evidence agents receive non-empty retrieval context when available.

```python
# app/modules/chat/service.py

class ChatService:
    """Main chat service handling clinical decision support."""

    async def process_message(self, request: ChatRequest):
        """Process a chat message and stream responses."""
        # 1. Extract patient profile
        patient = await extract_patient_from_message(request.message)

        # 2. Build clinical state
        clinical_state = build_clinical_state(patient, request.clinical_attachments)

        # 3. Get GraphRAG context
        context = await build_graphrag_context(clinical_state)

        # 4. Generate recommendations
        recommendation = await build_recommendation(clinical_state, context)

        # 5. Verify against constraints
        verification = await verify_recommendation(recommendation)

        # 6. Add plain language summaries
        recommendation = await attach_plain_language_summaries(
            recommendation,
            language=request.language or "en"
        )

        # 7. Generate LLM answer
        answer = await build_llm_answer(patient, recommendation, verification)

        return {
            "patient_draft": patient,
            "recommendation": recommendation,
            "verification": verification,
            "answer": answer
        }
```

### 4.3.3. GraphRAG Service Implementation

The GraphRAG service (`app/modules/graphrag/service.py`) implements hybrid retrieval over ChromaDB dense vectors, BM25-style sparse keyword search, and Neo4j neighborhood queries, fusing ranked candidate lists with Reciprocal Rank Fusion (RRF) before optional semantic reranking. Query construction begins with entity extraction from the patient profile and active medication list, optionally augmented by HyDE hypothetical document expansion and query decomposition for multi-aspect clinical questions. Local search retrieves constraint and evidence chunks whose embeddings are nearest to the query vector in cosine space; global search traverses Neo4j community and relationship patterns to surface multi-hop interaction and class-level guidance. The merged `GraphRAGContext` supplies citation-ready evidence spans to the explanation LLM while the deterministic reasoning engine continues to enforce numeric thresholds from PostgreSQL catalogs independently of retrieved prose.

RRF scoring \(\mathrm{Score}_{\mathrm{RRF}}(d) = \sum_r 1/(k + \mathrm{rank}_r(d))\) ensures that documents appearing highly ranked across both dense and sparse retrievers rise to the top even when individual retriever scores are incomparable, an important property when clinical queries mix exact drug names (sparse-friendly) with paraphrased indication language (dense-friendly).

The BM25 index is held in memory and rebuilt on backend startup from published chunk metadata, a trade-off favoring query latency over incremental index updates. ChromaDB queries use metadata filters on `drug_class` and `chunk_type` when clinical state specifies focus classes, reducing candidate pool size and contributing to the 0.8-second GraphRAG mean (Section 5.3.2).

```python
# app/modules/graphrag/service.py

class GraphRAGService:
    """GraphRAG service for clinical knowledge retrieval."""

    async def get_relevant_context(
        self,
        patient: PatientProfile,
        medications: list[str]
    ) -> GraphRAGContext:
        # 1. Build entity query
        query_entities = self._extract_entities(patient, medications)

        # 2. Local search: Find relevant constraints
        local_constraints = await self._local_search(query_entities)

        # 3. Global search: Find community patterns
        global_insights = await self._global_search(query_entities)

        # 4. Merge and rank
        return self._merge_context(local_constraints, global_insights)

    async def _local_search(self, entities: list[str]) -> list[Constraint]:
        query_embedding = self.embedder.encode(" ".join(entities))
        results = self.vector_store.search(
            query_vector=query_embedding,
            n_results=20,
            filter={"type": "constraint"}
        )
        return [self.constraints.get_by_id(r["id"]) for r in results]
```

### 4.3.4. Card Summarizer Implementation

The card summarizer (`app/modules/explanation/card_summarizer.py`) implements a deterministic plain-language mapping layer that translates structured recommendation fields into clinician-friendly labels without invoking an LLM. Drug class strings such as "ACE inhibitor" map to locale-specific phrases ("Thuốc hạ huyết áp" in Vietnamese, "Blood pressure medication" in English); action/status codes map to badge text ("Use with caution", "Cân nhắc thận trọng"). This separation ensures that safety-critical status values displayed on `ClinicalPanel` cards mirror the deterministic reasoning output exactly, while the LLM narrative in the chat thread may elaborate on rationale using GraphRAG citations. When the user toggles language (Section 4.4.3), the backend regenerates simplified fields for the new locale and the frontend re-renders cards from the updated `simplified` object without re-running full reasoning.

Deterministic simplification is a deliberate trust mechanism: survey respondents rated clinical usefulness at 4.5/5 (Section 5.4.3) partly because GDMT cards remain stable even when LLM narrative tone varies between runs.

```python
# app/modules/explanation/card_summarizer.py

class CardSummarizer:
    """Generate plain language summaries for recommendation cards."""

    DRUG_CLASS_PLAIN = {
        "vi": {
            "ACE inhibitor": "Thuốc hạ huyết áp",
            "SGLT2 inhibitor": "Thuốc đái tháo đường, bảo vệ thận",
            "Beta blocker": "Thuốc giảm nhịp tim, bảo vệ tim",
            "MRA": "Thuốc lợi tiểu giữ kali",
            "ARNI": "Thuốc tim mạch (ARNI)",
        },
        "en": {
            "ACE inhibitor": "Blood pressure medication",
            "SGLT2 inhibitor": "Diabetes & kidney protection medication",
            "Beta blocker": "Heart rate & heart protection medication",
            "MRA": "Potassium-sparing diuretic",
            "ARNI": "Heart medication (ARNI)",
        }
    }

    STATUS_LABELS = {
        "en": {
            "avoid": "Avoid or delay",
            "consider_with_caution": "Use with caution",
            "consider": "Consider",
            "continue": "Continue",
            "blocked": "Blocked",
        }
    }

    def simplify_structured_field(self, raw_value: str, field_type: str, language: str) -> str:
        if field_type == "status":
            return self.STATUS_LABELS.get(language, self.STATUS_LABELS["en"]).get(
                raw_value, raw_value
            )
        if field_type == "drug_class":
            return self.DRUG_CLASS_PLAIN.get(language, self.DRUG_CLASS_PLAIN["en"]).get(
                raw_value, raw_value
            )
        return raw_value
```

## 4.4. Frontend Implementation

### 4.4.1. Frontend Project Structure

The frontend is organized as a monorepo under `frontend/` with a doctor dashboard (primary clinical chat UI), an admin governance portal, and shared packages for API clients and catalog configuration. The doctor dashboard is built with React 18 and Vite, using hooks-based state management and a thin API layer that consumes SSE streams from `/api/v1/chat/stream`.

```
frontend/
├── doctor-dashboard/
│   ├── src/
│   │   ├── components/     # ClinicalChatThread, ClinicalPanel, ChatInput, etc.
│   │   ├── pages/          # ChatPage, EvidencePage, ApiExplorerPage
│   │   ├── hooks/          # useChat, useConversations, useApiHealth
│   │   ├── lib/            # clinicalChatStream, recommendationDisplay
│   │   ├── i18n/           # LanguageProvider, messages
│   │   └── api/
│   └── package.json
├── admin/
└── shared/
    ├── governance/
    └── api/
```

The frontend is split into a doctor dashboard, an admin application, and shared governance and API utilities. Vite's dev server proxies `/api` requests to the FastAPI backend (`VITE_DEV_PROXY_TARGET`), while production builds may be served as static assets behind Nginx (Section 4.5.2).

The `clinicalChatStream` module in `lib/` implements SSE frame parsing with event-type dispatch, a thin layer that maps server event names (`draft_ready`, `recommendation_ready`, etc.) to React state updaters. This separation keeps UI components declarative while isolating protocol parsing logic for unit testing.

### 4.4.2. ClinicalPanel Component

The `ClinicalPanel` hosts `RecommendationCard` components that render GDMT and safety recommendations as structured cards alongside shared vitals and retrieved evidence snippets. Each card reads deterministic recommendation fields (`drug_class`, `status`, `clinical_reasoning`) and locale-specific simplified labels produced by the card summarizer. The component uses the `useLanguage()` hook to select Vietnamese or English display strings, falling back gracefully when a translation key is absent. Status badges apply tone styling (for example, cautionary amber for `consider_with_caution`) so that clinicians can scan multiple drug-class rows quickly during a patient encounter, supporting the usability scores reported in Section 5.4.3.

```jsx
// frontend/doctor-dashboard/src/components/ClinicalPanel.jsx

function RecommendationCard({ item, evidenceChunks = [], sharedVitals = [] }) {
  const { language } = useLanguage();
  const simplified = item.simplified || {};

  const getSimplified = (field, fallback = []) => {
    const simplifiedList = simplified[field];
    if (Array.isArray(simplifiedList) && simplifiedList.length > 0) {
      return simplifiedList.map(item => item?.[language] || item?.vi || "").filter(Boolean);
    }
    return fallback;
  };

  const displayDrugClass =
    simplified.drug_class_plain?.[language] ||
    simplified.drug_class_plain?.vi ||
    item.drug_class;

  const displayStatus =
    simplified.status_plain?.[language] ||
    simplified.status_plain?.vi ||
    item.status;

  const reasoningItems = getSimplified("reasoning_plain", item.clinical_reasoning);

  return (
    <article className="recommendation-card">
      <header>
        <h3>{displayDrugClass}</h3>
        <Badge tone={displayStatus}>{displayStatus}</Badge>
      </header>
      <div className="clinical-details">
        {reasoningItems.map((item, i) => (
          <RecommendationBlock key={i} title="Clinical Reasoning">
            <p>{item}</p>
          </RecommendationBlock>
        ))}
      </div>
    </article>
  );
}
```

### 4.4.3. Language Toggle Implementation

Bilingual operation is a first-class requirement for deployment in Vietnamese clinical settings. The `LanguageProvider` persists the user's locale preference in `localStorage` under `hf_cdss_chat_language`, updates the document `lang` attribute for accessibility, and exposes `language` and `setLanguage` through React context to all chat and panel components. When the clinician switches between Vietnamese (`vi`) and English (`en`), the dashboard issues a language parameter on subsequent chat requests (or invokes a lightweight re-simplification endpoint) so that card summarizer output and UI chrome regenerate in the selected language while conversation history and structured patient state remain intact, consistent with the under-2-second language switch latency and zero data-loss observations in Section 5.4.2.

```jsx
// frontend/doctor-dashboard/src/i18n/LanguageProvider.jsx

const LANGUAGE_STORAGE_KEY = "hf_cdss_chat_language";

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(() => {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return stored || "vi";
  });

  const setLanguage = useCallback((code) => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, code);
    setLanguageState(code);
    document.documentElement.lang = code;
  }, []);

  return (
    <LanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
}
```

The `clinicalChatStream` client parses SSE frames incrementally, updating `ClinicalPanel` as recommendation events arrive before answer token streaming begins, preserving responsive UI behavior despite multi-second backend processing.

## 4.5. System Deployment

### 4.5.1. Docker Configuration

Production-like local deployment uses Docker Compose to orchestrate the full data and inference stack: PostgreSQL for governance, Redis for cache and rate limiting, Neo4j for the knowledge graph, ChromaDB for vector retrieval, Ollama for local LLM and embedding inference, LocalStack for S3-compatible raw/processed artifact storage, and the FastAPI backend and Vite/React frontend services. Service health checks gate backend startup until PostgreSQL, Neo4j, ChromaDB, Redis, LocalStack bucket initialization, and Ollama model pulls have completed, preventing race conditions during artifact hydration.

```yaml
# infrastructure/docker-compose.yml

version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: hf_cdss
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-password}
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data

  chromadb:
    image: chromadb/chroma:latest
    ports:
      - "8001:8000"
    volumes:
      - chroma_data:/chroma/chroma

  localstack:
    image: localstack/localstack:3.8.1
    ports:
      - "4566:4566"
    environment:
      SERVICES: s3
      PERSISTENCE: "1"
    volumes:
      - localstack_data:/var/lib/localstack

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"

  backend:
    build: ../backend
    environment:
      DATABASE_URL: postgresql://postgres:${DB_PASSWORD}@postgres:5432/hf_cdss
      REDIS_URL: redis://redis:6379
      HF_CDSS_NEO4J_URI: bolt://neo4j:7687
      HF_CDSS_CHROMA_HOST: chromadb
      HF_CDSS_S3_ENDPOINT_URL: http://localstack:4566
      HF_CDSS_RAW_BUCKET: hf-cdss-raw
      OLLAMA_BASE_URL: http://ollama:11434
    depends_on:
      - postgres
      - redis
      - neo4j
      - chromadb
      - localstack
      - ollama
    ports:
      - "8000:8000"

  frontend:
    build: ../frontend/doctor-dashboard
    ports:
      - "3000:3000"
    depends_on:
      - backend

  admin:
    build: ../frontend/admin
    ports:
      - "3001:3000"
    depends_on:
      - backend

  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
    depends_on:
      - frontend
      - admin
      - backend

volumes:
  postgres_data:
  redis_data:
  neo4j_data:
  chroma_data:
  localstack_data:
  ollama_data:
```

The Compose file expresses service dependencies explicitly so that the backend container starts only after datastores are healthy and the LocalStack init job has created `hf-cdss-raw` and `hf-cdss-processed` buckets. GPU passthrough to Ollama is configured on supported hosts via NVIDIA Container Toolkit, enabling acceptable embedding and generation latency for the evaluation hardware profile in Chapter 5.

### 4.5.2. Nginx Configuration

Nginx terminates HTTP on port 80 and routes traffic by path prefix: the doctor dashboard receives `/`, the admin portal receives `/admin` (with URI rewrite stripping the prefix), and REST/SSE API calls under `/api` proxy to the FastAPI backend with appropriate hop-by-hop headers for SSE (`Cache-Control: no-cache`, disable buffering). This single-origin layout avoids CORS complexity in production while preserving Vite proxy behavior during development.

```nginx
# infrastructure/nginx.conf

events {
    worker_connections 1024;
}

http {
    upstream backend { server backend:8000; }
    upstream frontend { server frontend:3000; }
    upstream admin { server admin:3000; }

    server {
        listen 80;

        location / {
            proxy_pass http://frontend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_cache_bypass $http_upgrade;
        }

        location /admin {
            rewrite ^/admin(.*)$ $1 break;
            proxy_pass http://admin;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
        }

        location /api {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
```

Nginx routes root requests to the doctor dashboard, `/admin` to the admin portal, and `/api` to the FastAPI backend.

### 4.5.3. Environment Configuration

Feature flags and thresholds for the section filter, clinical intake semantic matchers, embedding provider, and verification agents are centralized in environment variables so that operations can tune cost-quality trade-offs without code changes.

```bash
# infrastructure/.env.example

# Database
DB_PASSWORD=your_secure_password_here

# Redis
REDIS_URL=redis://redis:6379

# Ollama (Local LLM)
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:7b
EMBEDDING_MODEL=bge-m3

# Graph / Vector / Object Storage
HF_CDSS_NEO4J_URI=bolt://neo4j:7687
HF_CDSS_CHROMA_HOST=chromadb
HF_CDSS_S3_ENDPOINT_URL=http://localstack:4566
HF_CDSS_RAW_BUCKET=hf-cdss-raw

# Application
SECRET_KEY=your_secret_key_here
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Feature Flags
HF_CDSS_SECTION_BORDERLINE_LLM_ENABLED=true
HF_CDSS_SECTION_SIMILARITY_THRESHOLD=0.52
HF_CDSS_SECTION_BORDERLINE_LOW_THRESHOLD=0.40
HF_CDSS_SECTION_BORDERLINE_LLM_MAX=400
```

### 4.5.4. Deployment Trade-offs and Alternatives

Several deployment decisions warrant explicit discussion because alternative choices would materially affect cost, latency, and operational complexity.

**Local Ollama versus cloud LLM APIs.** The evaluation stack uses Ollama with Qwen2.5-7B and BGE-M3 on-premises. Cloud APIs (OpenAI, Anthropic, Azure OpenAI) would eliminate GPU hardware requirements and simplify scaling but introduce per-token costs, data residency concerns for PHI-containing chat narratives, and network latency variability. The 8.1-second mean latency includes local inference; cloud round-trips would add unpredictable delay unless models are co-located in the same region as the hospital. On-premise Ollama trades capital expense (RTX 3080) for operational control, a rational choice for Vietnamese hospital IT environments with restricted outbound clinical data flows.

**Docker Compose versus Kubernetes.** Compose satisfies evaluation and single-hospital pilot deployment with eleven services on one host. Kubernetes would enable horizontal pod autoscaling for backend replicas and managed PostgreSQL operators but adds operational overhead disproportionate to the 50-concurrent-user NFR-1 target. The modular monolith backend (Section 4.3.1) can later split GraphRAG or Ollama into dedicated pods if load profiles demand it.

**LocalStack versus AWS S3.** LocalStack provides S3-compatible APIs for development and evaluation without cloud accounts. Production deployment would migrate to AWS S3 or MinIO with identical SDK calls (`HF_CDSS_S3_ENDPOINT_URL`), preserving pipeline artifact layout. LocalStack persistence (`PERSISTENCE=1`) enables laptop-close-reopen workflows; cloud S3 adds durability and lifecycle policies for raw label archives.

**Neo4j Community versus managed graph services.** Neo4j Community runs in Compose with volume persistence. Managed alternatives (Neo4j Aura, Amazon Neptune) reduce operational burden but increase cost and may restrict Cypher features. GraphRAG neighborhood queries are read-heavy and tolerate eventual consistency after pipeline sync, Community Edition suffices at current scale.

**ChromaDB embedded versus Pinecone/Weaviate.** ChromaDB co-locates with the backend stack, avoiding external vector service fees and keeping embeddings on-premise. Trade-off: Chroma lacks managed replication; disaster recovery relies on S3 processed artifact re-embedding via `--from-step kg_base`.

**Nginx TLS termination versus service-mesh mTLS.** Current design terminates TLS at Nginx (production) with plain HTTP inside Compose network, a common pattern for single-tenant hospital VLAN deployment. Service mesh mTLS would harden east-west traffic if backend replicas span nodes.

**Single-origin Nginx versus separate frontend CDN.** Serving React builds through Nginx simplifies SSE proxy configuration (no cross-origin EventSource). CDN deployment would improve static asset latency globally but is unnecessary for intranet hospital access patterns.

These trade-offs collectively prioritize on-premise deployability, auditable governance, and sub-10-second median latency over hyperscale cloud elasticity, a profile aligned with the thesis deployment context and evaluation hardware.

## 4.6. Testing

### 4.6.1. Testing Strategy Overview

Testing strategy follows a pyramid aligned with the hybrid architecture: extensive unit tests on deterministic modules (intake merge, RRF fusion, card summarizer, constraint matching), integration tests on assembled chat flows with mocked LLM endpoints, and manual cardiologist review for clinical accuracy (Chapter 5). LLM components are excluded from correctness-critical unit tests except where outputs are schema-validated (ingestion extraction); stochastic generation is tested for contract compliance, not clinical truth.

The principle **deterministic modules must not depend on LLM stochasticity for pass/fail** governs test design. Reasoning, dose calculation, constraint matching, and card summarizer achieve near-complete unit coverage. GraphRAG tests verify RRF ranking invariants and metadata filter behavior with fixture embeddings. Chat integration tests mock Ollama responses to return fixed JSON, enabling reproducible CI runs without GPU hardware.

Regression suites run on every pull request via GitHub Actions (or equivalent CI): `pytest backend/app/tests/` for Python, `npm test` for frontend SSE parser utilities. Pre-commit hooks enforce Pydantic model consistency and SQL migration ordering for governance schema changes.

### 4.6.2. Unit Tests

Unit tests isolate deterministic components whose correctness must not depend on LLM stochasticity. The card summarizer test suite verifies that drug class and status codes map to the expected English plain-language strings, guarding the bilingual display contract consumed by `ClinicalPanel`. GraphRAG unit tests include RRF fusion behavior, ensuring that consensus rankings across retrievers prefer documents that appear in multiple lists, directly supporting retrieval quality assumptions evaluated indirectly through recommendation accuracy in Chapter 5.

Additional unit test coverage includes: `_prefer_measured` merge policy in clinical intake (regex labs override LLM guesses); negation detection suppressing false medication hits; eGFR derivation from creatinine/age/sex when direct eGFR absent; constraint rule matching against risk flag arrays; dose rule renal band selection; and JWT role dependency rejection on admin routes.

```python
# backend/app/tests/test_card_summarizer.py

def test_simplify_drug_class_en(summarizer, sample_recommendation):
    result = summarizer.simplify_structured_field(
        sample_recommendation.drug_class,
        "drug_class",
        "en"
    )
    assert result == "Blood pressure medication"

def test_simplify_status(summarizer, sample_recommendation):
    assert summarizer.simplify_structured_field("avoid", "status", "en") == "Avoid or delay"
```

### 4.6.3. Integration Tests

Integration tests exercise the assembled chat pipeline with mocked or local LLM endpoints where appropriate, validating that patient extraction, clinical state construction, recommendation generation, and demographic parsing cooperate correctly across module boundaries.

```python
# backend/app/tests/test_chat_flow.py

@pytest.mark.asyncio
async def test_chat_message_processing():
    """Test full chat message processing flow."""
    service = ChatService()

    request = ChatRequest(
        message="65-year-old male, EF 30%, on bisoprolol 5mg. eGFR 45, K+ 4.2",
        conversation_id="test_conv",
        language="en"
    )

    result = await service.process_message(request)

    assert result.patient_draft is not None
    assert result.recommendation is not None
    assert len(result.recommendation.recommendations) > 0
    assert result.patient_draft.demographics.age == 65
```

Clinical intake integration tests additionally cover hybrid regex-and-LLM extraction paths, semantic medication matching above the 0.52 threshold, and eGFR derivation when only creatinine is supplied, behaviors that explain error reductions documented in Section 5.6.

SSE integration tests verify event ordering invariants (Section 3.5.1.1): `draft_ready` precedes `recommendation_ready`, which precedes `verification_ready`, which precedes first `answer_delta`. Missing-field short-circuit tests assert suppression of `recommendation_ready` when potassium is absent and MRA is in scope.

### 4.6.4. Pipeline and Ingestion Tests

Ingestion pipeline tests validate section filter tier boundaries using fixture sections with known similarity scores: keyword-hit sections never invoke embedding; borderline sections invoke mocked LLM review; sub-0.40 sections drop. Classification tests assert `hard_block` tier assignment for ACEi-ARNI washout patterns. Sync tests verify PostgreSQL upsert idempotency and Redis cache invalidation on admin approve.

Data quality regression: `data_quality_report` CLI emits record counts compared against golden baselines (127 drugs, 6,032 constraints) to catch silent pipeline regressions.

### 4.6.5. Frontend Tests

Frontend unit tests cover `clinicalChatStream` SSE frame parsing, `LanguageProvider` localStorage persistence, and `RecommendationCard` fallback rendering when simplified fields are absent. React Testing Library exercises clinical panel update sequences mocked from recorded SSE fixture files captured during evaluation runs.

### 4.6.6. Clinical and Safety Validation (External to CI)

Recommendation accuracy (94.0%), safety scenario pass rates (100% on four curated cases), and usability surveys (4.22/5) constitute external validation layers not fully automatable in CI. Two cardiologists independently scored 50 vignettes against structured recommendation objects, a human-in-the-loop test protocol treating LLM prose as non-authoritative.

## 4.7. Operations and Maintenance

### 4.7.1. Monitoring

Operational readiness relies on layered health endpoints exposed by `app/api/routes/health.py`. The liveness endpoint `/api/v1/health` confirms that the FastAPI process is accepting requests. The readiness endpoint `/api/v1/health/ready` verifies that critical startup tasks (artifact hydration, catalog loading) have completed. The dependencies endpoint `/api/v1/health/dependencies` probes PostgreSQL, Redis, ChromaDB, Neo4j, S3/LocalStack, and Ollama connectivity, returning structured status per datastore for orchestrator health checks and on-call diagnostics. Application logs are written to stdout in JSON format at configurable severity (DEBUG, INFO, WARNING, ERROR) and collected by Docker logging drivers.

**Health Checks:**
```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/ready
curl http://localhost:8000/api/v1/health/dependencies
```

Structured JSON logs include `conversation_id`, pipeline stage timings, and GraphRAG candidate counts, fields used to decompose the 8.1-second mean latency in Section 5.3.2 during evaluation instrumentation.

### 4.7.2. Backup and Restore

PostgreSQL governance catalogs are backed up with `pg_dump` from the running container volume. Neo4j and ChromaDB volumes may be snapshotted separately when graph or embedding rebuild from S3 processed artifacts is insufficient (for example, after schema migration). LocalStack S3 persistence (`PERSISTENCE=1`) retains raw and processed buckets across Compose restarts, but periodic export to external object storage is recommended for disaster recovery.

```bash
# Backup database
docker exec hf_cdss-postgres-1 pg_dump -U postgres hf_cdss > backup.sql

# Restore database
docker exec -i hf_cdss-postgres-1 psql -U postgres hf_cdss < backup.sql
```

Recovery time objective (RTO) for governance catalogs is dominated by PostgreSQL restore; vector and graph indexes can rebuild from S3 processed JSONL via `--from-step kg_base` within hours rather than minutes, a acceptable trade-off given ingestion idempotency.

### 4.7.3. Update Knowledge Base

Knowledge base updates follow a repeatable pipeline re-sync workflow: run ingestion from the `kg_base` step to rebuild JSONL artifacts and embeddings, synchronize governance catalogs into PostgreSQL with `sync_governance_catalog`, and validate record counts and anomaly flags with `data_quality_report`. Backend restart or explicit reload endpoints hydrate Neo4j and ChromaDB from processed S3 objects. This procedure is executed after FDA label updates, new guideline publication, or admin approval of rules promoted from `needs_condition_refinement` to `usable_rules`.

```bash
# Run pipeline
cd scraper
python -m scraper.orchestration.run_ingestion_pipeline --from-step kg_base

# Sync to database
python -m scraper.process.sync_governance_catalog --catalog all

# Verify counts
python -m scraper.orchestration.data_quality_report
```

Operators should monitor borderline LLM call counts during re-ingestion; if section filter thresholds drift because of new document layouts, tuning `HF_CDSS_SECTION_SIMILARITY_THRESHOLD` and keyword lexicons is preferred over disabling LLM review entirely, preserving the cost-coverage balance demonstrated in Section 5.2.2.

---

This chapter mapped Chapter 3 designs to concrete implementation artifacts: the ingestion pipeline modules with three-tier section filtering, FastAPI backend services with async fork-join orchestration, React frontend with SSE-driven clinical panels, Docker Compose deployment with explicit trade-off analysis, a layered testing strategy separating deterministic and generative components, and operational procedures for monitoring, backup, and knowledge base refresh.
