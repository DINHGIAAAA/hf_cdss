# Architecture

The thesis implementation uses a modular monolith for speed and stability. Module boundaries are shaped so they can later be extracted into services.

## Deployment Shape

The day-1 implementation runs as a small local stack:

- FastAPI backend for API contracts and domain orchestration.
- React/Vite doctor dashboard for demo workflows.
- PostgreSQL for future structured persistence.
- Neo4j for future knowledge graph storage.
- ChromaDB for future vector retrieval.

The backend is currently the only service with implemented application logic. Database containers are included so the local environment mirrors the planned architecture early.

## Backend Boundaries

API routes stay thin and return Pydantic response models. Business logic belongs in `app/modules`.

Initial module boundaries:

- `patient`: patient profile contracts and validation helpers.
- `clinical_normalization`: clinical value normalization.
- `risk_extraction`: patient risk flag extraction.
- `constraint_builder`: personalized clinical constraints.
- `knowledge_graph`: Neo4j schema, seed data, and graph queries.
- `vector_retrieval`: guideline and drug-label chunk retrieval.
- `graphrag`: combines graph and vector context.
- `reasoning`: structured medication recommendation generation.
- `dose_checking`: dose and renal adjustment checks.
- `interaction_checking`: drug-drug and drug-condition checks.
- `verification_agents`: safety, dose, interaction, guideline, evidence, and final reviewer agents.
- `explanation`: physician-facing rationale and reasoning path.
- `audit`: input, context, output, and verification trail.
- `evaluation`: baseline, ablation, metrics, and report generation.

## Core Flow

1. Patient profile ingestion.
2. Clinical normalization.
3. Risk extraction.
4. Constraint building.
5. Knowledge graph retrieval.
6. Vector retrieval.
7. GraphRAG context assembly.
8. Reasoning.
9. Dose, interaction, guideline, and evidence verification.
10. Explanation and audit logging.

## API Principles

- All API responses use Pydantic schemas.
- Controllers do not hardcode medical rules.
- Clinical decision logic lives inside domain modules or rule files.
- Recommendation output must include evidence or constraint references.
- Errors use a structured `error.code`, `error.message`, and optional `error.details` shape.
- Every medical output includes the clinical decision support disclaimer.

## Data Principles

The initial data model is intentionally compact and thesis-friendly:

- Patient profiles capture the minimum clinical variables needed for HFrEF-focused GDMT decisions.
- Medication records focus on drug class, contraindications, and monitoring requirements.
- Observations preserve raw clinical values.
- Diagnoses connect patient cases to heart failure type and comorbidities.
- Recommendations store patient summary, risk flags, recommendation decisions, and disclaimer.
- Audit logs store the full trace needed to explain and reproduce a recommendation.

## Day-1 Runtime

Local backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Local frontend:

```bash
cd frontend/doctor-dashboard
npm install
npm run dev
```

Docker stack:

```bash
cd infrastructure
docker compose up --build
```

## Later Extraction Path

If the project grows beyond the modular monolith, modules can be extracted into services in this order:

1. Retrieval service for Neo4j and vector context.
2. Verification service for multi-agent checks.
3. Audit service for durable case traces.
4. Evaluation service for batch experiments.

The day-1 repo keeps these boundaries visible without paying the operational cost of microservices too early.

## Week-1 Completion Matrix

| Area | Artifact | Status |
| --- | --- | --- |
| Repository foundation | `README.md`, folder layout, `.gitignore` | Done |
| Backend skeleton | FastAPI app, routes, config, logging, error handlers | Done |
| Frontend skeleton | React/Vite doctor dashboard with `/health` check | Done |
| Runtime | Docker Compose with backend, frontend, PostgreSQL, Neo4j, ChromaDB | Done |
| Data contracts | Pydantic schemas and `docs/data_schema.md` | Done |
| Sample data | 10 synthetic patient profiles | Done |
| Research scope | data sources, data scope, medication scope, comorbidity scope, guideline scope, GDMT groups, risk table | Done |
| Report draft | Chapter 1 and Chapter 3 notes | Done |
| Tests | health, version, validation, recommendation contract, sample cases | Done |

## Week-2 Clinical Pipeline

Week 2 adds the first medical extraction pipeline:

1. `clinical_normalization` maps raw patient fields into normalized HF, renal, potassium, BP, HR, comorbidity, medication, and allergy fields.
2. `risk_extraction` emits structured risk flags with severity and evidence.
3. `constraint_builder` applies JSON rules to generate medication-class constraints.

The API surface is:

- `POST /normalize`
- `POST /risks`
- `POST /constraints`

The data artifacts are:

- `data/heart_failure/evaluation/synthetic_cases/week2_30_cases.json`
- `data/heart_failure/evaluation/gold_labels/week2_expected_risks.json`
- `backend/app/modules/constraint_builder/rules/constraints_v1.json`

## Week-1 Runtime Contract

The first milestone proves that the stack can be started locally and that the frontend can reach the backend. The original `/recommend` route stabilized the response shape so downstream UI and test work could depend on it.

## Week-3 Clinical Recommendation MVP

Week 3 upgrades `/recommend` from a placeholder contract into a rule-based clinical MVP:

1. `reasoning` calls `clinical_normalization`, `risk_extraction`, and `constraint_builder`.
2. The response includes patient summary, risk flags, medication constraints, recommendation statuses, overall status, and disclaimer.
3. Each recommendation includes warning text and `constraint_ids` when patient-specific constraints apply.
4. Hard constraints convert the affected medication class to `avoid`.
5. The React dashboard calls `/recommend` for sample cases and displays clinical summary, risks, constraints, and medication-class decisions.

## Traceability Strategy

Future modules should preserve a trace from input to output:

1. Raw request payload.
2. Normalized patient summary.
3. Risk flags and constraints.
4. Graph facts and vector evidence chunks.
5. Reasoning output.
6. Verification results.
7. Final physician-facing explanation.

This trace will support the audit log and thesis evaluation. Week 1 defines the fields; later weeks will fill them with real context.

## Safety Boundary

The application is clinical decision support only. It must not present recommendations as autonomous prescriptions. The backend response includes a disclaimer from the first milestone, and the frontend should preserve that disclaimer anywhere medical output is shown.
