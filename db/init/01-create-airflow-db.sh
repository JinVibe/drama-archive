#!/bin/bash
# Runs once on first PostgreSQL container start.
# Creates a separate database for Airflow metadata so it never shares
# tables with the canonical dramamemory database.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE "${AIRFLOW_DB:-airflow}" OWNER "$POSTGRES_USER";
EOSQL
