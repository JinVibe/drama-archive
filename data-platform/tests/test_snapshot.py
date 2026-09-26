from datetime import UTC, datetime

import httpx
import pytest

from dramamemory_data.ingestion.snapshot import (
    DisallowedUrlError,
    FetchFailedError,
    content_hash,
    extension_for,
    fetch,
    object_key,
)
from dramamemory_data.sources import SourceConfig, get_source, is_allowed_url

TVN = SourceConfig(code="tvn_official", allowed_url_prefixes=("https://tvn.cjenm.com/",), pool="p")


def test_content_hash_is_sha256_hex():
    assert content_hash(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert content_hash(b"a") != content_hash(b"b")


@pytest.mark.parametrize(
    ("content_type", "ext"),
    [
        ("text/html; charset=utf-8", "html"),
        ("application/json", "json"),
        ("TEXT/XML", "xml"),
        ("image/png", "bin"),
    ],
)
def test_extension_for(content_type, ext):
    assert extension_for(content_type) == ext


def test_object_key_is_partitioned_and_content_addressed():
    ts = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
    key = object_key("tvn_official", "DRAMA", ts, "abc123", "html")
    assert key == "source=tvn_official/entity=drama/dt=2026-09-26/abc123.html"


def test_is_allowed_url_prefix_match():
    assert is_allowed_url("https://tvn.cjenm.com/ko/goblin", TVN)
    assert not is_allowed_url("https://evil.example/tvn.cjenm.com/", TVN)
    assert not is_allowed_url("http://tvn.cjenm.com/", TVN)


def test_manual_source_allows_any_https_only():
    manual = get_source("manual")
    assert is_allowed_url("https://anything.example/page", manual)
    assert not is_allowed_url("http://anything.example/page", manual)
    assert not is_allowed_url("file:///etc/passwd", manual)


def test_get_source_unknown_code():
    with pytest.raises(KeyError, match="unknown source code"):
        get_source("nope")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_returns_snapshot_with_hash_and_final_url():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "https://tvn.cjenm.com/new"})
        return httpx.Response(
            200, content=b"<html>ok</html>", headers={"content-type": "text/html"}
        )

    result = fetch("https://tvn.cjenm.com/old", TVN, client=_client(handler))
    assert result.requested_url == "https://tvn.cjenm.com/old"
    assert result.final_url == "https://tvn.cjenm.com/new"
    assert result.status_code == 200
    assert result.content_hash == content_hash(b"<html>ok</html>")
    assert result.fetched_at.tzinfo is not None


def test_fetch_rejects_disallowed_url_before_any_request():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    with pytest.raises(DisallowedUrlError):
        fetch("https://other.example/", TVN, client=_client(handler))
    assert calls == []


def test_fetch_raises_on_non_2xx():
    def handler(request):
        return httpx.Response(404)

    with pytest.raises(FetchFailedError) as exc:
        fetch("https://tvn.cjenm.com/missing", TVN, client=_client(handler))
    assert exc.value.status_code == 404
