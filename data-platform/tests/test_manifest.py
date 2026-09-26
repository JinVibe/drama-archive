import json

import pytest
from pydantic import ValidationError

from dramamemory_data.ingestion.manifest import ManifestItem, dedupe_items, load_manifest


def _item(external_id: str, entity_type: str = "DRAMA") -> ManifestItem:
    return ManifestItem(external_id=external_id, entity_type=entity_type, url="https://example.com/x")


def test_load_manifest_roundtrip(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(
        json.dumps(
            {
                "source_code": "manual",
                "items": [{"external_id": "goblin", "entity_type": "DRAMA", "url": "https://example.com/goblin"}],
            }
        ),
        encoding="utf-8",
    )
    manifest = load_manifest(path)
    assert manifest.source_code == "manual"
    assert manifest.items[0].as_task_arg() == {
        "external_id": "goblin",
        "entity_type": "DRAMA",
        "url": "https://example.com/goblin",
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"external_id": "", "entity_type": "DRAMA", "url": "https://x.com"},
        {"external_id": "a", "entity_type": "MOVIE", "url": "https://x.com"},
        {"external_id": "a", "entity_type": "DRAMA", "url": "not a url"},
    ],
)
def test_manifest_item_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        ManifestItem(**bad)


def test_dedupe_items_keeps_first_per_entity_and_id():
    items = [_item("a"), _item("b"), _item("a"), _item("a", "PERSON")]
    deduped = dedupe_items(items)
    assert [(i.entity_type, i.external_id) for i in deduped] == [
        ("DRAMA", "a"),
        ("DRAMA", "b"),
        ("PERSON", "a"),
    ]
