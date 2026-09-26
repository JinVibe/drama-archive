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
    user_agent: str = "DramaMemoryBot/0.1 (+https://github.com/JinVibe/drama-archive)"
    extra: dict[str, str] = field(default_factory=dict)


SOURCES: dict[str, SourceConfig] = {
    # Hand-curated manifests. Any https URL is allowed because a human chose it.
    "manual": SourceConfig(
        code="manual",
        allowed_url_prefixes=("https://",),
        pool="source_manual_pool",
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
