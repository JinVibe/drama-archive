"""Source-specific parsers: raw snapshot bytes -> NormalizedDrama.

Registry maps `source.code` to a parser. Every parser exposes `PARSER_VERSION` so
staging rows can be re-parsed when a parser changes (docs/AIRFLOW_DAGS.md §6).
"""

from __future__ import annotations

from collections.abc import Callable

from dramamemory_data.normalization.models import NormalizedDrama
from dramamemory_data.parsers import dramamemory_json, wikidata_sparql

Parser = Callable[[bytes], NormalizedDrama]


class ParseError(ValueError):
    """Payload could not be turned into a normalized record. Not retryable."""


_REGISTRY: dict[str, tuple[str, Parser]] = {
    "manual": (dramamemory_json.PARSER_VERSION, dramamemory_json.parse),
    "local_seed": (dramamemory_json.PARSER_VERSION, dramamemory_json.parse),
    "wikidata": (wikidata_sparql.PARSER_VERSION, wikidata_sparql.parse),
    # "tvn_official": added once site terms are confirmed and an HTML parser exists.
}


def parser_for(source_code: str) -> tuple[str, Parser]:
    """Return (parser_version, parse) for a source, or raise KeyError."""
    try:
        return _REGISTRY[source_code]
    except KeyError as exc:
        raise KeyError(f"no parser registered for source {source_code!r}") from exc


def registered_sources() -> list[str]:
    return sorted(_REGISTRY)
