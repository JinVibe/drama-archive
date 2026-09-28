"""Static registry of ingestion sources.

The `source` table (db/migrations) holds trust level and terms; this registry holds
what the pipeline needs at parse time: which URLs a collector may fetch and which
Airflow pool throttles it. Both are keyed by `source.code`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceConfig:
    code: str
    # Only URLs starting with one of these prefixes are fetched (SSRF / policy guard).
    allowed_url_prefixes: tuple[str, ...]
    # Airflow pool name; slots are defined in data-platform/config/pools.json.
    pool: str
    request_timeout_seconds: float = 20.0
    # Politeness delay between requests inside one task (0 = none).
    min_interval_seconds: float = 0.0
    # True when a source_discovery_* DAG writes manifests/{code}/latest.json and emits
    # raw.discovery.{code}; the ingest DAG is then scheduled on that asset.
    discovered: bool = False
    user_agent: str = "DramaMemoryBot/0.1 (+https://github.com/JinVibe/drama-archive)"
    extra: dict[str, str] = field(default_factory=dict)


SOURCES: dict[str, SourceConfig] = {
    # Hand-curated manifests. Any https URL is allowed because a human chose it.
    "manual": SourceConfig(
        code="manual",
        allowed_url_prefixes=("https://",),
        pool="source_manual_pool",
    ),
    # Local-only: nginx serving data-platform/seed/ inside compose (service "seed").
    "local_seed": SourceConfig(
        code="local_seed",
        allowed_url_prefixes=("http://seed:8000/",),
        pool="source_manual_pool",
    ),
    # Wikidata Query Service (CC0). ~1 req/s, descriptive User-Agent (their policy).
    "wikidata": SourceConfig(
        code="wikidata",
        allowed_url_prefixes=("https://query.wikidata.org/",),
        pool="source_wikidata_pool",
        request_timeout_seconds=120.0,
        min_interval_seconds=1.0,
        discovered=True,
    ),
    # Korean Wikipedia REST summaries (CC BY-SA 4.0). Used by synopsis_enrich_kowiki only.
    "kowiki": SourceConfig(
        code="kowiki",
        allowed_url_prefixes=("https://ko.wikipedia.org/",),
        pool="source_kowiki_pool",
        request_timeout_seconds=30.0,
        min_interval_seconds=0.25,
    ),
    # First vertical slice target (docs/IMPLEMENTATION_GUIDE.md §1).
    # Collectors stay disabled until site terms are confirmed; manifests are manual for now.
    "tvn_official": SourceConfig(
        code="tvn_official",
        allowed_url_prefixes=("https://tvn.cjenm.com/",),
        pool="source_tvn_pool",
    ),
}


def get_source(code: str) -> SourceConfig:
    try:
        return SOURCES[code]
    except KeyError as exc:
        raise KeyError(f"unknown source code {code!r}; known: {sorted(SOURCES)}") from exc


def is_allowed_url(url: str, source: SourceConfig) -> bool:
    return any(url.startswith(prefix) for prefix in source.allowed_url_prefixes)
