# db

Canonical PostgreSQL schema, applied with Flyway.

- `init/` — one-time container init scripts (runs only on an empty data volume)
- `migrations/` — versioned Flyway migrations `V{n}__{description}.sql`

Rules:

- PostgreSQL is the System of Record. Vector index / Neo4j are derived and re-creatable from here.
- Never edit an applied migration; add a new version.
- Schema follows `docs/DATA_MODEL.md`. If they diverge, update the doc in the same commit.

Apply locally:

```sh
make migrate        # or: docker compose run --rm migrate
make migrate-info   # show applied/pending versions
```
