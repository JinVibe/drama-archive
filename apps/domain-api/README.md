# domain-api

Spring Boot Domain API: user/auth, watched state, memory notes, admin, canonical read API, outbox.

Scaffolded in Phase 2 (DM-401+). See `docs/ARCHITECTURE.md` §4.2.

Owns no schema migrations of its own — canonical schema lives in `db/migrations` and is applied by Flyway before this service starts.
