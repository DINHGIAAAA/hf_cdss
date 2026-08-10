# HF CDSS Frontend

Unified React app for clinical chat and admin governance.

## Routes

| Path | Access |
|------|--------|
| `/login` | Public |
| `/` | Redirect: login / admin / chat |
| `/chat` | Authenticated clinical users |
| `/admin/rules` | `admin` or `clinical_lead` |
| `/admin/evidence` | `admin` or `clinical_lead` |
| `/admin/system` | `admin` or `clinical_lead` |
| `/admin/api` | `admin` or `clinical_lead` |

After login, users with `admin` or `clinical_lead` are routed to `/admin/rules`. Other roles go to `/`.

## Run

```bash
cp .env.example .env
npm install
npm run dev
```

Open http://127.0.0.1:5173

## Dev login

See `.env.example` for `VITE_API_BASE_URL` (leave empty in dev to use the Vite proxy).

## Patient intake and chat latency (clinical safety)

- Fill the **new patient** form with LVEF, eGFR, K+, BP, HR, medications, and conditions before chatting. The app sends `patient` + `draft` on every message (`compactPatientForRequest`), so a complete profile **skips LLM clinical intake** and only applies regex updates from new messages.
- Default NKDA / no acute instability are set when allergy and red-flag fields are left blank so governance checks stay consistent.
- Use **Load demo case** to seed a complete profile without manual entry.

## Backend data and warm caches

After ingestion, ensure published chunks exist and restart the backend once so bootstrap warms BM25, governance catalogs, and the clinical intake medication catalog (`drug_aliases.json`). Edit aliases under `data/heart_failure/config/drug_aliases.json` and restart the backend (or call `invalidate_drug_catalog_cache()` in a running worker) so intake semantic search picks up new trade names.

## Docker: separate chat vs embedding (optional)

In `infrastructure/docker-compose.yml`, chat uses `HF_CDSS_LLM_*` (OpenAI-compatible, default `http://ollama:11434/v1`) and embeddings use `HF_CDSS_EMBEDDING_*` (default `http://ollama:11434`, model `bge-m3`). Pointing both at the same Ollama instance is fine; for heavier load you can run a dedicated embed endpoint without changing CDSS logic.

On first bootstrap, set backend `HF_CDSS_AUTH_SEED_USERS_JSON` or copy `backend/app/data/seed_users.example.json` to `seed_users.json` (gitignored). Dev example: `admin` / `password123`, `clinical_lead` / `password123` (see `backend/app/data/README.md`).
