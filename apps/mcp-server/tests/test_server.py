"""Tools/resources/prompts against a fake backend, exercised through MCPServer's
own dispatch (call_tool / read_resource / get_prompt), plus one transport smoke
test over the stateless streamable-HTTP app."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from mcp.server.transport_security import TransportSecuritySettings

from mcp_server.backend import BackendError
from mcp_server.config import Settings
from mcp_server.server import build_server

GOBLIN = {
    "id": 1, "slug": "goblin", "titleKo": "도깨비", "titleEn": "Guardian", "aliases": ["Goblin"],
    "broadcaster": {"code": "tvn", "nameKo": "tvN"}, "startDate": "2016-12-02",
    "endDate": "2017-01-21", "episodeCount": 16, "genres": ["fantasy", "romance"],
    "synopsis": "불멸의 도깨비", "synopsisSource": {"code": "kowiki", "url": "https://ko.wikipedia.org/wiki/x",
                                            "license": "CC BY-SA 4.0"},
    "credits": [
        {"personId": 10, "nameKo": "공유", "creditType": "ACTOR", "characterName": "김신",
         "mainCast": True},
        {"personId": 11, "nameKo": "김은숙", "creditType": "WRITER"},
    ],
    "osts": [{"songId": 5, "title": "Stay With Me", "partNo": 1,
              "artists": [{"name": "찬열"}, {"name": "펀치"}]}],
    "links": [{"providerCode": "tving", "url": "https://www.tving.com/x", "linkType": "OTT_DETAIL",
               "regionCode": "KR", "availabilityStatus": "AVAILABLE", "lastVerifiedAt": None}],
    "canonicalVersion": 3,
}
GONG_YOO = {
    "id": 10, "slug": "gong-yoo", "nameKo": "공유", "nameEn": "Gong Yoo", "birthDate": "1979-07-10",
    "filmography": [
        {"dramaId": 1, "titleKo": "도깨비", "broadcasterCode": "tvn", "startDate": "2016-12-02",
         "creditType": "ACTOR", "characterName": "김신", "mainCast": True},
        {"dramaId": 2, "titleKo": "커피프린스 1호점", "broadcasterCode": "mbc",
         "startDate": "2007-07-02", "creditType": "ACTOR", "characterName": "최한결",
         "mainCast": True},
    ],
}


class FakeBackend:
    def __init__(self):
        self.calls: list[tuple] = []

    async def search(self, q, *, size, year_from, year_to, broadcaster):
        self.calls.append(("search", q, size, year_from, year_to, broadcaster))
        return {
            "strategy": "hybrid+graph", "relaxed": False, "retrieval_version": "hybrid-v1",
            "plan": {"text": q, "year_from": year_from, "year_to": year_to,
                     "broadcaster": broadcaster, "signals": {}},
            "hits": [{"drama_id": 1, "title": "도깨비", "score": 0.0489,
                      "metadata": {"year": 2016, "broadcaster_code": "tvn", "slug": "goblin"},
                      "ranks": {"fts": 1, "vector": 2, "graph": 1}, "scores": {}}],
        }

    async def drama(self, drama_id):
        self.calls.append(("drama", drama_id))
        if drama_id == 1:
            return GOBLIN
        raise BackendError("DRAMA_NOT_FOUND", f"no drama {drama_id}")

    async def person(self, person_id):
        if person_id == 10:
            return GONG_YOO
        raise BackendError("PERSON_NOT_FOUND", f"no person {person_id}")

    async def year(self, year, *, size):
        return {"total": 1, "items": [{"id": 1, "titleKo": "도깨비", "slug": "goblin",
                                       "broadcaster": {"code": "tvn"}, "startDate": "2016-12-02",
                                       "genres": ["fantasy"]}]}

    async def broadcasters(self):
        return [{"code": "tvn", "nameKo": "tvN", "nameEn": "tvN", "officialUrl": "https://tvn"}]

    async def related_dramas(self, drama_id, *, limit):
        self.calls.append(("related", drama_id, limit))
        if drama_id == 1:
            return {"drama_id": 1,
                    "via_people": [{"id": 2, "title": "커피프린스 1호점", "shared": 1}],
                    "via_ost_artists": [{"id": 3, "title": "쌈, 마이웨이", "shared": 1}]}
        return {"drama_id": drama_id, "via_people": [{"id": 4, "title": "다른 작품", "shared": 1}],
                "via_ost_artists": []}

    async def collaborators(self, person_id, *, limit):
        if person_id == 10:
            return {"person_id": 10, "collaborators": [{"id": 12, "name": "이동욱", "shared": 1}]}
        raise BackendError("UPSTREAM_UNAVAILABLE", "graph down", retryable=True)


@pytest.fixture
def server():
    backend = FakeBackend()
    settings = Settings(web_base_url="https://dm.test", graph_per_minute=2)
    return build_server(settings, backend), backend


def _payload(result) -> Any:
    """call_tool returns content blocks (+ structured content); pull the JSON out."""
    if isinstance(result, tuple):  # (content, structured) form
        _, structured = result
        if structured:
            return structured.get("result", structured)
    if hasattr(result, "structuredContent") and result.structuredContent:
        sc = result.structuredContent
        return sc.get("result", sc)
    content = result.content if hasattr(result, "content") else result
    return json.loads(content[0].text)


async def test_tools_are_registered_and_public_only(server):
    mcp, _ = server
    names = {t.name for t in await mcp.list_tools()}
    assert names == {"search_dramas", "get_drama", "get_actor", "get_ost",
                     "get_official_watch_links", "traverse_drama_graph"}
    assert not names & {"mark_watched", "add_memory_note", "get_my_timeline"}


async def test_search_passes_filters_and_reports_match_reasons(server):
    mcp, backend = server
    out = _payload(await mcp.call_tool("search_dramas", {"query": "공유 판타지", "year_from": 2015,
                                                          "year_to": 2017, "limit": 5}))
    assert backend.calls[0] == ("search", "공유 판타지", 5, 2015, 2017, None)
    assert out["items"][0]["drama_id"] == 1 and out["items"][0]["year"] == 2016
    assert out["items"][0]["match_reasons"] == ["fts#1", "graph#1", "vector#2"]
    assert out["strategy"] == "hybrid+graph"
    empty = _payload(await mcp.call_tool("search_dramas", {"query": "   "}))
    assert empty["error"]["code"] == "EMPTY_QUERY"


async def test_get_drama_view_and_not_found_error_model(server):
    mcp, _ = server
    d = _payload(await mcp.call_tool("get_drama", {"drama_id": 1}))
    assert d["title"] == "도깨비" and d["year"] == 2016 and d["broadcaster"]["code"] == "tvn"
    assert d["cast"] == [{"person_id": 10, "name": "공유", "character": "김신", "main_cast": True}]
    assert d["crew"] == [{"person_id": 11, "name": "김은숙", "role": "WRITER"}]
    assert d["ost"][0]["artists"] == ["찬열", "펀치"]
    assert d["synopsis_source"]["license"] == "CC BY-SA 4.0"
    assert d["official_links"] == {"count": 1, "verified": 0}
    assert d["url"] == "https://dm.test/dramas/goblin"
    missing = _payload(await mcp.call_tool("get_drama", {"drama_id": 999}))
    assert missing == {"error": {"code": "DRAMA_NOT_FOUND", "message": "no drama 999",
                                 "retryable": False}}


async def test_actor_works_are_chronological_and_graph_failure_is_soft(server):
    mcp, _ = server
    p = _payload(await mcp.call_tool("get_actor", {"person_id": 10}))
    assert [w["year"] for w in p["works"]] == [2007, 2016]
    assert p["collaboration_summary"] == [{"id": 12, "name": "이동욱", "shared": 1}]
    missing = _payload(await mcp.call_tool("get_actor", {"person_id": 11}))
    assert missing["error"]["code"] == "PERSON_NOT_FOUND"


async def test_watch_links_flag_stale_verification(server):
    mcp, _ = server
    out = _payload(await mcp.call_tool("get_official_watch_links", {"drama_id": 1}))
    assert out["items"][0]["provider"] == "tving" and out["items"][0]["last_verified_at"] is None
    assert out["warning"]["code"] == "LINK_STALE"
    assert _payload(await mcp.call_tool("get_official_watch_links",
                                        {"drama_id": 1, "region": "US"}))["items"] == []


async def test_graph_traversal_is_bounded_and_rate_limited(server):
    mcp, backend = server
    out = _payload(await mcp.call_tool("traverse_drama_graph",
                                       {"start_type": "DRAMA", "start_id": 1, "max_depth": 5,
                                        "limit": 500}))
    assert out["depth"] == 2 and len(out["neighbours"]) <= 50
    ids = [n["id"] for n in out["neighbours"]]
    assert ids[:2] == [2, 3] and 4 in ids            # depth-2 node reached via drama 2
    assert {n["relation"] for n in out["neighbours"][:2]} == {"ACTED_IN", "PERFORMED"}
    person = _payload(await mcp.call_tool("traverse_drama_graph",
                                          {"start_type": "PERSON", "start_id": 10}))
    assert person["neighbours"][0]["name"] == "이동욱"
    # graph_per_minute=2 in the fixture: third call in the window is refused
    third = _payload(await mcp.call_tool("traverse_drama_graph",
                                         {"start_type": "PERSON", "start_id": 10}))
    assert third["error"]["code"] == "RATE_LIMITED" and third["error"]["retryable"] is True


async def test_resources_and_prompts(server):
    mcp, _ = server
    templates = {t.uri_template for t in await mcp.list_resource_templates()}
    assert templates == {"drama://{drama_id}", "actor://{person_id}", "year://{year}",
                         "broadcaster://{code}"}
    drama = await mcp.read_resource("drama://1")
    body = json.loads(list(drama)[0].content)
    assert body["title"] == "도깨비"
    year = json.loads(list(await mcp.read_resource("year://2016"))[0].content)
    assert year["items"][0]["slug"] == "goblin"
    bc = json.loads(list(await mcp.read_resource("broadcaster://TVN"))[0].content)
    assert bc["name"] == "tvN"
    prompts = {p.name for p in await mcp.list_prompts()}
    assert prompts == {"nostalgia_search", "actor_journey"}
    prompt = await mcp.get_prompt("nostalgia_search", {"memory_text": "겨울 불멸 남주",
                                                        "optional_year_hint": "2016"})
    text = prompt.messages[0].content.text
    assert "search_dramas" in text and "2016" in text and "겨울 불멸 남주" in text


async def test_streamable_http_stateless_roundtrip(server):
    """No initialize handshake needed in stateless mode: one POST per call."""
    mcp, _ = server
    app = mcp.streamable_http_app(
        stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    headers = {"Accept": "application/json, text/event-stream",
               "Content-Type": "application/json", "MCP-Protocol-Version": "2025-06-18"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://mcp") as client:
            resp = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "get_ost", "arguments": {"drama_id": 1}},
            })
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    payload = result.get("structuredContent") or json.loads(result["content"][0]["text"])
    payload = payload.get("result", payload)
    assert payload["items"][0]["title"] == "Stay With Me"
