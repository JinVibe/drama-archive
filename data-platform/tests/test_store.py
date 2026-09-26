import json
from datetime import UTC, datetime

from dramamemory_data.ingestion.snapshot import FetchResult
from dramamemory_data.ingestion.store import PARSER_VERSION, store_snapshot, write_snapshot_object


class FakeStore:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def check_for_key(self, key, bucket_name):
        return f"{bucket_name}/{key}" in self.objects

    def load_bytes(self, bytes_data, key, bucket_name):
        self.objects[f"{bucket_name}/{key}"] = bytes_data


class FakeCursor:
    """Records executed SQL and simulates ON CONFLICT DO NOTHING on content hash."""

    def __init__(self):
        self.seen: set[tuple] = set()
        self.executed: list[tuple[str, tuple]] = []
        self._next_id = 1
        self._last: tuple | None = None

    def execute(self, sql, params):
        self.executed.append((sql, params))
        # (source_id, entity_type, external_id, content_hash) — the unique index
        key = (params[0], params[2], params[1], params[5])
        if key in self.seen:
            self._last = None
        else:
            self.seen.add(key)
            self._last = (self._next_id,)
            self._next_id += 1

    def fetchone(self):
        return self._last


def _result(body: bytes = b"<html/>") -> FetchResult:
    return FetchResult(
        requested_url="https://tvn.cjenm.com/goblin",
        final_url="https://tvn.cjenm.com/goblin",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        fetched_at=datetime(2026, 9, 26, tzinfo=UTC),
    )


def test_write_snapshot_object_skips_existing_key():
    store = FakeStore()
    assert write_snapshot_object(store, "raw", "k", b"1") is True
    assert write_snapshot_object(store, "raw", "k", b"2") is False
    assert store.objects["raw/k"] == b"1"


def test_store_snapshot_writes_object_and_record():
    store, cur = FakeStore(), FakeCursor()
    stored = store_snapshot(
        store=store, bucket="raw", cur=cur, source_code="tvn_official", source_id=7,
        external_id="goblin", entity_type="DRAMA", result=_result(),
    )
    assert stored.object_written is True
    assert stored.source_record_id == 1
    assert stored.object_key.startswith("source=tvn_official/entity=drama/dt=2026-09-26/")
    assert stored.object_key.endswith(".html")
    assert f"raw/{stored.object_key}" in store.objects

    _, params = cur.executed[0]
    assert params[0] == 7
    assert params[1] == "goblin"
    assert params[2] == "DRAMA"
    assert params[4] == stored.object_key
    assert params[7] == PARSER_VERSION
    assert json.loads(params[8])["content_type"] == "text/html; charset=utf-8"


def test_store_snapshot_is_idempotent_on_unchanged_content():
    store, cur = FakeStore(), FakeCursor()
    kwargs = dict(
        store=store, bucket="raw", cur=cur, source_code="tvn_official", source_id=7,
        external_id="goblin", entity_type="DRAMA", result=_result(),
    )
    first = store_snapshot(**kwargs)
    second = store_snapshot(**kwargs)
    assert first.source_record_id == 1
    assert second.source_record_id is None
    assert second.object_written is False
    assert len(store.objects) == 1


def test_store_snapshot_changed_content_creates_new_object_and_record():
    store, cur = FakeStore(), FakeCursor()
    common = dict(store=store, bucket="raw", cur=cur, source_code="tvn_official", source_id=7,
                  external_id="goblin", entity_type="DRAMA")
    a = store_snapshot(result=_result(b"v1"), **common)
    b = store_snapshot(result=_result(b"v2"), **common)
    assert a.object_key != b.object_key
    assert (a.source_record_id, b.source_record_id) == (1, 2)
