# mcp-server

Remote MCP server (Python SDK v2, streamable HTTP, **stateless**) exposing the public
catalog/search/graph capabilities of `docs/MCP_SPEC.md` to AI clients. It owns no data:
every tool is a typed view over domain-api (`/api/v1/*`) and ai-api (`/v1/search`, `/v1/graph/*`).

```text
POST /mcp        JSON-RPC (Accept: application/json, text/event-stream); no session handshake needed
GET  /health
```

| Capability | Names |
|---|---|
| Tools | `search_dramas`, `get_drama`, `get_actor`, `get_ost`, `get_official_watch_links`, `traverse_drama_graph` |
| Resources | `drama://{id}`, `actor://{id}`, `year://{year}`, `broadcaster://{code}` |
| Prompts | `nostalgia_search`, `actor_journey` |

Not registered on purpose: the protected set (`get_my_timeline`, `mark_watched`, `add_memory_note`,
`timeline://me`) — it needs the OAuth authorization server (MCP_SPEC §5/§8), which does not exist yet.
Errors come back as `{"error": {"code", "message", "retryable"}}` (§11). Rate limits (§9) are
in-process per client IP; graph traversal is capped at depth 2 / 50 nodes (§14).

```sh
# local
docker compose up -d --build mcp-server        # http://localhost:8100/mcp
curl -s localhost:8100/mcp -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_dramas","arguments":{"query":"2016년 공유 판타지"}}}'

# tests (fake backend + one stateless HTTP roundtrip)
pip install -e ".[dev]" && ruff check . && pytest -q
```

Environment: `MCP_DOMAIN_API_URL`, `MCP_AI_API_URL`, `MCP_WEB_BASE_URL`, `MCP_*_PER_MINUTE`.
