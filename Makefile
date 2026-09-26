.PHONY: up down migrate migrate-info logs ps clean

# Local stack (postgres + migrations + redis + object storage)
up:
	docker compose up -d postgres redis objectstore
	docker compose run --rm migrate
	docker compose run --rm objectstore-init

down:
	docker compose down

migrate:
	docker compose run --rm migrate

migrate-info:
	docker compose run --rm migrate info

logs:
	docker compose logs -f

ps:
	docker compose ps

# Destroys volumes. Use when you need a clean database.
clean:
	docker compose down -v

# Airflow (api-server on :8080, no login locally)
airflow-up:
	docker compose up -d airflow-apiserver airflow-scheduler airflow-dag-processor airflow-triggerer

airflow-down:
	docker compose stop airflow-apiserver airflow-scheduler airflow-dag-processor airflow-triggerer

airflow-cli:
	docker compose run --rm airflow-cli $(ARGS)

dag-errors:
	docker compose run --rm airflow-cli dags list-import-errors

# Pipeline unit tests + lint, run inside the Airflow image (same Python/deps as production)
test-data:
	docker compose run --rm --entrypoint bash -v ./data-platform:/workspace -w /workspace airflow-cli -c "pip install -q pytest ruff && ruff check . && pytest -q"

# Same DAG import check CI runs
dag-check:
	docker run --rm -v "$(CURDIR)/data-platform:/workspace" -w /workspace -e PYTHONPATH=/workspace/src -e AIRFLOW__CORE__LOAD_EXAMPLES=false -e AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////tmp/ci.db --entrypoint python apache/airflow:3.3.0-python3.12 -c "from airflow.models import DagBag; b=DagBag('dags'); assert not b.import_errors, b.import_errors; print(sorted(b.dag_ids))"
