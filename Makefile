COMPOSE := docker compose -f infrastructure/docker-compose.yml

.PHONY: start start-detached stop logs test seed evaluate airflow

start:
	$(COMPOSE) up --build

start-detached:
	$(COMPOSE) up -d --build

stop:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

airflow:
	$(COMPOSE) --profile airflow up -d --build airflow

test:
	cd backend && python -m pytest

seed:
	cd backend && python -m app.scripts.bootstrap_datastores

evaluate:
	cd backend && python -m pytest app/tests/test_sample_cases.py app/tests/test_week2_synthetic_cases.py
