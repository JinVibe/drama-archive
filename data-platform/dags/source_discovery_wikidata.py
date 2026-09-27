"""DAG `source_discovery_wikidata` — docs/AIRFLOW_DAGS.md §4 for the `wikidata` source.

Weekly (and on demand). One SPARQL query lists every Korean television series
(not animation) that started in or after `year_from`; each item becomes a
manifest entry whose URL is the per-item detail query the ingest DAG will fetch.
The manifest is written to object storage (manifests/wikidata/latest.json plus a
dated copy) and asset raw.discovery.wikidata triggers ingest_source_records__wikidata.

Quality rule (§4): if the new count is under 60% of the previous manifest, the
run fails instead of publishing a manifest that would look like mass deletion.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import httpx
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.sdk import Asset, Param, dag, task

from dramamemory_data.parsers.wikidata_sparql import SPARQL_ENDPOINT, detail_url
from dramamemory_data.sources import get_source

S3_CONN_ID = "dramamemory_s3"
SOURCE = "wikidata"
DISCOVERY_ASSET = Asset(name=f"raw.discovery.{SOURCE}", uri=f"asset://raw/discovery/{SOURCE}")
LATEST_KEY = f"manifests/{SOURCE}/latest.json"

# Direct instances only (no subclass walk) so animation classes stay out.
LIST_QUERY = """
SELECT DISTINCT ?item WHERE {
  VALUES ?cls { wd:Q5398426 wd:Q526877 wd:Q1259759 wd:Q482612 wd:Q24855895 }
  ?item wdt:P31 ?cls ; wdt:P495 wd:Q884 ; wdt:P580 ?start .
  FILTER(YEAR(?start) >= %d)
}
"""


@dag(
    dag_id="source_discovery_wikidata",
    schedule="@weekly",
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "discovery", SOURCE],
    params={"year_from": Param(2006, type="integer", minimum=1950, maximum=2100)},
    doc_md=__doc__,
)
def source_discovery_wikidata():
    @task(pool=get_source(SOURCE).pool, outlets=[DISCOVERY_ASSET])
    def discover(params: dict) -> dict[str, int | str]:
        source = get_source(SOURCE)
        resp = httpx.get(
            SPARQL_ENDPOINT,
            params={"format": "json", "query": LIST_QUERY % int(params["year_from"])},
            headers={"User-Agent": source.user_agent, "Accept": "application/sparql-results+json"},
            timeout=300,
        )
        resp.raise_for_status()
        qids = sorted(
            {r["item"]["value"].rsplit("/", 1)[1] for r in resp.json()["results"]["bindings"]},
            key=lambda q: int(q[1:]),
        )
        items = [{"external_id": q, "entity_type": "DRAMA", "url": detail_url(q)} for q in qids]

        s3 = S3Hook(aws_conn_id=S3_CONN_ID)
        bucket = os.environ["DRAMAMEMORY_RAW_BUCKET"]
        previous = 0
        if s3.check_for_key(LATEST_KEY, bucket_name=bucket):
            previous = len(json.loads(s3.read_key(LATEST_KEY, bucket_name=bucket)).get("items", []))
        if previous and len(items) < previous * 0.6:
            raise RuntimeError(
                f"discovery dropped from {previous} to {len(items)} items; not publishing manifest"
            )

        manifest = json.dumps({"source_code": SOURCE, "items": items}, ensure_ascii=False)
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
        dated_key = f"manifests/{SOURCE}/{stamp}.json"
        s3.load_string(manifest, key=dated_key, bucket_name=bucket, replace=True)
        s3.load_string(manifest, key=LATEST_KEY, bucket_name=bucket, replace=True)
        summary = {"items": len(items), "previous": previous, "manifest": LATEST_KEY}
        print(f"wikidata discovery: {summary}")
        return summary

    discover()


source_discovery_wikidata()
