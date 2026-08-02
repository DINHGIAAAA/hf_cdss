# Runtime Architecture — hf_cdss

```mermaid
graph TD
    %% ── EXTERNAL DEPENDENCIES ──────────────────────────────────────────────
    ext_db[(PostgreSQL)]
    ext_redis[(Redis Cache)]
    ext_llm[(LLM API)]
    ext_s3[(S3 / Object Store)]

    subgraph "Trust Boundary: Data Layer"
        ext_db
        ext_redis
        ext_s3
    end

    %% ── FRONTEND TIER ───────────────────────────────────────────────────────
    subgraph "Frontend (React)"
        FE["Admin UI\n+ Doctor Dashboard"]
    end

    %% ── BACKEND TIER ─────────────────────────────────────────────────────────
    subgraph "Backend (FastAPI)"
        API["API Routes\n/admin · /auth · /patients · /evidence"]
        MID["Middleware\n(production_guard · audit_log · auth)"]
        CORE["Core Engine\nDose Safety · GDMT · Drug Interactions"]
        KG["Knowledge Graph\n(graphrag_context · retrieval)"]
        SCHEMAS["Pydantic Schemas\n(Patient · User · Claims · Rules)"]
    end

    %% ── SCRAPER / INGESTION PIPELINE ────────────────────────────────────────
    subgraph "Scraper Pipeline (Python)"
        ACQ["Acquisition\n(JSON fetch + S3 download)"]
        SEM["Semantic Layer\n(claim_extraction · type_gates)"]
        PROC["Process / Rule Engine\n(transform · validate · create_claims)"]
        EVAL["Eval / Heuristics\n(auto_judge · filter_quality)"]
    end

    %% ── TRAINING TIER ────────────────────────────────────────────────────────
    subgraph "Training (Fine-tuning)"
        TRAIN["BRAT → Fine-tune\n(NER / classification)"]
    end

    %% ── PRIMARY PATH ─────────────────────────────────────────────────────────
    FE -->|"HTTPS"| MID
    MID -->|"validated request"| API
    API -->|auth token| SCHEMAS
    SCHEMAS -->|patient + rules| CORE
    CORE -->|lookup / cache| ext_redis
    CORE -->|persist| ext_db
    KG -->|context / facts| CORE
    KG -->|reads from| ext_db

    %% ── INGESTION PATH ──────────────────────────────────────────────────────
    ACQ -->|raw docs| ext_s3
    ext_s3 -->|feeds| SEM
    SEM -->|structured claims| PROC
    PROC -->|validated| EVAL
    EVAL -->|gold claims| ext_db
    TRAIN -->|model weights| SEM

    %% ── SCRAPER → BACKEND BRIDGE ─────────────────────────────────────────────
    PROC -->|"rule updates"| ext_db
    TRAIN -->|"updated rules"| ext_db

    classDef frontend fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef backend  fill:#f3e5f5,stroke:#6a1b9a,color:#4a148c
    classDef scraper  fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef training fill:#fff3e0,stroke:#e65100,color:#bf360c
    classDef external fill:#eceff1,stroke:#546e7a,color:#37474f
    classDef primary  stroke:#d50000,stroke-width:3px

    class FE,API,MID,CORE,KG,SCHEMAS backend
    class ACQ,SEM,PROC,EVAL scraper
    class TRAIN training
    class ext_db,ext_redis,ext_llm,ext_s3 external
    class FE primary
    class CORE primary
    class ext_db primary
```

## Cards

### 1. Admin UI + Doctor Dashboard
React application serving two roles: clinical administration (rule management, audit history, bulk approvals) and point-of-care decision support.

### 2. FastAPI Middleware Stack
`production_guard_middleware` — blocks access in non-production; `audit_logging` — appends to audit trail on every mutation; `auth` — JWT/OAuth2 token validation.

### 3. Core Clinical Engine
Three rule engines in one process: **Dose Safety** (dose-range checking against rules), **GDMT Policy** (guideline-directed medical therapy adherence), **Drug Interaction** (cross-reference against constraint rules). All three share the same schema layer.

### 4. Knowledge Graph Retrieval
`graphrag_context` / `retrieval_context` — builds structured clinical context from the graph DB for LLM grounding. Feeds the core engine facts retrieved at query time.

### 5. Claim Extraction (Semantic Layer)
`claim_extraction` parses unstructured text into structured `Claim` objects. `claim_type_gates` apply structural validation gates (numeric threshold, temporal, comparative, etc.).

### 6. Scraper Acquisition
JSON API fetching + S3 download. Feeds raw documents into the pipeline. `acquisition/json` community handles the download/parse logic.

### 7. Process / Rule Engine
`transform` → `validate` → `create_claims`. Takes raw claims through quality filtering and writes approved rules back to PostgreSQL.

### 8. Evaluation / Auto-Judge
`auto_judge` + `filter_claims_for_quality` — heuristic and LLM-based scoring of claim accuracy. Produces `gold` claims for the evaluation set.

### 9. Fine-tuning Pipeline
BRAT-annotated clinical text → fine-tune NER/classification models → updated weights flow back into `claim_extraction`.

### 10. Data Layer
- **PostgreSQL** — primary store: users, patients, rules, audit logs, gold claims
- **Redis** — L1 cache for rule lookups (`_reset_constraint_cache` triggered on rule mutation)
- **S3** — raw document blob store for scraped content

---

**Trust boundaries:**
- Frontend is entirely outside the backend trust perimeter — every request is re-authenticated server-side
- LLM API is an external call; no clinical facts are trusted from LLM output without graph grounding
- Scraper pipeline writes to the same PostgreSQL as the live API; a separate eval schema (`claims_gold`) provides a staging gate before production rule activation
