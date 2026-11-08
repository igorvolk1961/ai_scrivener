from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from rag_indexer.client import RagClient, RagClientError


def _client(handler: httpx.MockTransport) -> RagClient:
    http_client = httpx.AsyncClient(
        base_url="http://rag.test",
        transport=handler,
    )
    return RagClient("http://rag.test", "abc123", client=http_client)


def test_index_chunks_posts_payload_and_token() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["token"] = request.headers.get("X-Service-Token")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"indexed_chunks": 1})

    client = _client(httpx.MockTransport(handler))
    payload = {"source_type": "knowledge_material", "chunks": []}

    result = asyncio.run(client.index_chunks(payload))
    asyncio.run(client.close())

    assert result == {"indexed_chunks": 1}
    assert captured["url"] == "http://rag.test/v1/index/chunks"
    assert captured["token"] == "abc123"  # noqa: S105
    assert captured["body"] == payload


def test_retrieve_posts_query_and_filters() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": []})

    client = _client(httpx.MockTransport(handler))
    result = asyncio.run(client.retrieve("вопрос", {"source_types": ["template"]}, 5))
    asyncio.run(client.close())

    assert result == {"results": []}
    assert captured["url"] == "http://rag.test/v1/retrieve"
    assert captured["body"] == {
        "query": "вопрос",
        "filters": {"source_types": ["template"]},
        "top_k": 5,
    }


def test_activate_posts_version() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"activated": True})

    client = _client(httpx.MockTransport(handler))
    result = asyncio.run(client.activate("knowledge_material", "sha-1", "v2"))
    asyncio.run(client.close())

    assert result == {"activated": True}
    assert captured["url"] == "http://rag.test/v1/index/activate"
    assert captured["body"] == {
        "source_type": "knowledge_material",
        "source_id": "sha-1",
        "version": "v2",
    }


def test_collection_and_alias_methods() -> None:
    captured: list[tuple[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={"ok": True})

    client = _client(httpx.MockTransport(handler))
    asyncio.run(client.create_collection("knowledge_v3"))
    asyncio.run(client.switch_alias("knowledge_current", "knowledge_v3"))
    asyncio.run(client.close())

    assert captured == [
        ("http://rag.test/v1/admin/collections", {"name": "knowledge_v3"}),
        (
            "http://rag.test/v1/admin/alias",
            {"alias": "knowledge_current", "collection": "knowledge_v3"},
        ),
    ]


def test_cleanup_posts_options() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"deleted": 3})

    client = _client(httpx.MockTransport(handler))
    result = asyncio.run(client.cleanup(12, "knowledge_material"))
    asyncio.run(client.close())

    assert result == {"deleted": 3}
    assert captured["url"] == "http://rag.test/v1/index/cleanup"
    assert captured["body"] == {
        "older_than_hours": 12,
        "source_type": "knowledge_material",
    }


def test_delete_encodes_path() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"deleted": True})

    client = _client(httpx.MockTransport(handler))
    asyncio.run(client.delete("knowledge_material", "sha/1"))
    asyncio.run(client.close())

    assert captured["url"] == "http://rag.test/v1/index/knowledge_material/sha%2F1"


def test_delete_targets_collection() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"deleted": True})

    client = _client(httpx.MockTransport(handler))
    asyncio.run(client.delete("knowledge_material", "sha-1", "knowledge_v2"))
    asyncio.run(client.close())

    assert captured["url"].endswith("?target_collection=knowledge_v2")


def test_client_raises_on_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = _client(httpx.MockTransport(handler))

    with pytest.raises(RagClientError):
        asyncio.run(client.index_chunks({"source_type": "x", "chunks": []}))
    asyncio.run(client.close())
