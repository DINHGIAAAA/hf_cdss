# Local auth seed (development only)

Do not commit `seed_users.json`. Copy `seed_users.example.json` and replace `password_hash` values.

Generate a bcrypt hash (cost factor **12**):

```bash
cd backend
python -c "from app.core.passwords import hash_password; print(hash_password('your-password'))"
```

The example file ships with cost-12 hashes for the dev password documented in `frontend/doctor-dashboard/README.md`.
