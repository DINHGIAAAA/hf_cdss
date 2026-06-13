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
  week3_clinical_mvp.md
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

Docker services:

- Frontend dashboard: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Ollama local LLM: `http://localhost:11434`
- PostgreSQL: `localhost:55432` mapped to container port `5432`
- Neo4j Browser: `http://localhost:7474`
- ChromaDB: `http://localhost:8001`
- LocalStack S3: `http://localhost:4566`

## Docker Demo Flow

Run these commands from the repository root: `C:\Users\VinhNgo\hf_cdss`.

1. Prepare environment:

```powershell
Copy-Item infrastructure/.env.example infrastructure/.env -ErrorAction SilentlyContinue
```

2. Start infrastructure services first:

```powershell
docker compose -f infrastructure/docker-compose.yml up -d postgres neo4j chromadb localstack ollama ollama-pull
```

3. Confirm the embedding and chat models are available:

```powershell
docker exec hf_cdss_ollama ollama list
```

Expected models for the current backend:

```text
qwen2.5:7b
qwen2.5:1.5b
bge-m3
```

If `bge-m3` is missing:

```powershell
docker exec hf_cdss_ollama ollama pull bge-m3
```

4. Build or refresh scraped and processed data.

Use this when LocalStack was recreated, raw files changed, or you want a clean demo dataset:

```powershell
python -m scraper.acquisition.download_sources --registry data/heart_failure/sources/sources.example.json --bucket hf-cdss-raw --prefix heart_failure --endpoint-url http://localhost:4566
python -m scraper.orchestration.run_ingestion_pipeline --skip-download --s3-endpoint-url http://localhost:4566
```

If data was already scraped and validated locally, only upload processed artifacts:

```powershell
python -m scraper.store.sync_processed_to_s3 --bucket hf-cdss-processed --prefix heart_failure --endpoint-url http://localhost:4566
```

5. Start the demo UI and API with the default dependency flow.

Backend startup automatically loads processed artifacts from S3 into PostgreSQL, Neo4j, and ChromaDB. It can take several minutes because embeddings are generated with `bge-m3`.

```powershell
docker compose -f infrastructure/docker-compose.yml up -d --build backend frontend
```

For a fast UI demo, use deterministic hashing embeddings before starting backend. This still uses the scraped/processed evidence data, but skips slow Ollama embedding calls:

```powershell
$env:HF_CDSS_EMBEDDING_PROVIDER="hashing"
docker compose -f infrastructure/docker-compose.yml up -d --build backend frontend
```

For the full semantic embedding path, keep the default Ollama embedding provider and expect indexing to take longer.

6. Open and test:

- Frontend dashboard: `http://localhost:5173`
- Backend API docs: `http://localhost:8000/docs`
- Backend readiness: `http://localhost:8000/health/ready`
- Metrics: `http://localhost:8000/metrics`

In the frontend, enter patient demographics and clinical values, optionally upload clinical text files/images, then ask a clinical question in chat. Evidence cards should include source metadata and clickable source links.

If LocalStack fails with `port is already allocated`, stop the old container that is using port `4566`, then rerun the compose command:

```powershell
docker ps --filter publish=4566
docker stop <container_name_or_id>
```

### Local LLM

The explanation layer can call either OpenAI Responses API or a local OpenAI-compatible chat-completions server.

Docker Compose starts Ollama automatically and pulls the configured model on first startup:

```env
HF_CDSS_OPENAI_API_KEY=""
OLLAMA_MODEL="qwen2.5:7b"
OLLAMA_KEEP_ALIVE="24h"
HF_CDSS_LLM_BASE_URL="http://ollama:11434/v1"
HF_CDSS_LLM_MODEL="qwen2.5:7b"
HF_CDSS_LLM_API_TYPE="chat_completions"
HF_CDSS_LLM_TIMEOUT_SECONDS="90"
```

Then start the full stack:

```bash
cd infrastructure
docker compose up -d --build
```

The first run can take several minutes while `ollama-pull` downloads the model into the persistent `ollama_data` volume.

## Current Verification

- Backend health: `GET http://localhost:8000/health`
- Backend version: `GET http://localhost:8000/version`
- Clinical pipeline: `POST http://localhost:8000/normalize`, `/risks`, `/constraints`
- Recommendation MVP: `POST http://localhost:8000/recommend`
- Dose checking: `POST http://localhost:8000/dose/check`
- Interaction checking: `POST http://localhost:8000/interaction/check`
- GraphRAG context: `POST http://localhost:8000/graphrag/context`
- Verification agents: `POST http://localhost:8000/verify`
- Frontend dashboard: `http://localhost:5173`
- Docker Compose entrypoint: `infrastructure/docker-compose.yml`

The current backend includes the Week 7 clinical safety flow: normalization, risk extraction, constraint rules, GraphRAG retrieval, dose checking, interaction checking, hybrid verification agents, audit logging, and constraint-aware medication-class recommendations.
