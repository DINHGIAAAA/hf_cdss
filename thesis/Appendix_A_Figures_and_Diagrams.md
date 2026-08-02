# APPENDIX A: FIGURES AND DIAGRAMS

Interactive diagrams (Archify, showcase validation) live under [`figures/html/`](figures/html/). Source specs: [`figures/archify/*.json`](figures/archify/). Open any `.html` file in a browser for pan/zoom and theme toggle.

<link rel="stylesheet" href="figures/thesis-figures.css">

---

## Figure A.1: Overall HF-CDSS System Architecture

<figure class="thesis-archify-figure">
  <iframe src="figures/html/figure-a1-architecture.html" title="Figure A.1 HF-CDSS architecture"></iframe>
  <figcaption><strong>Figure A.1.</strong> Overall HF-CDSS architecture (mono-app)</figcaption>
</figure>

---

## Figure A.2: Chat Message Processing Flow

<figure class="thesis-archify-figure">
  <iframe src="figures/html/figure-a2-chat-workflow.html" title="Figure A.2 Chat processing flow"></iframe>
  <figcaption><strong>Figure A.2.</strong> Chat message processing flow from input to recommendation</figcaption>
</figure>

---

## Figure A.3: Knowledge-Base Construction Pipeline

<figure class="thesis-archify-figure">
  <iframe src="figures/html/figure-a3-kb-pipeline.html" title="Figure A.3 KB construction pipeline"></iframe>
  <figcaption><strong>Figure A.3.</strong> Medical knowledge-base construction pipeline</figcaption>
</figure>

### Why is S3 needed if data is synced directly to PostgreSQL?

| Purpose            | Explanation                                                 |
| ------------------ | ----------------------------------------------------------- |
| **Backup**         | If PostgreSQL crashes, data can be restored from S3         |
| **Multi-instance** | Multiple backend instances can load from a single S3 source |
| **ChromaDB/Neo4j** | No direct sync, must go through bootstrap                   |
| **Versioning**     | S3 retains history; rollback is possible                    |

---

## Figure A.4: GraphRAG Architecture

<figure class="thesis-archify-figure">
  <iframe src="figures/html/figure-a4-graphrag.html" title="Figure A.4 GraphRAG architecture"></iframe>
  <figcaption><strong>Figure A.4.</strong> GraphRAG hybrid retrieval architecture</figcaption>
</figure>

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

<figure class="thesis-archify-figure">
  <iframe src="figures/html/figure-a6-frontend-routes.html" title="Figure A.6 Frontend routes"></iframe>
  <figcaption><strong>Figure A.6.</strong> Frontend routing and UI structure</figcaption>
</figure>

---

## Figure A.7: Chat-Flow Sequence Diagram

<figure class="thesis-archify-figure">
  <iframe src="figures/html/figure-a7-chat-sequence.html" title="Figure A.7 Chat sequence"></iframe>
  <figcaption><strong>Figure A.7.</strong> Chat-flow sequence diagram</figcaption>
</figure>

---

## Table A.1: Main System Components

| Component               | Technology       | Port  | Purpose                         |
| ----------------------- | ---------------- | ----- | ------------------------------- |
| **Frontend (Mono App)** | React + Vite     | 5173  | Doctor Dashboard + Admin Portal |
| **Backend API**         | FastAPI + Python | 8000  | Clinical logic                  |
| **LLM Server**          | Ollama           | 11434 | Local LLM inference             |
| **PostgreSQL**          | Database         | 55432 | Rules, audit, chat history      |
| **Neo4j**               | Graph DB         | 7474  | Knowledge graph                 |
| **ChromaDB**            | Vector DB        | 8001  | Evidence embeddings             |
| **Redis**               | Cache            | 6379  | Draft, messages, LLM cache      |
| **LocalStack**          | S3 Emulator      | 4566  | Artifact storage                |

**Table A.1. Main system components and ports**

---

## Table A.2: Frontend Routes

| Route                         | Component              | Description                              |
| ----------------------------- | ---------------------- | ---------------------------------------- |
| `/`                           | HomePage               | Landing page                             |
| `/chat`                       | ChatPage               | Main chat interface                      |
| `/admin`                      | AdminLayout            | Admin portal (redirects to /admin/rules) |
| `/admin/rules`                | RulesPage              | Constraint rules management              |
| `/admin/dose-rules`           | DoseRulesPage          | Dose rules management                    |
| `/admin/dose-safety-warnings` | DoseSafetyWarningsPage | Safety warnings                          |
| `/admin/interaction-rules`    | InteractionRulesPage   | Drug interactions                        |
| `/admin/gdmt-policies`        | GdmtPoliciesPage       | GDMT policies                            |
| `/admin/evidence`             | EvidencePage           | Evidence management                      |
| `/admin/audit`                | AuditPage              | Audit logs                               |
| `/admin/system`               | SystemPage             | System health                            |
| `/admin/api`                  | ApiExplorerPage        | API testing                              |
| `/admin/users`                | UsersPage              | User management (admin only)             |

**Table A.2. Frontend routes**

---

### Regenerating figures

```powershell
cd c:\Users\VinhNgo\hf_cdss
$archify = "$env:USERPROFILE\.agents\skills\archify\bin\archify.mjs"
$fig = "thesis\figures"
node $archify deliver architecture "$fig\archify\figure-a1-architecture.json" "$fig\html\figure-a1-architecture.html" --quality showcase
# … repeat per JSON under thesis/figures/archify/
```
