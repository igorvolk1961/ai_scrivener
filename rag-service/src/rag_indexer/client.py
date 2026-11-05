from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx


class RagClientError(RuntimeError):
    pass


class RagClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout_seconds,
            headers={"X-Service-Token": token},
        )
        self._owns_client = client is None

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def index_chunks(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/v1/index/chunks", json=payload)

    async def retrieve(
        self,
        query: str,
        filters: dict[str, Any],
        top_k: int = 10,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/retrieve",
            json={"query": query, "filters": filters, "top_k": top_k},
        )

    async def activate(
        self,
        source_type: str,
        source_id: str,
        version: str,
        target_collection: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_type": source_type,
            "source_id": source_id,
            "version": version,
        }
        if target_collection is not None:
            payload["target_collection"] = target_collection
        return await self._request(
            "POST",
            "/v1/index/activate",
            json=payload,
        )

    async def create_collection(self, name: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/admin/collections",
            json={"name": name},
        )

    async def switch_alias(self, alias: str, collection: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/admin/alias",
            json={"alias": alias, "collection": collection},
        )

    async def cleanup(
        self,
        older_than_hours: float,
        source_type: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/index/cleanup",
            json={
                "older_than_hours": older_than_hours,
                "source_type": source_type,
            },
        )

    async def delete(
        self,
        source_type: str,
        source_id: str,
        target_collection: str | None = None,
    ) -> dict[str, Any]:
        path = f"/v1/index/{quote(source_type, safe='')}/{quote(source_id, safe='')}"
        if target_collection is not None:
            path += f"?target_collection={quote(target_collection, safe='')}"
        return await self._request("DELETE", path)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(
                method,
                path,
                json=json,
                headers={"X-Service-Token": self._token},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RagClientError(f"{method} {path} failed") from error
        payload = response.json()
        if not isinstance(payload, dict):
            raise RagClientError(f"{method} {path} returned invalid JSON")
        return payload
