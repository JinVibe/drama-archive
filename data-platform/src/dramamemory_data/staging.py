"""Read/write helpers for the silver `staging_record` table.

Cursor-based so DAGs pass a psycopg cursor and tests pass a fake.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from dramamemory_data.normalization.models import NormalizedDrama

SELECT_UNPARSED = """
SELECT sr.id, s.code, sr.entity_type, sr.object_key, sr.source_url
FROM source_record sr
JOIN source s ON s.id = sr.source_id
LEFT JOIN staging_record st ON st.source_record_id = sr.id
WHERE sr.entity_type = 'DRAMA'
  AND (st.id IS NULL OR st.status = 'PARSE_FAILED')
ORDER BY sr.id
"""

UPSERT_STAGING = """
INSERT INTO staging_record (source_record_id, entity_type, parser_version, payload, status, issues)
VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb)
ON CONFLICT (source_record_id) DO UPDATE SET
    parser_version = EXCLUDED.parser_version,
    payload        = EXCLUDED.payload,
    status         = EXCLUDED.status,
    issues         = EXCLUDED.issues,
    resolution     = NULL
RETURNING id
"""

SELECT_BY_STATUS = """
SELECT st.id, st.source_record_id, sr.source_id, s.code, st.payload, st.resolution
FROM staging_record st
JOIN source_record sr ON sr.id = st.source_record_id
JOIN source s ON s.id = sr.source_id
WHERE st.status = %s
ORDER BY st.id
"""

UPDATE_STATUS = """
UPDATE staging_record
SET status = %s, resolution = COALESCE(%s::jsonb, resolution), issues = COALESCE(%s::jsonb, issues)
WHERE id = %s
"""


@dataclass(frozen=True)
class StagingRow:
    id: int
    source_record_id: int
    source_id: int
    source_code: str
    payload: NormalizedDrama
    resolution: dict[str, Any] | None


def upsert_parsed(
    cur, *, source_record_id: int, parser_version: str, drama: NormalizedDrama
) -> int:
    cur.execute(
        UPSERT_STAGING,
        (source_record_id, "DRAMA", parser_version, drama.model_dump_json(), "NEW", None),
    )
    return int(cur.fetchone()[0])


def upsert_parse_failed(cur, *, source_record_id: int, parser_version: str, error: str) -> int:
    issues = json.dumps([{"code": "PARSE_FAILED", "severity": "ERROR", "message": error}])
    cur.execute(
        UPSERT_STAGING,
        (source_record_id, "DRAMA", parser_version, None, "PARSE_FAILED", issues),
    )
    return int(cur.fetchone()[0])


def fetch_by_status(cur, status: str) -> list[StagingRow]:
    cur.execute(SELECT_BY_STATUS, (status,))
    rows = []
    for id_, source_record_id, source_id, code, payload, resolution in cur.fetchall():
        rows.append(
            StagingRow(
                id=int(id_),
                source_record_id=int(source_record_id),
                source_id=int(source_id),
                source_code=code,
                payload=NormalizedDrama.model_validate(payload),
                resolution=resolution,
            )
        )
    return rows


def set_status(
    cur,
    staging_id: int,
    status: str,
    *,
    resolution: dict[str, Any] | None = None,
    issues: list[dict[str, Any]] | None = None,
) -> None:
    cur.execute(
        UPDATE_STATUS,
        (
            status,
            json.dumps(resolution) if resolution is not None else None,
            json.dumps(issues) if issues is not None else None,
            staging_id,
        ),
    )
