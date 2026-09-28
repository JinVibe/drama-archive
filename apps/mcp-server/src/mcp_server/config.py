from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment: MCP_DOMAIN_API_URL, MCP_AI_API_URL, ..."""

    model_config = SettingsConfigDict(env_prefix="MCP_")

    domain_api_url: str = "http://domain-api:8081"
    ai_api_url: str = "http://ai-api:8090"
    request_timeout_seconds: float = 10.0

    # docs/MCP_SPEC.md §9 — starting values, revisit with traffic.
    search_per_minute: int = 30
    read_per_minute: int = 120
    graph_per_minute: int = 20

    # §14 graph explosion: depth/node caps regardless of what the client asks for.
    graph_max_depth: int = 2
    graph_max_nodes: int = 50

    # Public base URL for web links inside tool results (`url` fields).
    web_base_url: str = "https://dramamemory.example"
