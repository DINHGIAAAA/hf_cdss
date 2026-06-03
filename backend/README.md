# Backend

FastAPI modular monolith. API routers stay thin; clinical and reasoning logic belongs in `app/modules`.

## Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

