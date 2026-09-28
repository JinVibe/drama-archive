"""DAG `popularity_refresh_kowiki` — a popularity proxy for "그해의 인기작".

The catalog has no viewership data. The Korean Wikipedia article's page views
over the trailing 12 months (Wikimedia pageviews API, public, no key) are a
usable proxy for lasting interest: 도깨비 and 태양의 후예 are read every day,
a forgotten daily drama is not. Weekly:

    targets  published dramas whose kowiki article is known (synopsis URL) or resolvable
             through the Wikidata sitelink
    fetch    GET /metrics/pageviews/per-article/ko.wikipedia/all-access/user/{title}/monthly/{from}/{to}
    write    drama.popularity_score = sum(views), popularity_source = 'kowiki:pageviews:365d',
             popularity_updated_at = now()   (no canonical_version bump: presentation data only)

The UI labels the number as page views, never as ratings.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, unquote

import httpx
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task

from dramamemory_data.sources import get_source

POSTGRES_CONN_ID = "dramamemory_postgres"
SOURCE = "kowiki"
PAGEVIEWS = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/ko.wikipedia/all-access/user"
SITELINKS_QUERY = """
SELECT ?item ?title WHERE {
  VALUES ?item { %s }
  ?article schema:about ?item ; schema:isPartOf <https://ko.wikipedia.org/> ; schema:name ?title .
}
"""

SELECT_TARGETS = """
SELECT d.id, d.synopsis_source_url, m.external_ref
  FROM drama d
  JOIN source_entity_map m ON m.canonical_type = 'DRAMA' AND m.canonical_id = d.id
  JOIN source_record sr ON sr.id = m.source_record_id
  JOIN source s ON s.id = sr.source_id AND s.code = 'wikidata'
 WHERE d.status = 'PUBLISHED' AND m.external_ref LIKE 'Q%'
   AND (d.popularity_updated_at IS NULL OR d.popularity_updated_at < now() - interval '6 days')
 GROUP BY d.id, d.synopsis_source_url, m.external_ref
 ORDER BY d.id
"""

UPDATE = """
UPDATE drama
   SET popularity_score = %s, popularity_source = 'kowiki:pageviews:365d',
       popularity_updated_at = now()
 WHERE id = %s
"""


@dag(
    dag_id="popularity_refresh_kowiki",
    schedule="@weekly",
    catchup=False,
    max_active_runs=1,
    tags=["enrichment", SOURCE, "popularity"],
    doc_md=__doc__,
)
def popularity_refresh_kowiki():
    @task(pool=get_source(SOURCE).pool)
    def refresh() -> dict[str, int]:
        source = get_source(SOURCE)
        wikidata = get_source("wikidata")
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        rows = pg.get_records(SELECT_TARGETS)

        # Article titles: stored kowiki URL, else the Wikidata sitelink (batched).
        titles: dict[int, str] = {}
        missing: dict[str, int] = {}
        for drama_id, url, qid in rows:
            if url and "/wiki/" in url:
                titles[int(drama_id)] = unquote(url.rsplit("/wiki/", 1)[1]).replace("_", " ")
            else:
                missing[qid] = int(drama_id)
        end = datetime.now(UTC).replace(day=1) - timedelta(days=1)  # last full month
        start = (end.replace(day=1) - timedelta(days=365)).replace(day=1)
        span = f"{start:%Y%m}01/{end:%Y%m}{end.day:02d}"

        updated = no_article = errors = 0
        with httpx.Client(timeout=source.request_timeout_seconds, follow_redirects=True) as client:
            qids = list(missing)
            for i in range(0, len(qids), 200):
                chunk = qids[i : i + 200]
                resp = client.get(
                    "https://query.wikidata.org/sparql",
                    params={"format": "json",
                            "query": SITELINKS_QUERY % " ".join(f"wd:{q}" for q in chunk)},
                    headers={"User-Agent": wikidata.user_agent,
                             "Accept": "application/sparql-results+json"},
                    timeout=120,
                )
                resp.raise_for_status()
                for r in resp.json()["results"]["bindings"]:
                    titles[missing[r["item"]["value"].rsplit("/", 1)[1]]] = r["title"]["value"]
                time.sleep(wikidata.min_interval_seconds)
            no_article = len(rows) - len(titles)

            with pg.get_conn() as conn, conn.cursor() as cur:
                for n, (drama_id, title) in enumerate(titles.items(), start=1):
                    url = f"{PAGEVIEWS}/{quote(title.replace(' ', '_'), safe='')}/monthly/{span}"
                    try:
                        resp = client.get(url, headers={"User-Agent": source.user_agent})
                    except httpx.HTTPError:
                        errors += 1
                        continue
                    if resp.status_code == 404:  # no views recorded in the window
                        views = 0
                    elif resp.status_code != 200:
                        errors += 1
                        continue
                    else:
                        views = sum(int(item.get("views", 0)) for item in resp.json().get("items", []))
                    cur.execute(UPDATE, (views, drama_id))
                    updated += 1
                    if n % 200 == 0:
                        conn.commit()
                        print(f"{n}/{len(titles)}")
                    time.sleep(0.1)  # Wikimedia asks for a descriptive UA and moderate rates
                conn.commit()
        summary = {"targets": len(rows), "updated": updated, "no_article": no_article,
                   "errors": errors, "window": span}
        print(f"kowiki popularity: {summary}")
        return summary

    refresh()


popularity_refresh_kowiki()
