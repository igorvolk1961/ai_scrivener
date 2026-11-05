from __future__ import annotations

import asyncio
from typing import Any

import httpx

from rag_service.config import ApplicationParameters, ServiceSettings


class CloudRuError(RuntimeError):
    pass


def _root_url(value: str) -> str:
    return value.rstrip("/").removesuffix("/v1")


def _embedding_url(value: str) -> str:
    return f"{_root_url(value)}/v1/embeddings"


def _score_url(value: str) -> str:
    return f"{_root_url(value)}/score"


class CloudRuEmbedder:
    def __init__(
        self,
        settings: ServiceSettings,
        parameters: ApplicationParameters,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if settings.foundation_api_key is None:
            raise CloudRuError("RAG_FOUNDATION_API_KEY is not set")
        self._settings = settings
        self._parameters = parameters
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(parameters.gigachat.request_timeout_seconds)
        )
        self._dimension: int | None = None

    @property
    def dimension(self) -> int | None:
        return self._dimension

    async def close(self) -> None:
        await self._client.aclose()

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
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
                    raise CloudRuError(f"Cloud.ru embeddings returned HTTP {status}") from error
                if attempt + 1 >= attempts:
                    raise CloudRuError(f"Cloud.ru embeddings returned HTTP {status}") from error
            except httpx.RequestError as error:
                if attempt + 1 >= attempts:
                    raise CloudRuError("Cloud.ru embeddings request failed") from error
            delay = backoff[min(attempt, len(backoff) - 1)]
            await asyncio.sleep(delay)
        raise CloudRuError("Cloud.ru embeddings retries exhausted")

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._settings.foundation_api_key is None:
            raise CloudRuError("RAG_FOUNDATION_API_KEY is not set")
        response = await self._request_with_retries(
            "POST",
            _embedding_url(self._settings.foundation_api_url),
            headers={
                "Authorization": ("Bearer " + self._settings.foundation_api_key.get_secret_value()),
                "Accept": "application/json",
            },
            json={
                "model": self._settings.foundation_embedding_model,
                "input": texts,
            },
        )
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list):
            raise CloudRuError("invalid Cloud.ru embeddings response")
        ordered = sorted(data, key=lambda item: item.get("index", 0))
        vectors: list[list[float]] = []
        for item in ordered:
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise CloudRuError("invalid Cloud.ru embedding vector")
            vector = [float(value) for value in embedding]
            if self._dimension is None:
                self._dimension = len(vector)
            elif len(vector) != self._dimension:
                raise CloudRuError("Cloud.ru embedding dimension mismatch")
            vectors.append(vector)
        if len(vectors) != len(texts):
            raise CloudRuError("Cloud.ru embeddings count mismatch")
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
            raise CloudRuError("Cloud.ru embedding dimension is not available")
        return self._dimension


class CloudRuReranker:
    def __init__(
        self,
        settings: ServiceSettings,
        parameters: ApplicationParameters,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if settings.foundation_api_key is None:
            raise CloudRuError("RAG_FOUNDATION_API_KEY is not set")
        self._settings = settings
        self._parameters = parameters
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(parameters.gigachat.request_timeout_seconds)
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
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
                    raise CloudRuError(f"Cloud.ru rerank returned HTTP {status}") from error
                if attempt + 1 >= attempts:
                    raise CloudRuError(f"Cloud.ru rerank returned HTTP {status}") from error
            except httpx.RequestError as error:
                if attempt + 1 >= attempts:
                    raise CloudRuError("Cloud.ru rerank request failed") from error
            delay = backoff[min(attempt, len(backoff) - 1)]
            await asyncio.sleep(delay)
        raise CloudRuError("Cloud.ru rerank retries exhausted")

    async def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        if self._settings.foundation_api_key is None:
            raise CloudRuError("RAG_FOUNDATION_API_KEY is not set")
        scores: list[float] = []
        batch_size = max(1, self._parameters.rag.rerank_batch_size)
        start = 0
        while start < len(documents):
            batch = documents[start : start + batch_size]
            response = await self._request_with_retries(
                "POST",
                _score_url(self._settings.foundation_api_url),
                headers={
                    "Authorization": (
                        "Bearer " + self._settings.foundation_api_key.get_secret_value()
                    ),
                    "Accept": "application/json",
                },
                json={
                    "model": self._settings.foundation_rerank_model,
                    "encoding_format": "float",
                    "text_1": query,
                    "text_2": batch,
                },
            )
            payload = response.json()
            data = payload.get("data")
            if not isinstance(data, list):
                raise CloudRuError("invalid Cloud.ru rerank response")
            ordered = sorted(data, key=lambda item: item.get("index", 0))
            if len(ordered) != len(batch):
                raise CloudRuError("Cloud.ru rerank count mismatch")
            for item in ordered:
                score = item.get("score")
                if not isinstance(score, (int, float)):
                    raise CloudRuError("invalid Cloud.ru rerank score")
                scores.append(float(score))
            start += batch_size
        return scores
