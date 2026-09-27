"""DAG `anonymous_user_cleanup` — docs/AIRFLOW_DAGS.md §17a, ADR-011 §6.

Daily. Deletes anonymous users idle for 90+ days in small batches so the online
write path never waits on a long-running delete. Logged-in users (anonymous =
false) and MERGED rows are never touched; user_drama_state / user_consent /
user_identity go with the user via ON DELETE CASCADE.
"""

from __future__ import annotations

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task

POSTGRES_CONN_ID = "dramamemory_postgres"
RETENTION_DAYS = 90
BATCH_SIZE = 500

DELETE_BATCH = """
WITH victims AS (
    SELECT id FROM app_user
     WHERE anonymous AND status = 'ACTIVE'
       AND last_active_at < now() - make_interval(days => %s)
     ORDER BY last_active_at
     LIMIT %s
)
DELETE FROM app_user WHERE id IN (SELECT id FROM victims)
"""


@dag(
    dag_id="anonymous_user_cleanup",
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["users", "retention"],
    doc_md=__doc__,
)
def anonymous_user_cleanup():
    @task
    def delete_expired() -> dict[str, int]:
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        deleted = 0
        with pg.get_conn() as conn, conn.cursor() as cur:
            while True:
                cur.execute(DELETE_BATCH, (RETENTION_DAYS, BATCH_SIZE))
                n = cur.rowcount
                conn.commit()
                deleted += n
                if n < BATCH_SIZE:
                    break
        summary = {"deleted": deleted, "retention_days": RETENTION_DAYS}
        print(f"anonymous user cleanup: {summary}")
        return summary

    delete_expired()


anonymous_user_cleanup()
