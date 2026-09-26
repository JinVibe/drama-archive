.PHONY: up down migrate migrate-info logs ps clean

# Local stack (postgres + migrations + redis + minio)
up:
	docker compose up -d postgres redis minio
	docker compose run --rm migrate
	docker compose run --rm minio-init

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
