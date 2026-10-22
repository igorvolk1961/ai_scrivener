from __future__ import annotations

import asyncio
import base64
import time
import uuid
from typing import Any

import httpx

from rag_service.config import ApplicationParameters, ServiceSettings


class GigaChatError(RuntimeError):
    pass


class GigaChatClient:
    def __init__(
        self,
        settings: ServiceSettings,
        parameters: ApplicationParameters,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._parameters = parameters
        verify: bool | str = settings.gigachat_ca_bundle or True
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(parameters.gigachat.request_timeout_seconds),
            verify=verify,
        )
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._dimension: int | None = None

    @property
    def dimension(self) -> int | None:
        return self._dimension

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_token(self) -> str:
        now = time.time()
        if self._token is not None and now < self._token_expires_at:
            return self._token
        credentials = (
            f"{self._settings.gigachat_client_id}:"
            f"{self._settings.gigachat_client_secret.get_secret_value()}"
        )
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {encoded}",
            "RqUID": str(uuid.uuid4()),
            "Accept": "application/json",
        }
        response = await self._request_with_retries(
            "POST",
            str(self._settings.gigachat_oauth_url),
            headers=headers,
            data={"scope": self._settings.gigachat_scope},
        )
        payload = response.json()
        token = payload.get("access_token")
        expires_at = payload.get("expires_at")
        if not isinstance(token, str) or not isinstance(expires_at, int):
            raise GigaChatError("invalid OAuth response")
        self._token = token
        skew = self._parameters.gigachat.token_refresh_skew_seconds
        self._token_expires_at = (expires_at / 1000) - skew
        return token

    async def _request_with_retries(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        attempts = self._parameters.gigachat.max_retries + 1
        backoff = self._parameters.gigachat.retry_backoff_seconds
        for attempt in range(attempts):
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                if status not in self._parameters.http.retry_status_codes:
                    raise
                if attempt + 1 >= attempts:
                    raise
            except httpx.RequestError:
                if attempt + 1 >= attempts:
                    raise
            delay = backoff[min(attempt, len(backoff) - 1)]
            await asyncio.sleep(delay)
        raise GigaChatError("request retries exhausted")

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        token = await self._get_token()
        response = await self._request_with_retries(
            "POST",
            str(self._settings.gigachat_api_url),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json={"model": self._settings.gigachat_model, "input": texts},
        )
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list):
            raise GigaChatError("invalid embeddings response")
        ordered = sorted(data, key=lambda item: item.get("index", 0))
        vectors: list[list[float]] = []
        for item in ordered:
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise GigaChatError("invalid embedding vector")
            vector = [float(value) for value in embedding]
            if self._dimension is None:
                self._dimension = len(vector)
            elif len(vector) != self._dimension:
                raise GigaChatError("embedding dimension mismatch")
            vectors.append(vector)
        if len(vectors) != len(texts):
            raise GigaChatError("embeddings count mismatch")
        return vectors

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result: list[list[float]] = []
        batch_size = self._parameters.rag.embedding_batch_size
        start = 0
        while start < len(texts):
            batch = texts[start : start + batch_size]
            result.extend(await self._embed_batch(batch))
            start += batch_size
        return result

    async def probe_dimension(self) -> int:
        if self._dimension is None:
            await self.embed(["ping"])
        if self._dimension is None:
            raise GigaChatError("embedding dimension is not available")
        return self._dimension
