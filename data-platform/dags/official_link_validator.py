"""DAG `official_link_validator` — docs/AIRFLOW_DAGS.md §10 (DM-207).

Daily. Re-checks every stored official link (VOD, broadcaster page, OTT detail)
that has not been verified in the last `max_age_days`:

    load_links          links due for a check, grouped by provider
    validate_provider   (mapped per provider) HEAD, GET on 405/403, follow redirects,
                        then links.validator.classify decides the availability status
    summarize           counts per status; emits asset://gold/official_links

Rules live in dramamemory_data.links.validator (pure, tested): a 403 alone is
never a dead link, a redirect off the provider's site is not "available". Only
URLs already in streaming_link are fetched — nothing user- or LLM-supplied.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import timedelta

import httpx
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, Param, dag, task

from dramamemory_data.links.validator import classify

POSTGRES_CONN_ID = "dramamemory_postgres"
LINKS_ASSET = Asset(name="gold.official_links", uri="asset://gold/official_links")
USER_AGENT = "DramaMemoryBot/0.1 (+https://github.com/JinVibe/drama-archive; link check)"

SELECT_DUE = """
SELECT l.id, l.provider_code, l.url
  FROM streaming_link l
  JOIN drama d ON d.id = l.drama_id AND d.status = 'PUBLISHED'
 WHERE l.last_verified_at IS NULL OR l.last_verified_at < now() - (%s || ' days')::interval
 ORDER BY l.provider_code, l.id
"""

UPDATE_LINK = """
UPDATE streaming_link
   SET availability_status = %s, http_status = %s, last_verified_at = now()
 WHERE id = %s
"""


@dag(
    dag_id="official_link_validator",
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["gold", "links"],
    params={
        "max_age_days": Param(7, type="integer", minimum=0, maximum=365),
        "min_interval_seconds": Param(1.0, type="number", minimum=0, maximum=30),
    },
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    doc_md=__doc__,
)
def official_link_validator():
    @task
    def load_links(params: dict) -> list[list[dict]]:
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        rows = pg.get_records(SELECT_DUE, parameters=(str(int(params["max_age_days"])),))
        by_provider: dict[str, list[dict]] = defaultdict(list)
        for link_id, provider, url in rows:
            by_provider[provider].append({"id": int(link_id), "provider": provider, "url": url})
        print(f"links due: {len(rows)} across {len(by_provider)} providers")
        return list(by_provider.values())

    @task(pool="link_validator_pool", max_active_tis_per_dag=2)
    def validate_provider(links: list[dict], params: dict) -> dict[str, int]:
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        counts: dict[str, int] = defaultdict(int)
        interval = float(params["min_interval_seconds"])
        with httpx.Client(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20
        ) as client, pg.get_conn() as conn, conn.cursor() as cur:
            for link in links:
                verdict = _check(client, link["provider"], link["url"])
                cur.execute(UPDATE_LINK, (verdict.status, verdict.http_status, link["id"]))
                counts[verdict.status] += 1
                time.sleep(interval)
            conn.commit()
        print(f"{links[0]['provider'] if links else '-'}: {dict(counts)}")
        return dict(counts)

    @task(outlets=[LINKS_ASSET])
    def summarize(results: list[dict[str, int]]) -> dict[str, int]:
        total: dict[str, int] = defaultdict(int)
        for r in results:
            for status, n in r.items():
                total[status] += n
        print(f"official links: {dict(total)}")
        return dict(total)

    summarize(validate_provider.expand(links=load_links()))


def _check(client: httpx.Client, provider: str, url: str):
    """HEAD first; many CDNs refuse HEAD, so fall back to GET on 405/403 before judging."""
    try:
        resp = client.head(url)
        if resp.status_code in (403, 405, 501):
            resp = client.get(url)
        return classify(
            provider, url, http_status=resp.status_code, final_url=str(resp.url)
        )
    except httpx.HTTPError as exc:
        return classify(provider, url, http_status=None, final_url=None, error=type(exc).__name__)


official_link_validator()
