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

On first bootstrap, set backend `HF_CDSS_AUTH_SEED_USERS_JSON` or copy `backend/app/data/seed_users.example.json` to `seed_users.json` (gitignored). Example dev users: `admin` / `password123`, `clinical_lead` / `password123` (bcrypt cost 12).
