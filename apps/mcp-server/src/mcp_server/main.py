"""ASGI entry point: `POST /mcp` (streamable HTTP, stateless, JSON responses) + `/health`.

Stateless mode (MCP 2026-07-28 core) means any instance behind the gateway can
answer any request — no session store (MCP_SPEC §2).
"""

from __future__ import annotations

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.backend import HttpBackend
from mcp_server.config import Settings
from mcp_server.server import build_server

settings = Settings()
backend = HttpBackend(settings.domain_api_url, settings.ai_api_url,
                      timeout=settings.request_timeout_seconds)
mcp = build_server(settings, backend)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "UP", "server": mcp.name, "version": mcp.version})


app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    # Host allow-listing belongs to the gateway/WAF in front of this service (§2).
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
