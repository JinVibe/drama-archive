"""DAG `ost_enrich_kowiki` — fills OST tracks from Korean Wikipedia articles.

Wikidata has almost no soundtrack data, kowiki drama articles do (CC BY-SA 4.0;
track facts, not prose). For published dramas whose article is already known
(synopsis step stored its URL) and that have not been checked:

    1. fetch the article wikitext (MediaWiki action=parse), snapshot it as a
       source_record (parser kowiki_ost/1) for provenance
    2. parse the OST section (parsers/kowiki_ost.py): albums, parts, tracks, artists
    3. write song / artist / song_artist / drama_ost through the same helpers the
       publish DAG uses, resolving each song and artist with entity_resolution
       (same-drama title match, artist by name) and mapping every song row to its
       synthetic external id so re-runs update instead of duplicating
    4. mark drama.ost_source ('kowiki' or 'kowiki:none') and bump canonical_version

Emits asset://enrich/synopsis (the enrichment asset) so search documents (OST in
body), embeddings and the graph (HAS_OST / PERFORMED) refresh.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import httpx
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, dag, task
from airflow.timetables.assets import AssetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

from dramamemory_data.entity_resolution import matching
from dramamemory_data.entity_resolution.repo import PostgresRepo
from dramamemory_data.ingestion.snapshot import content_hash, object_key
from dramamemory_data.parsers import kowiki_ost
from dramamemory_data.publish.gold import (
    ensure_artist,
    ensure_song,
    link_song_artist,
    upsert_drama_ost,
)
from dramamemory_data.sources import get_source

POSTGRES_CONN_ID = "dramamemory_postgres"
S3_CONN_ID = "dramamemory_s3"
GOLD_ASSET = Asset(name="gold.catalog", uri="asset://gold/catalog")
ENRICHED_ASSET = Asset(name="enrich.synopsis", uri="asset://enrich/synopsis")
SOURCE = "kowiki"
LICENSE = "CC BY-SA 4.0"
BATCH = 300
API = "https://ko.wikipedia.org/w/api.php"

SELECT_TARGETS = """
SELECT d.id, d.synopsis_source_url, m.external_ref
  FROM drama d
  JOIN source_entity_map m ON m.canonical_type = 'DRAMA' AND m.canonical_id = d.id
  JOIN source_record sr ON sr.id = m.source_record_id
  JOIN source s ON s.id = sr.source_id AND s.code = 'wikidata'
 WHERE d.status = 'PUBLISHED' AND d.ost_source IS NULL
   AND d.synopsis_source_url LIKE 'https://ko.wikipedia.org/wiki/%%'
 GROUP BY d.id, d.synopsis_source_url, m.external_ref
 ORDER BY d.id
 LIMIT %s
"""

MARK = """
UPDATE drama
   SET ost_source = %s, canonical_version = canonical_version + 1, updated_at = now()
 WHERE id = %s
"""


@dag(
    dag_id="ost_enrich_kowiki",
    schedule=AssetOrTimeSchedule(
        timetable=CronTriggerTimetable("0 4 * * *", timezone="UTC"), assets=[GOLD_ASSET]
    ),
    catchup=False,
    max_active_runs=1,
    tags=["enrichment", SOURCE, "ost"],
    doc_md=__doc__,
)
def ost_enrich_kowiki():
    @task(pool=get_source(SOURCE).pool, outlets=[ENRICHED_ASSET])
    def enrich() -> dict[str, int]:
        from urllib.parse import unquote

        source = get_source(SOURCE)
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        s3 = S3Hook(aws_conn_id=S3_CONN_ID)
        bucket = os.environ["DRAMAMEMORY_RAW_BUCKET"]
        source_id = int(
            pg.get_first("SELECT id FROM source WHERE code = %s", parameters=(SOURCE,))[0]
        )

        with_ost = without = songs_written = errors = 0
        headers = {"User-Agent": source.user_agent}
        with httpx.Client(timeout=source.request_timeout_seconds, headers=headers) as client:
            while True:
                targets = pg.get_records(SELECT_TARGETS, parameters=(BATCH,))
                if not targets:
                    break
                progressed = False
                conn = pg.get_conn()
                try:
                    for drama_id, url, qid in targets:
                        title = unquote(url.rsplit("/wiki/", 1)[1]).replace("_", " ")
                        try:
                            resp = client.get(
                                API,
                                params={
                                    "action": "parse",
                                    "page": title,
                                    "prop": "wikitext",
                                    "format": "json",
                                    "redirects": 1,
                                },
                            )
                            resp.raise_for_status()
                            wikitext = resp.json()["parse"]["wikitext"]["*"]
                        except (httpx.HTTPError, KeyError, ValueError):
                            errors += 1
                            continue
                        songs = kowiki_ost.parse(wikitext, qid=qid)
                        body = wikitext.encode("utf-8")
                        digest = content_hash(body)
                        key = object_key(SOURCE, "DRAMA", datetime.now(UTC), digest, "txt")
                        if not s3.check_for_key(key, bucket_name=bucket):
                            s3.load_bytes(body, key=key, bucket_name=bucket)
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO source_record (
                                    source_id, external_id, entity_type, source_url, object_key,
                                    content_hash, fetched_at, parser_version, raw_metadata)
                                VALUES (%s, %s, 'DRAMA', %s, %s, %s, now(), %s,
                                        jsonb_build_object('license', %s, 'songs', %s))
                                ON CONFLICT (source_id, entity_type, external_id, content_hash)
                                DO UPDATE SET fetched_at = now()
                                RETURNING id
                                """,
                                (
                                    source_id,
                                    qid,
                                    url,
                                    key,
                                    digest,
                                    kowiki_ost.PARSER_VERSION,
                                    LICENSE,
                                    len(songs),
                                ),
                            )
                            record_id = int(cur.fetchone()[0])
                            repo = PostgresRepo(cur)
                            for song in songs:
                                smatch = matching.resolve_song(song, source_id, repo, int(drama_id))
                                if smatch.decision == "REVIEW":
                                    continue  # ambiguous: leave it for a curated source
                                sdict = smatch.as_dict()
                                song_id = ensure_song(
                                    cur, song, sdict, source_id=source_id, drama_id=int(drama_id)
                                )
                                cur.execute(
                                    """
                                    INSERT INTO source_entity_map (
                                        source_record_id, canonical_type, canonical_id,
                                        match_method, decision, confidence, external_ref)
                                    VALUES (%s, 'SONG', %s, %s, %s, %s, %s)
                                    """,
                                    (
                                        record_id,
                                        song_id,
                                        sdict["method"],
                                        sdict["decision"],
                                        sdict["confidence"],
                                        song.external_id,
                                    ),
                                )
                                for sa in song.artists:
                                    amatch = matching.resolve_artist(sa.artist, source_id, repo)
                                    artist_id = ensure_artist(
                                        cur, sa.artist, amatch.as_dict(), source_id=source_id
                                    )
                                    link_song_artist(
                                        cur, song_id, artist_id, sa.role, sa.sort_order
                                    )
                                upsert_drama_ost(cur, int(drama_id), song_id, song)
                                songs_written += 1
                            cur.execute(MARK, ("kowiki" if songs else "kowiki:none", drama_id))
                        conn.commit()
                        if songs:
                            with_ost += 1
                        else:
                            without += 1
                        progressed = True
                        time.sleep(source.min_interval_seconds)
                finally:
                    conn.close()
                if not progressed:
                    break
        summary = {
            "with_ost": with_ost,
            "without": without,
            "songs": songs_written,
            "errors": errors,
        }
        print(f"kowiki ost: {summary}")
        return summary

    enrich()


ost_enrich_kowiki()
