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

Configure backend `HF_CDSS_AUTH_DEV_USERS_JSON`. Example: `ngovinh` / `password123` (admin + clinical_lead).
