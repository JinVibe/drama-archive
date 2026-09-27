from __future__ import annotations

from psycopg_pool import ConnectionPool

from ai_api.config import settings


def make_pool() -> ConnectionPool:
    s = settings()
    return ConnectionPool(
        conninfo=s.db_url,
        min_size=1,
        max_size=s.db_pool_size,
        open=False,
        kwargs={"autocommit": True},
    )
