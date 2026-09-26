# data-platform

Airflow 3 project for ingestion → normalization → entity resolution → quality gate → gold publish, plus search/graph refresh.

- `dags/` — Airflow DAGs (asset-driven where dependencies are data)
- `src/dramamemory_data/` — importable pipeline code (collectors, parsers, normalization, entity_resolution, quality, graph)
- `tests/` — unit tests for pipeline code, runnable without Airflow

Airflow never sits on the online request path. See `docs/AIRFLOW_DAGS.md`.
