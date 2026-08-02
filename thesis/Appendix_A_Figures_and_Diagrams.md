# APPENDIX A: FIGURES AND DIAGRAMS

---

## Figure A.1: Overall HF-CDSS System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                      USER                                           │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                                                                   │
│                     DOCTOR DASHBOARD (Mono App)                                 │
│                         Port: 5173 (Vite Dev Server)                            │
│                                                                                   │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                         ROUTING STRUCTURE                                  │   │
│   │                                                                          │   │
│   │   / ──────────────────────┬───────────────────────────────────────     │   │
│   │   │                       │                                              │   │
│   │   ▼                       ▼                                              │   │
│   │   Home Page        ┌─────────────────────────────────────────┐          │   │
│   │                    │           ADMIN SECTION (/admin/*)        │          │   │
│   │                    ├─────────────────────────────────────────┤          │   │
│   │                    │                                         │          │   │
│   │                    │  /admin/rules              → RulesPage   │          │   │
│   │                    │  /admin/dose-rules         → DoseRules  │          │   │
│   │                    │  /admin/dose-safety-warn  → Safety     │          │   │
│   │                    │  /admin/interaction-rules → Interact. │          │   │
│   │                    │  /admin/gdmt-policies     → GDMT       │          │   │
│   │                    │  /admin/evidence          → Evidence   │          │   │
│   │                    │  /admin/audit             → Audit      │          │   │
│   │                    │  /admin/system           → System     │          │   │
│   │                    │  /admin/api              → API Exp. │          │   │
│   │                    │  /admin/users            → Users     │          │   │
│   │                    │                                         │          │   │
│   │                    └─────────────────────────────────────────┘          │   │
│   │                                                                          │   │
│   │   /chat ───────────────────────────────────────────────────────────    │   │
│   │   │                                                                  │   │
│   │   ▼                                                                  │   │
│   │   ChatPage (Doctor Chat + Clinical Panel)                           │   │
│   │                                                                          │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                            │
└────────────────────────────────────┼────────────────────────────────────────────┘
                                     │ REST API / SSE
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              FASTAPI BACKEND                                         │
│                                 Port: 8000                                           │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          API Routes Layer                                    │   │
│  │  /chat, /chat/stream, /recommendation, /retrieval, │   │
│  │  /admin/*, /auth, /evidence, /knowledge-graph, /graphrag, /llm... │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                           │
│  ┌──────────────────────────────────────┼──────────────────────────────────────┐   │
│  │                                 Modules Layer                                │   │
│  │                                                                              │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │   │
│  │  │      Chat       │  │    Reasoning    │  │    GraphRAG     │             │   │
│  │  │ (Orchestration) │  │(Recommendations)│  │   (Retrieval)   │             │   │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │   │
│  │           │                    │                    │                      │   │
│  │  ┌────────▼────────┐  ┌────────▼────────┐  ┌────────▼────────┐             │   │
│  │  │Clinical Intake  │  │  Verification   │  │ Semantic Search │             │   │
│  │  │   Extraction     │  │     Agents     │  │ (Chroma+BM25)  │             │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘             │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                           │
│  ┌──────────────────────────────────────┼──────────────────────────────────────┐   │
│  │                                 Datastores Layer                             │   │
│  │                                                                              │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │   │
│  │  │ PostgreSQL  │ │    Neo4j    │ │   ChromaDB  │ │    Redis     │       │   │
│  │  │ (Rules/     │ │ (Knowledge  │ │  (Vectors)  │ │   (Cache)    │       │   │
│  │  │  Audit)     │ │   Graph)    │ │             │ │              │       │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘       │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              OLLAMA (Local LLM)                                    │
│                                Port: 11434                                          │
│                                                                                      │
│   Models: qwen2.5:7b (generation), qwen2.5:1.5b (agent), bge-m3 (embedding)     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Figure A.1. Overall HF-CDSS architecture (mono-app)**

---

## Figure A.2: Chat Message Processing Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (Doctor Dashboard) - Port 5173                    │
│                                                                                      │
│   Route: /chat                                                                       │
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  ChatPage.jsx                                                             │     │
│   │  ├── ChatMain.jsx (Message thread)                                        │     │
│   │  ├── ClinicalPanel.jsx (Patient info + Recommendations)                   │     │
│   │  ├── ChatInput.jsx (User input)                                          │     │
│   │  └── LanguageToggle.jsx (VI/EN)                                          │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                    │                                                │
│                                    ▼                                                │
│  useChat.js → POST /api/v1/chat/stream (SSE)                                    │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              BACKEND (FastAPI) - Port 8000                         │
│                                                                                      │
│  ┌───────────────────────────────────────────────────────────────────────────┐     │
│  │ 1. CLINICAL INTAKE EXTRACTION                                            │     │
│  │    clinical_intake_extraction/service.py                                   │     │
│  │    ├── Regex: LVEF, eGFR, medications, conditions extraction              │     │
│  │    ├── Semantic: sentence embeddings + similarity                         │     │
│  │    ├── Selective LLM: confidence < 0.75 → call LLM                     │     │
│  │    └── Merge → PatientProfile                                             │     │
│  └───────────────────────────────────────────────────────────────────────────┘     │
│                                    │                                                │
│                                    ▼                                                │
│  ┌───────────────────────────────────────────────────────────────────────────┐     │
│  │ 2. MISSING FIELDS CHECK                                                   │     │
│  │    Validate: LVEF, eGFR, potassium, BP, HR, age, sex                 │     │
│  └───────────────────────────────────────────────────────────────────────────┘     │
│                                    │                                                │
│                                    ▼                                                │
│  ┌───────────────────────────────────────────────────────────────────────────┐     │
│  │ 3. RECOMMENDATION ENGINE                                                  │     │
│  │    reasoning/service.py                                                   │     │
│  │    ├── Normalize patient → ClinicalProfile                               │     │
│  │    ├── Extract risks (CKD, hyperkalemia, hypotension)                  │     │
│  │    ├── Build constraints (avoid/caution)                                 │     │
│  │    ├── Check dose safety & drug interactions                            │     │
│  │    ├── Apply GDMT policies → recommendations per drug class            │     │
│  │    └── Build dose plans (titration steps)                              │     │
│  └───────────────────────────────────────────────────────────────────────────┘     │
│                                    │                                                │
│                                    ▼                                                │
│  ┌───────────────────────────────────────────────────────────────────────────┐     │
│  │ 4. GRAPHRAG CONTEXT                                                      │     │
│  │    graphrag/service.py                                                    │     │
│  │    ├── HyDE: Generate hypothetical document                              │     │
│  │    ├── Query decomposition                                                │     │
│  │    ├── Parallel retrieval: ChromaDB + BM25 + Neo4j                      │     │
│  │    ├── Reciprocal Rank Fusion (RRF)                                       │     │
│  │    └── Semantic reranking (Cohere)                                       │     │
│  └───────────────────────────────────────────────────────────────────────────┘     │
│                                    │                                                │
│                                    ▼                                                │
│  ┌───────────────────────────────────────────────────────────────────────────┐     │
│  │ 5. VERIFICATION AGENTS                                                   │     │
│  │    verification_agents/service.py                                         │     │
│  │    ├── safety_agent: Check "avoid" constraints                          │     │
│  │    ├── evidence_agent: Verify evidence retrieval                          │     │
│  │    ├── guideline_alignment_agent: Check references                        │     │
│  │    └── final_reviewer_agent: Overall verdict                             │     │
│  └───────────────────────────────────────────────────────────────────────────┘     │
│                                    │                                                │
│                                    ▼                                                │
│  ┌───────────────────────────────────────────────────────────────────────────┐     │
│  │ 6. EXPLANATION & ANSWER GENERATION                                      │     │
│  │    explanation/llm_service.py                                            │     │
│  │    ├── Compact recommendation to structured format                       │     │
│  │    ├── Cache lookup (Redis)                                              │     │
│  │    ├── If miss: call LLM (qwen2.5:7b)                                  │     │
│  │    └── Stream tokens via SSE                                              │     │
│  └───────────────────────────────────────────────────────────────────────────┘     │
│                                    │                                                │
│                                    ▼                                                │
│                          SSE Response Stream                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND - SSE Event Handlers                              │
│                                                                                      │
│   clinicalChatStream.js:                                                            │
│   ├── draft_ready        → updateActive({ draft: patient })                       │
│   ├── recommendation_ready → updateActive({ recommendation })                      │
│   ├── verification_ready → updateActive({ verification })                        │
│   ├── answer_delta       → appendAssistantMessage(content)                         │
│   └── done              → finalizeState()                                          │
│                                                                                      │
│   ClinicalPanel.jsx:                                                                │
│   └── Display: Patient Summary, GDMT Status, Recommendation Cards                 │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Figure A.2. Chat message processing flow from input to recommendation**

---

## Figure A.3: Knowledge-Base Construction Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                 DATA SOURCES                                        │
│                                                                                      │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│   │ FDA Drug Labels │  │ Clinical        │  │ Drug Interaction │               │
│   │ (XML/SPL)       │  │ Guidelines (PDF)│  │ Databases       │               │
│   │ DailyMed        │  │ ESC, AHA/ACC   │  │ DrugBank        │               │
│   └────────┬────────┘  └────────┬────────┘  └────────┬────────┘               │
└────────────┼─────────────────────┼─────────────────────┼──────────────────────────┘
             │                     │                     │
             └─────────────────────┼─────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: ACQUIRE (scraper/acquisition/)                                       │
│                                                                                      │
│   download_sources.py                                                                │
│   ├── HTTP/DailyMed downloads                                                      │
│   └── Upload to S3 raw bucket (hf-cdss-raw)                                        │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  STAGE 2: LOAD (Ephemeral Staging)                                           │
│                                                                                      │
│   ├── Sync from S3 raw bucket to staging                                            │
│   └── Validate file formats                                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: EXTRACT                                                            │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ 3a. KG_BASE                                                              │     │
│   │     ├── parse_guideline_pdf / html / drug_label_xml                     │     │
│   │     ├── extract_important_sections (keyword + semantic + LLM)           │     │
│   │     ├── chunk_sections → artifacts/chunks/                              │     │
│   │     ├── extract_entities → artifacts/entities/                          │     │
│   │     └── create_claims → artifacts/claims/                              │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ 3b. CATALOGS (Governance)                                              │     │
│   │     ├── constraints → artifacts/rules/constraints_classified.jsonl      │     │
│   │     ├── dose_rules → artifacts/rules/dose_rules_classified.jsonl         │     │
│   │     ├── interaction_rules → artifacts/rules/interaction_rules_classified.jsonl│   │
│   │     ├── dose_safety_warnings                                           │     │
│   │     └── gdmt_policies → artifacts/rules/gdmt_policies_classified.jsonl   │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  STAGE 4: STORE                                                             │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ A. Long-term Storage (S3)                                              │     │
│   │    ├── Promote to hf-cdss-processed/heart_failure/current/            │     │
│   │    └── Purpose: Backup, versioning, multi-server deployment            │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ B. Direct Sync → PostgreSQL (Governance Catalogs)                    │     │
│   │    ├── constraint_rules                                               │     │
│   │    ├── dose_rules                                                     │     │
│   │    ├── interaction_rules                                               │     │
│   │    ├── gdmt_policies                                                  │     │
│   │    └── dose_safety_warnings                                          │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ Backend Startup (Bootstrap)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  BOOTSTRAP (Backend app/main.py)                                                │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ A. Load from S3 → local data/heart_failure/                          │     │
│   │    └── Download artifacts from S3 processed bucket                       │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ B. Index → ChromaDB                                                   │     │
│   │    └── artifacts/chunks/*.jsonl → Vector embeddings                   │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ C. Import → Neo4j                                                     │     │
│   │    └── artifacts/entities/*.jsonl → Nodes + Edges                     │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│   NOTE: PostgreSQL governance catalogs were ALREADY SYNCED in the STORE step, no reload needed │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Figure A.3. Medical knowledge-base construction pipeline**

### Why is S3 needed if data is synced directly to PostgreSQL?

| Purpose | Explanation |
|---------|-------------|
| **Backup** | If PostgreSQL crashes, data can be restored from S3 |
| **Multi-instance** | Multiple backend instances can load from a single S3 source |
| **ChromaDB/Neo4j** | No direct sync, must go through bootstrap |
| **Versioning** | S3 retains history; rollback is possible |

---

## Figure A.4: GraphRAG Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              GRAPHRAG - Hybrid Retrieval                            │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                    User Query
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           QUERY PROCESSING                                          │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ 1. HyDE Expansion (hyde_expansion.py)                                  │     │
│   │    LLM generates hypothetical relevant document                          │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
│                                        │                                            │
│                                        ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ 2. Query Decomposition (query_decomposition.py)                         │     │
│   │    Split into targeted search queries                                     │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           RETRIEVAL LAYER                                          │
│                                                                                      │
│   ┌───────────────────────────┐    ┌───────────────────────────────────────┐     │
│   │      ChromaDB             │    │              Neo4j                     │     │
│   │   Vector Search           │    │        Knowledge Graph                 │     │
│   │   (bge-m3 embeddings)    │    │                                       │     │
│   │                           │    │  Drug ────treats───→ Disease          │     │
│   │  • Evidence chunks       │    │  Drug ──contraind──→ Drug           │     │
│   │  • Drug labels            │    │  Drug ──interacts──→ Lab            │     │
│   │  • Guideline text        │    │                                       │     │
│   └───────────────────────────┘    └───────────────────────────────────────┘     │
│               │                                    │                              │
│               │     ┌────────────────────────┐   │                              │
│               │     │       BM25             │   │                              │
│               │     │   Keyword Search       │   │                              │
│               │     └────────────────────────┘   │                              │
│               └────────────────┬─────────────────┘                              │
│                                │                                                  │
│                                ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ Reciprocal Rank Fusion (RRF)                                          │     │
│   │ Score = Σ 1/(k + rank_i) per retriever                               │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
│                                │                                                  │
│                                ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────┐     │
│   │ Semantic Reranking (Cohere)                                             │     │
│   │ Reorder top-K by semantic relevance                                    │     │
│   └─────────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                              Final Context Chunks
```

**Figure A.4. GraphRAG hybrid retrieval architecture**

---

## Figure A.5: Database Schema Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    PostgreSQL (Port 55432)                          │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │  GOVERNANCE TABLES                    │  CHAT TABLES                           │  │
│  ├──────────────────────────────────────┼───────────────────────────────────────┤  │
│  │  constraint_rules + _history          │  chat_conversations                    │  │
│  │  dose_rules + _history               │  chat_messages                         │  │
│  │  interaction_rules + _history         │  chat_patient_drafts                   │  │
│  │  gdmt_policies + _history            │                                        │  │
│  │  dose_safety_warnings + _history     │                                        │  │
│  ├──────────────────────────────────────┼───────────────────────────────────────┤  │
│  │  users                               │  cdss_audit_events                     │  │
│  └──────────────────────────────────────┴───────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│  Neo4j (7474)                              │  ChromaDB (8001)                       │
│  Heart-failure knowledge graph             │  heart_failure_evidence collection      │
│  Entity types: Drug, DrugClass, Disease,  │  BGE-M3 384-d embeddings               │
│  LabConcept, Condition, Guideline          │  metadata: source, drug_class,          │
│  Relationship types: TREATED_BY,          │  section, chunk_type                   │
│  CONTRAINDICATED_WITH, INDICATED_FOR,    │                                        │
│  INTERACTS_WITH, MONITORS, RELATED_TO     │                                        │
├───────────────────────────────────────────┴───────────────────────────────────────┤
│  Redis (6379)                              │  S3 / LocalStack (4566)               │
│  draft:{conversation_id}                  │  raw bucket: DailyMed XML/SPL,         │
│  messages:{conversation_id}               │  guideline PDFs                        │
│  llm_cache:{hash}, idempotency:{hash}    │  processed bucket: JSONL chunks,       │
│  constraint_cache:{drug_class}            │  rule exports, graph artifacts         │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Figure A.5. Database schema overview**

For detailed table schemas with all columns, data types, constraints, and indexes, see **Appendix B: Database Schema Reference**.

## Figure A.6: Frontend Routing and UI Structure

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                     DOCTOR DASHBOARD - ROUTING STRUCTURE                        │
│                            Port 5173 (Single App)                                │
└─────────────────────────────────────────────────────────────────────────────────────┘

                          ┌─────────────────────┐
                          │     / (Home)       │
                          │    HomePage.jsx     │
                          └──────────┬──────────┘
                                     │
         ┌─────────────────────────────┼─────────────────────────────┐
         │                           │                             │
         ▼                           ▼                             ▼
┌─────────────────────┐     ┌───────────────────────────────────────────────┐
│   /chat             │     │              /admin/*                        │
│   ChatPage.jsx     │     │           AdminLayout.jsx                    │
│                     │     │                                               │
│ ┌─────────────────┐ │     │  ┌─────────────────────────────────────────┐  │
│ │ ChatMain.jsx   │ │     │  │ Sidebar Navigation                   │  │
│ │ (Messages)     │ │     │  │                                      │  │
│ └────────┬────────┘ │     │  │ • /admin/rules                     │  │
│          │            │     │  │ • /admin/dose-rules                │  │
│ ┌────────▼────────┐ │     │  │ • /admin/dose-safety-warnings     │  │
│ │ClinicalPanel.jsx │ │     │  │ • /admin/interaction-rules         │  │
│ │                 │ │     │  │ • /admin/gdmt-policies             │  │
│ │ • Patient Info  │ │     │  │ • /admin/evidence                 │  │
│ │ • GDMT Status  │ │     │  │ • /admin/audit                    │  │
│ │ • Recommendations│ │     │  │ • /admin/system                   │  │
│ │ • Dose Plans   │ │     │  │ • /admin/api                      │  │
│ └─────────────────┘ │     │  │ • /admin/users (admin only)       │  │
└─────────────────────┘     │  └─────────────────────────────────────────┘  │
                            │                                               │
                            │  ┌─────────────────────────────────────────┐  │
                            │  │ Page Content (RulesPage.jsx, etc.)     │  │
                            │  │                                      │  │
                            │  │ ┌─────────────────────────────────┐ │  │
                            │  │ │ Stats: Draft | Approved | Retired │ │  │
                            │  │ └─────────────────────────────────┘ │  │
                            │  │ ┌─────────────────────────────────┐ │  │
                            │  │ │ Tab Navigation                   │ │  │
                            │  │ │ [All] [Draft] [Approved] [Ret.] │ │  │
                            │  │ └─────────────────────────────────┘ │  │
                            │  │ ┌─────────────────────────────────┐ │  │
                            │  │ │ Rules Table with Filters        │ │  │
                            │  │ │ - Constraint ID                 │ │  │
                            │  │ │ - Drug Class                    │ │  │
                            │  │ │ - Action                        │ │  │
                            │  │ │ - Safety Tier                  │ │  │
                            │  │ └─────────────────────────────────┘ │  │
                            │  └─────────────────────────────────────────┘  │
                            └───────────────────────────────────────────────┘
```

**Figure A.6. Frontend routing and UI structure**

---

## Figure A.7: Chat-Flow Sequence Diagram

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Doctor  │     │Frontend  │     │  FastAPI │     │ Services │     │   LLM    │
│          │     │Dashboard  │     │  Backend │     │          │     │ (Ollama) │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │                │
     │ 1. Input msg  │                │                │                │
     │───────────────>│                │                │                │
     │                │                │                │                │
     │                │ 2. POST /chat/stream             │                │
     │                │───────────────>│                │                │
     │                │                │                │                │
     │                │                │ 3. Extract patient               │
     │                │                │───────────────>│                │
     │                │                │<───────────────│                │
     │                │                │                │                │
     │                │                │ 4. Check missing fields        │
     │                │                │───────────────>│                │
     │                │                │<───────────────│                │
     │                │                │                │                │
     │                │                │ 5. Build recommendation         │
     │                │                │───────────────>│                │
     │                │                │<───────────────│                │
     │                │                │                │                │
     │                │                │ 6. GraphRAG retrieval            │
     │                │                │───────────────>│                │
     │                │                │<───────────────│                │
     │                │                │                │                │
     │                │                │ 7. Verify & Generate answer     │
     │                │                │───────────────────────────────>│
     │                │                │<────────────────────────────────│
     │                │                │                │                │
     │                │ 8. SSE: recommendation_ready              │
     │                │<───────────────│                │                │
     │                │                │                │                │
     │                │ 9. SSE: answer_delta                   │
     │                │<───────────────│                │                │
     │                │                │                │                │
     │ 10. Display  │                │                │                │
     │<──────────────│                │                │                │
     │                │                │                │                │
```

**Figure A.7. Chat-flow sequence diagram**

---

## Table A.1: Main System Components

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

**Table A.1. Main system components and ports**

---

## Table A.2: Frontend Routes

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

**Table A.2. Frontend routes**
