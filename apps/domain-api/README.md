# domain-api

Spring Boot Domain API: canonical read API now; user/auth, watched state, memory notes, admin, outbox next.
See `docs/ARCHITECTURE.md` §4.2.

Owns **no schema**. `db/migrations` is applied by Flyway before this service starts
(compose `migrate` service). Tests apply the same migrations into a Testcontainers PostgreSQL.

## Endpoints (v1, public read)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/broadcasters` | |
| GET | `/api/v1/years/{year}?broadcaster=tvn&page=0&size=50` | PUBLISHED only, ordered by start_date |
| GET | `/api/v1/dramas/{slug}` | credits, OST, genres, aliases, live official links. MERGED → 301 to survivor |
| GET | `/api/v1/persons/{slug}` | filmography newest first |
| GET | `/actuator/health` | |

Errors are RFC 9457 problem details.

## Run

```sh
./gradlew test          # needs Docker (Testcontainers)
./gradlew bootRun       # expects postgres on localhost:5432 with migrations applied (make up)
# or, inside compose:
docker compose up -d domain-api   # http://localhost:8081
```

Config via env: `DB_URL`, `DB_USER`, `DB_PASSWORD`, `PORT`.
