"""Fetch a source page and describe it as an immutable raw snapshot.

Pure functions plus one HTTP call; storage/DB writes live in `store.py` so this
module is testable with a fake transport.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from dramamemory_data.sources import SourceConfig, is_allowed_url


class DisallowedUrlError(ValueError):
    pass


class FetchFailedError(RuntimeError):
    def __init__(self, url: str, status_code: int):
        super().__init__(f"fetch failed: {status_code} {url}")
        self.url = url
        self.status_code = status_code


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes
    fetched_at: datetime

    @property
    def content_hash(self) -> str:
        return content_hash(self.body)


def content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


_EXTENSION_BY_CONTENT_TYPE = {
    "application/json": "json",
    "application/sparql-results+json": "json",
    "text/html": "html",
    "application/xml": "xml",
    "text/xml": "xml",
    "text/plain": "txt",
}


def extension_for(content_type: str) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return _EXTENSION_BY_CONTENT_TYPE.get(media_type, "bin")


def object_key(
    source_code: str, entity_type: str, fetched_at: datetime, digest: str, ext: str
) -> str:
    """Partitioned key, see docs/ARCHITECTURE.md §4.7.

    source=tvn_official/entity=drama/dt=2026-09-26/<sha256>.html
    """
    return (
        f"source={source_code}/entity={entity_type.lower()}/"
        f"dt={fetched_at:%Y-%m-%d}/{digest}.{ext}"
    )


def fetch(url: str, source: SourceConfig, client: httpx.Client | None = None) -> FetchResult:
    """GET `url` under the source's policy. Raises on disallowed URL or non-2xx."""
    if not is_allowed_url(url, source):
        raise DisallowedUrlError(f"{url} is outside allowed prefixes for source {source.code!r}")

    owns_client = client is None
    client = client or httpx.Client(
        timeout=source.request_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": source.user_agent},
    )
    try:
        response = client.get(url)
    finally:
        if owns_client:
            client.close()

    if response.status_code // 100 != 2:
        raise FetchFailedError(url, response.status_code)

    return FetchResult(
        requested_url=url,
        final_url=str(response.url),
        status_code=response.status_code,
        content_type=response.headers.get("content-type", "application/octet-stream"),
        body=response.content,
        fetched_at=datetime.now(tz=UTC),
    )
