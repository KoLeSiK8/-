# Shortcuts for the churn risk analyzer. Requires Docker Compose; the test and
# openapi targets also work from a local virtualenv with backend/requirements.txt.

PYTHON ?= python3
TEST_DATABASE_URL ?= postgresql+psycopg://churn:churn@localhost:5432/churn_test

.PHONY: up down reset logs test test-docker openapi demo-data frontend-build

up:            ## build and start db, api and web on http://localhost:8081
	docker compose up -d --build

down:
	docker compose down

reset:         ## wipe the database volume and start from scratch
	docker compose down -v
	docker compose up -d --build

logs:
	docker compose logs -f api

test:          ## backend tests against a local PostgreSQL test database
	cd backend && DATABASE_URL=$(TEST_DATABASE_URL) $(PYTHON) -m pytest -q

test-docker:   ## backend tests inside the api container (uses a separate database)
	docker compose exec db psql -U churn -d churn -tc "SELECT 1 FROM pg_database WHERE datname='churn_test'" | grep -q 1 \
		|| docker compose exec db createdb -U churn churn_test
	docker compose exec -e DATABASE_URL=postgresql+psycopg://churn:churn@db:5432/churn_test api python -m pytest -q backend/tests

openapi:       ## regenerate openapi.yml from the FastAPI app
	$(PYTHON) tools/export_openapi.py

demo-data:     ## regenerate data/demo.json and data/demo-step2.json
	$(PYTHON) tools/generate_demo.py --accounts 200 --seed 42 --out data/demo.json --step2-out data/demo-step2.json

frontend-build:
	cd frontend && npm ci && npm run build
