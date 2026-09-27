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

## Endpoints (v1, user state — guest-first, ADR-011)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/me` | `{userId, anonymous, displayName}`; without a session `userId` is absent. Never creates a user |
| GET | `/api/v1/me/dramas` | watched/watching/want-to-watch, newest first; empty without a session |
| PUT | `/api/v1/me/dramas/{id}/status` | body `{status: WATCHED\|WATCHING\|WANT_TO_WATCH, rating?: 0.5–5.0, firstWatchedYear?}`. **First write creates an anonymous user and sets the `dm_uid` cookie** |
| DELETE | `/api/v1/me/dramas/{id}/status` | 204 / 404 |

| GET | `/api/v1/me/dramas/{id}/note`, PUT, DELETE | private one-line memory note (1–500 chars) |
| GET | `/api/v1/me/timeline` | counts by status, watched-by-year, broadcaster/genre ratios, top actors |

## Search (v1, lexical)

`GET /api/v1/search?q=&size=` — full-text (`simple` config, title/alias weight A, body weight B) and
`pg_trgm` partial matching on title/aliases, fused with **RRF (k=60)**. Response carries `strategy`
(`FTS` / `TRIGRAM` / `FUSED` / `NONE`) and per-hit `inFts` / `inTrigram` for the evidence UI.
Every query is logged to `search_query_log` (no user id); zero-result queries feed alias curation.

Session cookie: `dm_uid = <uuid>.<hmac-sha256>`, HttpOnly, SameSite=Lax, 1 year. The HMAC key is
`SESSION_COOKIE_SECRET` (>= 32 bytes; rotating it logs everyone out). Set `SESSION_COOKIE_SECURE=true`
behind https. A cookie for a MERGED account is transparently re-issued for the survivor.

Every write inserts an `outbox_event` in the same transaction. This path never depends on the
AI subsystem.

Social login: `IdentityService.link(...)` implements linking + the merge rules (ADR-011 §7) and is
covered by tests; the Kakao/Naver/Google OAuth callbacks that call it are added once provider apps
are registered.

## Run

```sh
./gradlew test          # needs Docker (Testcontainers)
./gradlew bootRun       # expects postgres on localhost:5432 with migrations applied (make up)
# or, inside compose:
docker compose up -d domain-api   # http://localhost:8081
```

Config via env: `DB_URL`, `DB_USER`, `DB_PASSWORD`, `PORT`.
