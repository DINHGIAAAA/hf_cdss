# Local auth seed (development only)

Do not commit `seed_users.json`. Copy `seed_users.example.json` to `seed_users.json` and set a **unique** `password_hash` per user.

## Generate bcrypt hashes (cost factor **12**)

Using project helper (recommended):

```bash
cd backend
python -c "from app.core.passwords import hash_password; print(hash_password('your-password'))"
```

Using bcrypt directly:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt(rounds=12)).decode())"
```

## Example dev passwords

| User | Example password in `seed_users.example.json` |
|------|-----------------------------------------------|
| `admin` | `password123` |
| `clinical_lead` | `clinical_lead_dev` |

Each entry in the example file uses a **different** hash. Do not reuse the same hash across users.

See also `frontend/doctor-dashboard/README.md` for login workflow.
