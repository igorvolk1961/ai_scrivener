from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from rag_service.config import ApplicationParameters, ServiceSettings
from rag_service.gigachat import GigaChatClient, GigaChatError


def test_embed_caches_oauth_token(
    parameters: ApplicationParameters,
    settings: ServiceSettings,
) -> None:
    async def scenario() -> None:
        async with respx.mock:
            oauth = respx.post("https://oauth.example/token").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "access_token": "token",
                        "expires_at": int(time.time() * 1000) + 3_600_000,
                    },
                )
            )
            embeddings = respx.post("https://embeddings.example/v1").mock(
                return_value=httpx.Response(
                    200,
                    json={"data": [{"index": 0, "embedding": [1.0, 2.0, 3.0]}]},
                )
            )
            client = GigaChatClient(settings, parameters)
            try:
                first = await client.embed(["первый"])
                second = await client.embed(["второй"])
            finally:
                await client.close()
        assert first == [[1.0, 2.0, 3.0]]
        assert second == [[1.0, 2.0, 3.0]]
        assert oauth.call_count == 1
        assert embeddings.call_count == 2

    asyncio.run(scenario())


def test_embedding_dimension_mismatch_is_rejected(
    parameters: ApplicationParameters,
    settings: ServiceSettings,
) -> None:
    async def scenario() -> None:
        async with respx.mock:
            respx.post("https://oauth.example/token").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "access_token": "token",
                        "expires_at": int(time.time() * 1000) + 3_600_000,
                    },
                )
            )
            respx.post("https://embeddings.example/v1").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "data": [
                            {"index": 0, "embedding": [1.0, 2.0, 3.0]},
                            {"index": 1, "embedding": [1.0, 2.0]},
                        ]
                    },
                )
            )
            client = GigaChatClient(settings, parameters)
            try:
                with pytest.raises(GigaChatError):
                    await client.embed(["первый", "второй"])
            finally:
                await client.close()

    asyncio.run(scenario())


def test_retry_on_configured_status(
    parameters: ApplicationParameters,
    settings: ServiceSettings,
) -> None:
    retry_parameters = parameters.model_copy(deep=True)
    retry_parameters.gigachat.max_retries = 1
    retry_parameters.gigachat.retry_backoff_seconds = [0.0]

    async def scenario() -> None:
        async with respx.mock:
            respx.post("https://oauth.example/token").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "access_token": "token",
                        "expires_at": int(time.time() * 1000) + 3_600_000,
                    },
                )
            )
            embeddings = respx.post("https://embeddings.example/v1").mock(
                side_effect=[
                    httpx.Response(500, json={"error": "temporary"}),
                    httpx.Response(
                        200,
                        json={"data": [{"index": 0, "embedding": [1.0, 2.0, 3.0]}]},
                    ),
                ]
            )
            client = GigaChatClient(settings, retry_parameters)
            try:
                result = await client.embed(["текст"])
            finally:
                await client.close()
        assert result == [[1.0, 2.0, 3.0]]
        assert embeddings.call_count == 2

    asyncio.run(scenario())
