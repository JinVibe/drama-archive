"""Persist a fetched snapshot: object storage first, then the source_record row.

Both writes are idempotent on content hash, so re-running a DAG over unchanged
pages produces no new objects or rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from dramamemory_data.ingestion.snapshot import FetchResult, extension_for, object_key

PARSER_VERSION = "raw-snapshot/1"


class ObjectStore(Protocol):
    """Minimal subset of S3Hook / boto3 we rely on."""

    def check_for_key(self, key: str, bucket_name: str) -> bool: ...
    def load_bytes(self, bytes_data: bytes, key: str, bucket_name: str) -> None: ...


class Cursor(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...]) -> Any: ...
    def fetchone(self) -> tuple[Any, ...] | None: ...


@dataclass(frozen=True)
class StoredSnapshot:
    object_key: str
    content_hash: str
    source_record_id: int | None   # None when an identical snapshot already existed
    object_written: bool


def write_snapshot_object(store: ObjectStore, bucket: str, key: str, body: bytes) -> bool:
    """Upload unless the key (content-addressed) already exists. Returns True if written."""
    if store.check_for_key(key, bucket_name=bucket):
        return False
    store.load_bytes(body, key=key, bucket_name=bucket)
    return True


_INSERT_SOURCE_RECORD = """
INSERT INTO source_record (
    source_id, external_id, entity_type, source_url, object_key,
    content_hash, fetched_at, parser_version, raw_metadata
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
ON CONFLICT (source_id, entity_type, external_id, content_hash) DO NOTHING
RETURNING id
"""


def insert_source_record(
    cur: Cursor,
    *,
    source_id: int,
    external_id: str,
    entity_type: str,
    result: FetchResult,
    key: str,
) -> int | None:
    """Insert the provenance row; returns new id, or None if this exact content was seen before."""
    raw_metadata = {
        "final_url": result.final_url,
        "status_code": result.status_code,
        "content_type": result.content_type,
        "content_length": len(result.body),
    }
    cur.execute(
        _INSERT_SOURCE_RECORD,
        (
            source_id,
            external_id,
            entity_type,
            result.requested_url,
            key,
            result.content_hash,
            result.fetched_at,
            PARSER_VERSION,
            json.dumps(raw_metadata),
        ),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def store_snapshot(
    *,
    store: ObjectStore,
    bucket: str,
    cur: Cursor,
    source_code: str,
    source_id: int,
    external_id: str,
    entity_type: str,
    result: FetchResult,
) -> StoredSnapshot:
    digest = result.content_hash
    ext = extension_for(result.content_type)
    key = object_key(source_code, entity_type, result.fetched_at, digest, ext)
    written = write_snapshot_object(store, bucket, key, result.body)
    record_id = insert_source_record(
        cur,
        source_id=source_id,
        external_id=external_id,
        entity_type=entity_type,
        result=result,
        key=key,
    )
    return StoredSnapshot(
        object_key=key,
        content_hash=digest,
        source_record_id=record_id,
        object_written=written,
    )
