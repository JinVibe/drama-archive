"""DAG `synopsis_enrich_kowiki` — fills drama.synopsis from Korean Wikipedia.

Wikidata has no plot text. For published dramas without a synopsis, this DAG:

    1. asks Wikidata (one SPARQL query) for the kowiki sitelink of each drama's Q-id
    2. fetches the page's lead-section extract from the Wikipedia REST summary API
    3. stores the raw response as a source_record snapshot (provenance) and writes
       drama.synopsis + synopsis_source/url/license in one transaction per drama

This is an enrichment writer, not the publish DAG: it touches exactly the four
synopsis columns, records provenance for every write, and bumps updated_at so
search_document_build re-renders the document (and embedding_refresh re-embeds).

License: CC BY-SA 4.0 — the web shows "출처: 한국어 위키백과" with a link whenever
synopsis_source = 'kowiki'.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from urllib.parse import quote

import httpx
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, dag, task
from airflow.timetables.assets import AssetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

from dramamemory_data.ingestion.snapshot import content_hash, object_key
from dramamemory_data.sources import get_source

POSTGRES_CONN_ID = "dramamemory_postgres"
S3_CONN_ID = "dramamemory_s3"
GOLD_ASSET = Asset(name="gold.catalog", uri="asset://gold/catalog")
SOURCE = "kowiki"
LICENSE = "CC BY-SA 4.0"
BATCH = 200
MIN_EXTRACT_CHARS = 40

# Dramas that came from Wikidata (so we know the Q-id) and still lack a synopsis.
SELECT_TARGETS = """
SELECT d.id, m.external_ref
  FROM drama d
  JOIN source_entity_map m ON m.canonical_type = 'DRAMA' AND m.canonical_id = d.id
  JOIN source_record sr ON sr.id = m.source_record_id
  JOIN source s ON s.id = sr.source_id AND s.code = 'wikidata'
 WHERE d.status = 'PUBLISHED' AND d.synopsis IS NULL AND d.synopsis_source IS NULL
   AND m.external_ref IS NOT NULL
 GROUP BY d.id, m.external_ref
 ORDER BY d.id
 LIMIT %s
"""

SITELINKS_QUERY = """
SELECT ?item ?title WHERE {
  VALUES ?item { %s }
  ?article schema:about ?item ; schema:isPartOf <https://ko.wikipedia.org/> ; schema:name ?title .
}
"""

UPDATE_SYNOPSIS = """
UPDATE drama
   SET synopsis = %s, synopsis_source = %s, synopsis_source_url = %s, synopsis_license = %s,
       updated_at = now()
 WHERE id = %s AND synopsis IS NULL
"""


@dag(
    dag_id="synopsis_enrich_kowiki",
    schedule=AssetOrTimeSchedule(
        timetable=CronTriggerTimetable("0 3 * * *", timezone="UTC"), assets=[GOLD_ASSET]
    ),
    catchup=False,
    max_active_runs=1,
    tags=["enrichment", SOURCE],
    doc_md=__doc__,
)
def synopsis_enrich_kowiki():
    @task(pool=get_source(SOURCE).pool)
    def enrich() -> dict[str, int]:
        source = get_source(SOURCE)
        wikidata = get_source("wikidata")
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        s3 = S3Hook(aws_conn_id=S3_CONN_ID)
        bucket = os.environ["DRAMAMEMORY_RAW_BUCKET"]
        source_id = int(pg.get_first("SELECT id FROM source WHERE code = %s", parameters=(SOURCE,))[0])

        filled = no_article = too_short = errors = 0
        headers = {"User-Agent": source.user_agent}
        with httpx.Client(timeout=source.request_timeout_seconds, headers=headers, follow_redirects=True) as client:
            while True:
                targets = pg.get_records(SELECT_TARGETS, parameters=(BATCH,))
                if not targets:
                    break
                qids = {int(did): ref for did, ref in targets}
                values = " ".join(f"wd:{q}" for q in qids.values())
                resp = client.get(
                    "https://query.wikidata.org/sparql",
                    params={"format": "json", "query": SITELINKS_QUERY % values},
                    headers={"User-Agent": wikidata.user_agent, "Accept": "application/sparql-results+json"},
                    timeout=120,
                )
                resp.raise_for_status()
                title_by_qid = {
                    r["item"]["value"].rsplit("/", 1)[1]: r["title"]["value"]
                    for r in resp.json()["results"]["bindings"]
                }
                progressed = False
                with pg.get_conn() as conn:
                    for drama_id, qid in qids.items():
                        title = title_by_qid.get(qid)
                        if not title:
                            no_article += 1
                            _mark_checked(conn, drama_id)
                            progressed = True
                            continue
                        # Wikipedia REST wants the article title with underscores, percent-encoded once.
                        url = "https://ko.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"), safe="")
                        try:
                            page = client.get(url)
                        except httpx.HTTPError:
                            errors += 1
                            continue
                        if page.status_code != 200:
                            no_article += 1
                            _mark_checked(conn, drama_id)
                            progressed = True
                            continue
                        body = page.content
                        extract = (page.json().get("extract") or "").strip()
                        page_url = page.json().get("content_urls", {}).get("desktop", {}).get("page") or f"https://ko.wikipedia.org/wiki/{title}"
                        digest = content_hash(body)
                        key = object_key(SOURCE, "DRAMA", datetime.now(UTC), digest, "json")
                        if not s3.check_for_key(key, bucket_name=bucket):
                            s3.load_bytes(body, key=key, bucket_name=bucket)
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO source_record (source_id, external_id, entity_type, source_url, object_key,
                                                           content_hash, fetched_at, parser_version, raw_metadata)
                                VALUES (%s, %s, 'DRAMA', %s, %s, %s, now(), 'kowiki_summary/1',
                                        jsonb_build_object('license', %s, 'chars', %s))
                                ON CONFLICT (source_id, entity_type, external_id, content_hash) DO UPDATE SET fetched_at = now()
                                RETURNING id
                                """,
                                (source_id, qid, page_url, key, digest, LICENSE, len(extract)),
                            )
                            record_id = cur.fetchone()[0]
                            cur.execute(
                                """
                                INSERT INTO source_entity_map (source_record_id, canonical_type, canonical_id, match_method,
                                                               decision, confidence, external_ref)
                                VALUES (%s, 'DRAMA', %s, 'EXTERNAL_ID', 'AUTO_MERGE', 1.0, %s)
                                """,
                                (record_id, drama_id, qid),
                            )
                            if len(extract) >= MIN_EXTRACT_CHARS:
                                cur.execute(UPDATE_SYNOPSIS, (extract, SOURCE, page_url, LICENSE, drama_id))
                                filled += 1
                            else:
                                too_short += 1
                                _mark_checked(conn, drama_id, cur=cur)
                        conn.commit()
                        progressed = True
                        time.sleep(source.min_interval_seconds)
                if not progressed:
                    break  # every target errored: stop instead of spinning
        summary = {"filled": filled, "no_article": no_article, "too_short": too_short, "errors": errors}
        print(f"kowiki synopsis: {summary}")
        return summary

    enrich()


def _mark_checked(conn, drama_id: int, cur=None) -> None:
    """Dramas without a usable article get an empty-string synopsis_source marker so the
    target query does not pick them up every night (synopsis stays NULL for the UI)."""
    sql = "UPDATE drama SET synopsis_source = 'kowiki:none' WHERE id = %s AND synopsis IS NULL"
    if cur is not None:
        cur.execute(sql, (drama_id,))
    else:
        with conn.cursor() as c:
            c.execute(sql, (drama_id,))
        conn.commit()


synopsis_enrich_kowiki()
