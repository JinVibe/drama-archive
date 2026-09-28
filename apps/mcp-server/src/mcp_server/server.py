"""Tools, resources and prompts — docs/MCP_SPEC.md §4, §6, §7.

Public capabilities only. The protected set (get_my_timeline, mark_watched,
add_memory_note, timeline://me) needs the OAuth authorization server that does
not exist yet; it is deliberately not registered rather than exposed unguarded.

Every tool returns plain JSON. Failures come back as
``{"error": {"code", "message", "retryable"}}`` (§11) instead of raising, so a
model sees a stable shape it can reason about.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer

from mcp_server.backend import Backend, BackendError
from mcp_server.config import Settings

INSTRUCTIONS = """DramaMemory: a Korean drama memory archive (2006 to now; KBS, MBC, SBS, JTBC,
tvN and OTT platforms).
Use search_dramas for natural-language or half-remembered queries ("2016년 겨울 공유 판타지"),
get_drama / get_actor / get_ost for verified facts, get_official_watch_links for where to
watch (only stored, verified links — never invent URLs), and traverse_drama_graph for
cast/OST connections. Results are evidence: quote drama_id/title/year from them rather than
from memory. Synopsis text may be quoted from Korean Wikipedia (CC BY-SA 4.0) — keep the
attribution when you repeat it."""

Relation = Literal["ACTED_IN", "HAS_OST", "PERFORMED"]


class RateLimiter:
    """Sliding one-minute window per (bucket, client). In-process: fine for one
    instance, replace with the gateway's limiter when scaling out (§2)."""

    def __init__(self):
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, bucket: str, client: str, per_minute: int) -> bool:
        now = time.monotonic()
        q = self._hits[(bucket, client)]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= per_minute:
            return False
        q.append(now)
        return True


def _error(exc: BackendError) -> dict[str, Any]:
    return {"error": exc.as_dict()}


def _rate_limited(bucket: str) -> dict[str, Any]:
    return {"error": {"code": "RATE_LIMITED", "message": f"{bucket}: too many requests",
                      "retryable": True}}


def _client_key(ctx: Context | None) -> str:
    try:
        request = ctx.request_context.request  # type: ignore[union-attr]
        return request.client.host or "anon"  # type: ignore[union-attr]
    except Exception:
        return "anon"


def _year(iso: str | None) -> int | None:
    return int(iso[:4]) if iso else None


def _match_reasons(hit: dict[str, Any]) -> list[str]:
    """Which retrievers put this drama forward, e.g. ["fts#1", "graph#2"]."""
    return [f"{name}#{rank}" for name, rank in sorted(hit.get("ranks", {}).items())]


def drama_view(d: dict[str, Any], web_base_url: str) -> dict[str, Any]:
    """get_drama output (§4): facts plus where each quoted text came from."""
    bc = d.get("broadcaster") or {}
    links = d.get("links") or []
    return {
        "drama_id": d["id"],
        "slug": d["slug"],
        "title": d["titleKo"],
        "title_en": d.get("titleEn"),
        "aliases": d.get("aliases") or [],
        "year": _year(d.get("startDate")),
        "start_date": d.get("startDate"),
        "end_date": d.get("endDate"),
        "broadcaster": {"code": bc.get("code"), "name": bc.get("nameKo")} if bc else None,
        "episode_count": d.get("episodeCount"),
        "genres": d.get("genres") or [],
        "cast": [
            {
                "person_id": c["personId"], "name": c["nameKo"],
                "character": c.get("characterName"), "main_cast": c.get("mainCast", False),
            }
            for c in d.get("credits") or [] if c.get("creditType") == "ACTOR"
        ],
        "crew": [
            {"person_id": c["personId"], "name": c["nameKo"], "role": c["creditType"]}
            for c in d.get("credits") or [] if c.get("creditType") != "ACTOR"
        ],
        "ost": ost_view(d),
        "synopsis": d.get("synopsis"),
        "synopsis_source": d.get("synopsisSource"),
        "official_links": {
            "count": len(links),
            "verified": sum(1 for link in links if link.get("lastVerifiedAt")),
        },
        "provenance": {"canonical_version": d.get("canonicalVersion")},
        "url": f"{web_base_url}/dramas/{d['slug']}",
    }


def ost_view(d: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "song_id": s["songId"], "title": s["title"], "release_date": s.get("releaseDate"),
            "part_no": s.get("partNo"),
            "artists": [a["name"] for a in s.get("artists") or []],
        }
        for s in d.get("osts") or []
    ]


def links_view(d: dict[str, Any], region: str) -> dict[str, Any]:
    items = [
        {
            "provider": link["providerCode"], "url": link["url"], "type": link["linkType"],
            "region": link.get("regionCode"), "availability": link.get("availabilityStatus"),
            "last_verified_at": link.get("lastVerifiedAt"),
        }
        for link in d.get("links") or []
        if not region or (link.get("regionCode") or "KR") == region
    ]
    unverified = [i for i in items if not i["last_verified_at"]]
    out: dict[str, Any] = {"drama_id": d["id"], "title": d["titleKo"], "region": region,
                           "items": items}
    if items and len(unverified) == len(items):
        out["warning"] = {"code": "LINK_STALE",
                          "message": "Official links exist but have not been verified recently.",
                          "retryable": True}
    return out


def person_view(p: dict[str, Any], collaborators: list[dict[str, Any]],
                web_base_url: str) -> dict[str, Any]:
    works = sorted(p.get("filmography") or [], key=lambda w: w.get("startDate") or "")
    return {
        "person_id": p["id"],
        "slug": p["slug"],
        "name": p["nameKo"],
        "name_en": p.get("nameEn"),
        "birth_date": p.get("birthDate"),
        "works": [
            {
                "drama_id": w["dramaId"], "title": w["titleKo"], "year": _year(w.get("startDate")),
                "broadcaster": w.get("broadcasterCode"), "role": w["creditType"],
                "character": w.get("characterName"), "main_cast": w.get("mainCast", False),
            }
            for w in works
        ],
        "collaboration_summary": collaborators,
        "url": f"{web_base_url}/persons/{p['slug']}",
    }


def build_server(settings: Settings, backend: Backend) -> MCPServer:
    limiter = RateLimiter()
    mcp = MCPServer(
        "DramaMemory",
        title="DramaMemory",
        description="Korean drama catalog, memory search and cast/OST graph",
        instructions=INSTRUCTIONS,
        version="0.1.0",
    )

    def allow(bucket: str, ctx: Context | None) -> dict[str, Any] | None:
        limit = {"search": settings.search_per_minute, "graph": settings.graph_per_minute}.get(
            bucket, settings.read_per_minute
        )
        return None if limiter.allow(bucket, _client_key(ctx), limit) else _rate_limited(bucket)

    # ------------------------------------------------------------------ tools
    @mcp.tool(description="Find dramas from natural language or half-remembered details "
                          "(year, channel, actor, plot). Returns ranked candidates with the "
                          "retrievers that matched them; verify with get_drama.")
    async def search_dramas(
        query: str,
        year_from: int | None = None,
        year_to: int | None = None,
        broadcaster: str | None = None,
        limit: int = 10,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if denied := allow("search", ctx):
            return denied
        query = query.strip()
        if not query:
            return {"error": {"code": "EMPTY_QUERY", "message": "query is empty",
                              "retryable": False}}
        try:
            r = await backend.search(query, size=max(1, min(limit, 50)), year_from=year_from,
                                     year_to=year_to, broadcaster=broadcaster)
        except BackendError as exc:
            return _error(exc)
        items = [
            {
                "drama_id": h["drama_id"], "title": h["title"],
                "year": h.get("metadata", {}).get("year"),
                "broadcaster": h.get("metadata", {}).get("broadcaster_code"),
                "slug": h.get("metadata", {}).get("slug"),
                "match_reasons": _match_reasons(h), "score": round(h.get("score", 0), 4),
            }
            for h in r.get("hits", [])
        ]
        return {"items": items, "strategy": r.get("strategy"), "relaxed": r.get("relaxed", False),
                "understood": r.get("plan"), "retrieval_version": r.get("retrieval_version")}

    @mcp.tool(description="Canonical facts for one drama: dates, channel, genres, cast, OST, "
                          "synopsis with its source, and how many official links are verified.")
    async def get_drama(drama_id: int, ctx: Context | None = None) -> dict[str, Any]:
        if denied := allow("read", ctx):
            return denied
        try:
            return drama_view(await backend.drama(drama_id), settings.web_base_url)
        except BackendError as exc:
            return _error(exc)

    @mcp.tool(description="Canonical profile of an actor/writer/director with their works in "
                          "order and the people they worked with most (a count, not a claim "
                          "about relationships).")
    async def get_actor(person_id: int, ctx: Context | None = None) -> dict[str, Any]:
        if denied := allow("read", ctx):
            return denied
        try:
            person = await backend.person(person_id)
        except BackendError as exc:
            return _error(exc)
        try:
            collab = (await backend.collaborators(person_id, limit=10)).get("collaborators", [])
        except BackendError:
            collab = []  # graph is optional: the profile still answers
        return person_view(person, collab, settings.web_base_url)

    @mcp.tool(description="OST tracks of a drama with their artists.")
    async def get_ost(drama_id: int, ctx: Context | None = None) -> dict[str, Any]:
        if denied := allow("read", ctx):
            return denied
        try:
            d = await backend.drama(drama_id)
        except BackendError as exc:
            return _error(exc)
        return {"drama_id": d["id"], "title": d["titleKo"], "items": ost_view(d)}

    @mcp.tool(description="Stored, verified official watch links (VOD, broadcaster page, OTT). "
                          "Never construct a URL yourself; if this returns none, say so.")
    async def get_official_watch_links(
        drama_id: int, region: str = "KR", ctx: Context | None = None
    ) -> dict[str, Any]:
        if denied := allow("read", ctx):
            return denied
        try:
            return links_view(await backend.drama(drama_id), region.upper())
        except BackendError as exc:
            return _error(exc)

    @mcp.tool(description="Bounded neighbourhood of a drama or person through cast and OST "
                          "relations (ACTED_IN, HAS_OST, PERFORMED). Depth is capped at 2.")
    async def traverse_drama_graph(
        start_type: Literal["DRAMA", "PERSON"],
        start_id: int,
        relations: list[Relation] | None = None,
        max_depth: int = 1,
        limit: int = 20,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if denied := allow("graph", ctx):
            return denied
        depth = max(1, min(max_depth, settings.graph_max_depth))
        limit = max(1, min(limit, settings.graph_max_nodes))
        rels = set(relations or ["ACTED_IN", "HAS_OST", "PERFORMED"])
        try:
            if start_type == "PERSON":
                collab = await backend.collaborators(start_id, limit=limit)
                nodes = [{"type": "PERSON", **c} for c in collab.get("collaborators", [])]
                return {"start": {"type": "PERSON", "id": start_id}, "depth": 1,
                        "relations": sorted(rels), "neighbours": nodes[:limit]}
            first = await backend.related_dramas(start_id, limit=limit)
            neighbours = _related_nodes(first, rels)
            if depth >= 2:
                seen = {start_id} | {n["id"] for n in neighbours}
                for n in list(neighbours)[:5]:  # cap fan-out: at most 5 second hops
                    more = await backend.related_dramas(int(n["id"]), limit=10)
                    for m in _related_nodes(more, rels):
                        if m["id"] not in seen and len(neighbours) < limit:
                            seen.add(m["id"])
                            neighbours.append({**m, "via": n["id"], "depth": 2})
            return {"start": {"type": "DRAMA", "id": start_id}, "depth": depth,
                    "relations": sorted(rels), "neighbours": neighbours[:limit]}
        except BackendError as exc:
            return _error(exc)

    # -------------------------------------------------------------- resources
    @mcp.resource("drama://{drama_id}", description="Canonical drama representation",
                  mime_type="application/json")
    async def drama_resource(drama_id: int) -> dict[str, Any]:
        try:
            return drama_view(await backend.drama(drama_id), settings.web_base_url)
        except BackendError as exc:
            return _error(exc)

    @mcp.resource("actor://{person_id}", description="Canonical person profile",
                  mime_type="application/json")
    async def actor_resource(person_id: int) -> dict[str, Any]:
        try:
            return person_view(await backend.person(person_id), [], settings.web_base_url)
        except BackendError as exc:
            return _error(exc)

    @mcp.resource("year://{year}", description="Dramas that started in a year",
                  mime_type="application/json")
    async def year_resource(year: int) -> dict[str, Any]:
        try:
            page = await backend.year(year, size=200)
        except BackendError as exc:
            return _error(exc)
        return {
            "year": year, "total": page.get("total"),
            "items": [
                {"drama_id": d["id"], "title": d["titleKo"], "slug": d["slug"],
                 "broadcaster": (d.get("broadcaster") or {}).get("code"),
                 "start_date": d.get("startDate"), "genres": d.get("genres") or []}
                for d in page.get("items", [])
            ],
        }

    @mcp.resource("broadcaster://{code}", description="A channel or platform",
                  mime_type="application/json")
    async def broadcaster_resource(code: str) -> dict[str, Any]:
        try:
            rows = await backend.broadcasters()
        except BackendError as exc:
            return _error(exc)
        for b in rows:
            if b.get("code") == code.lower():
                return {"code": b["code"], "name": b.get("nameKo"), "name_en": b.get("nameEn"),
                        "official_url": b.get("officialUrl")}
        return {"error": {"code": "BROADCASTER_NOT_FOUND", "message": code, "retryable": False}}

    # ---------------------------------------------------------------- prompts
    @mcp.prompt(description="Turn a vague memory of a drama into search_dramas calls")
    def nostalgia_search(memory_text: str, optional_year_hint: str | None = None) -> str:
        hint = ""
        if optional_year_hint:
            hint = f" The user thinks it aired around {optional_year_hint}."
        return (
            "The user half-remembers a Korean drama. Extract the concrete signals from their "
            "memory (year or era, channel, actor names, character jobs, setting, mood, an OST) "
            "and call search_dramas with the natural-language query plus year_from/year_to "
            "when a year is implied. Show the top candidates with title, year and channel, say "
            "which signals matched, and ask one clarifying question if nothing scores clearly. "
            f"Do not invent titles.{hint}\n\nMemory: {memory_text}"
        )

    @mcp.prompt(description="Summarise an actor's works in chronological order")
    def actor_journey(person_name: str) -> str:
        return (
            f"Find {person_name} with search_dramas (query: \"{person_name} 출연작\"), take the "
            "person_id from a matching cast entry via get_drama, then call get_actor. Present "
            "the works chronologically with year, channel and role, and mention frequent "
            "collaborators from collaboration_summary as counts of shared works only."
        )

    return mcp


def _related_nodes(related: dict[str, Any], rels: set[str]) -> list[dict[str, Any]]:
    """Flatten ai-api's related-dramas payload into typed neighbour nodes."""
    out: list[dict[str, Any]] = []
    for key, value in related.items():
        if key == "drama_id" or not isinstance(value, list):
            continue
        via = "PERFORMED" if "ost" in key.lower() or "artist" in key.lower() else "ACTED_IN"
        if via not in rels and not ("HAS_OST" in rels and via == "PERFORMED"):
            continue
        for item in value:
            if isinstance(item, dict) and "id" in item:
                out.append({"type": "DRAMA", "relation": via, "depth": 1, **item})
    return out
