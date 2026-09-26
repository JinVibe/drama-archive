"""Discovery manifest: the list of (external_id, entity_type, url) a source run should fetch.

Until the discovery DAG exists, manifests are JSON files under data-platform/manifests/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, TypeAdapter

EntityType = Literal["DRAMA", "PERSON", "SONG", "LINK"]


class ManifestItem(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    entity_type: EntityType
    url: HttpUrl

    def as_task_arg(self) -> dict[str, str]:
        """Plain dict for Airflow XCom / dynamic task mapping."""
        return {
            "external_id": self.external_id,
            "entity_type": self.entity_type,
            "url": str(self.url),
        }


class Manifest(BaseModel):
    source_code: str = Field(min_length=1, max_length=60)
    items: list[ManifestItem]


_manifest_adapter = TypeAdapter(Manifest)


def load_manifest(path: str | Path) -> Manifest:
    raw = Path(path).read_text(encoding="utf-8")
    return _manifest_adapter.validate_python(json.loads(raw))


def dedupe_items(items: list[ManifestItem]) -> list[ManifestItem]:
    """Drop repeated (entity_type, external_id) pairs, keeping first occurrence."""
    seen: set[tuple[str, str]] = set()
    unique: list[ManifestItem] = []
    for item in items:
        key = (item.entity_type, item.external_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
