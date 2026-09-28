"""HTTP access to the application query layer (domain-api + ai-api).

The MCP server holds no data of its own: every tool is a thin, typed view over
the same REST endpoints the web app uses (MCP_SPEC §1). Only fixed, server-side
URLs are ever fetched — no client-supplied URL reaches this module (§14 SSRF).
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx


class BackendError(Exception):
    """Mapped onto the tool error model (MCP_SPEC §11)."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


class Backend(Protocol):
    async def search(self, q: str, *, size: int, year_from: int | None, year_to: int | None,
                     broadcaster: str | None) -> dict[str, Any]: ...
    async def drama(self, drama_id: int) -> dict[str, Any]: ...
    async def person(self, person_id: int) -> dict[str, Any]: ...
    async def year(self, year: int, *, size: int) -> dict[str, Any]: ...
    async def broadcasters(self) -> list[dict[str, Any]]: ...
    async def related_dramas(self, drama_id: int, *, limit: int) -> dict[str, Any]: ...
    async def collaborators(self, person_id: int, *, limit: int) -> dict[str, Any]: ...


class HttpBackend:
    def __init__(self, domain_api_url: str, ai_api_url: str, *, timeout: float = 10.0):
        # MERGED entities answer 301 to the survivor: follow it (MCP clients carry ids).
        self._domain = httpx.AsyncClient(base_url=domain_api_url, timeout=timeout,
                                         follow_redirects=True)
        self._ai = httpx.AsyncClient(base_url=ai_api_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._domain.aclose()
        await self._ai.aclose()

    async def _get(self, client: httpx.AsyncClient, path: str, *, not_found: str,
                   params: dict[str, Any] | None = None) -> Any:
        try:
            resp = await client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise BackendError("UPSTREAM_UNAVAILABLE", f"{path}: {exc}", retryable=True) from exc
        if resp.status_code == 404:
            raise BackendError(not_found, f"nothing published at {path}")
        if resp.status_code == 503:
            raise BackendError("UPSTREAM_UNAVAILABLE", f"{path}: not ready", retryable=True)
        if resp.status_code >= 400:
            raise BackendError("UPSTREAM_ERROR", f"{path}: HTTP {resp.status_code}")
        return resp.json()

    async def search(self, q: str, *, size: int, year_from: int | None, year_to: int | None,
                     broadcaster: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"q": q, "size": size}
        if year_from is not None:
            params["year_from"] = year_from
        if year_to is not None:
            params["year_to"] = year_to
        if broadcaster:
            params["broadcaster"] = broadcaster
        return await self._get(self._ai, "/v1/search", params=params, not_found="SEARCH_FAILED")

    async def drama(self, drama_id: int) -> dict[str, Any]:
        return await self._get(self._domain, f"/api/v1/dramas/by-id/{drama_id}",
                               not_found="DRAMA_NOT_FOUND")

    async def person(self, person_id: int) -> dict[str, Any]:
        return await self._get(self._domain, f"/api/v1/persons/by-id/{person_id}",
                               not_found="PERSON_NOT_FOUND")

    async def year(self, year: int, *, size: int) -> dict[str, Any]:
        return await self._get(self._domain, f"/api/v1/years/{year}", params={"size": size},
                               not_found="YEAR_NOT_FOUND")

    async def broadcasters(self) -> list[dict[str, Any]]:
        return await self._get(self._domain, "/api/v1/broadcasters", not_found="NOT_FOUND")

    async def related_dramas(self, drama_id: int, *, limit: int) -> dict[str, Any]:
        return await self._get(self._ai, f"/v1/graph/dramas/{drama_id}/related",
                               params={"limit": limit}, not_found="DRAMA_NOT_FOUND")

    async def collaborators(self, person_id: int, *, limit: int) -> dict[str, Any]:
        return await self._get(self._ai, f"/v1/graph/persons/{person_id}/collaborators",
                               params={"limit": limit}, not_found="PERSON_NOT_FOUND")
