# Heart Failure Medication Decision Support System

Modular monolith demo for a heart failure medication clinical decision support system based on GraphRAG and multi-agent verification.

## Repository Structure

```text
frontend/
  doctor-dashboard/

backend/
  app/
    api/
    core/
    modules/
    schemas/
    tests/

data/
  raw/
  processed/
  synthetic_cases/
  gold_labels/
  guideline_chunks/
  kg_seed/

infrastructure/
  docker-compose.yml
  neo4j/
  chromadb/
  postgres/

docs/
  architecture.md
  api_spec.md
  data_schema.md
  data_sources.md
  data_scope.md
  medication_scope.md
  comorbidity_scope.md
  week2_clinical_pipeline.md
  thesis_notes.md
  evaluation_report.md
```

## Local Development

Copy environment defaults:

```bash
cp .env.example backend/.env
```

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend/doctor-dashboard
npm install
npm run dev
```

Docker:

```bash
cd infrastructure
docker compose up --build
```

## Day 1 Verification

- Backend health: `GET http://localhost:8000/health`
- Backend version: `GET http://localhost:8000/version`
- Frontend dashboard: `http://localhost:5173`
- Docker Compose entrypoint: `infrastructure/docker-compose.yml`

The first day focuses on a runnable foundation. Clinical normalization, risk extraction, constraints, knowledge graph ingestion, and GraphRAG logic are intentionally left for later milestones.
