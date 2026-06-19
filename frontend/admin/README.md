# HF CDSS Admin Dashboard

Standalone React app for reviewing constraint rules, evidence chunks, system health, and API exploration.

## Development

```bash
cd frontend/admin
npm install
npm run dev
```

Open http://127.0.0.1:5174

## Environment

Copy `.env.example` to `.env`:

- `VITE_API_BASE_URL` — backend API
- `VITE_DOCTOR_DASHBOARD_URL` — link back to doctor chat app

## Docker

Built as `admin-frontend` service in `infrastructure/docker-compose.yml` on port **5174**.
