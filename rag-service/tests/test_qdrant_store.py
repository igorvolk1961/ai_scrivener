from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from qdrant_client import AsyncQdrantClient

from rag_service.chunking import TextChunk
from rag_service.models import SearchFilters
from rag_service.qdrant_store import IndexedDocument, QdrantStore, VectorStoreError, point_id


def _store(client: AsyncMock | None = None) -> QdrantStore:
    return QdrantStore(
        url="http://qdrant:6333",
        collection="test",
        client=cast(AsyncQdrantClient | None, client),
    )


def test_point_id_is_deterministic() -> None:
    first = point_id("template", "doc-1", "1", 0)
    second = point_id("template", "doc-1", "1", 0)
    assert first == second
    assert first != point_id("template", "doc-1", "2", 0)


def test_ensure_collection_creates_vectors_and_indexes() -> None:
    client = AsyncMock()
    store = _store(client)
    client.collection_exists.return_value = False
    asyncio.run(store.ensure_collection(3))

    client.create_collection.assert_awaited_once()
    assert client.create_payload_index.await_count == 5


def test_ensure_collection_rejects_dimension_mismatch() -> None:
    client = AsyncMock()
    store = _store(client)
    client.collection_exists.return_value = True
    client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=4)))
    )
    with pytest.raises(VectorStoreError, match="dimension 4, expected 3"):
        asyncio.run(store.ensure_collection(3))


def test_upsert_builds_payload_and_replaces_source() -> None:
    client = AsyncMock()
    store = _store(client)
    store._client = client
    document = IndexedDocument(
        source_id="doc-1",
        version="1",
        title="Шаблон",
        metadata={"doc_type": "ИсходящийДокумент", "position_ids": ["p-1"]},
    )

    count = asyncio.run(
        store.upsert(
            "template",
            document,
            [TextChunk(index=0, text="текст")],
            [[1.0, 2.0, 3.0]],
        )
    )

    assert count == 1
    client.delete.assert_awaited_once()
    points = client.upsert.await_args.kwargs["points"]
    assert points[0].payload["doc_type"] == "ИсходящийДокумент"
    assert points[0].payload["position_ids"] == ["p-1"]


def test_search_maps_payload_to_result() -> None:
    client = AsyncMock()
    store = _store(client)
    client.query_points.return_value = SimpleNamespace(
        points=[
            SimpleNamespace(
                score=0.9,
                payload={
                    "source_type": "template",
                    "source_id": "doc-1",
                    "version": "1",
                    "title": "Шаблон",
                    "chunk_index": 0,
                    "text": "текст",
                    "metadata": {"doc_type": "ИсходящийДокумент"},
                },
            )
        ]
    )
    results = asyncio.run(
        store.search(
            [1.0, 2.0, 3.0],
            SearchFilters(source_types=["template"]),
            limit=10,
            min_score=0.0,
        )
    )

    assert len(results) == 1
    assert results[0].source_id == "doc-1"
    assert results[0].score == 0.9
    client.query_points.assert_awaited_once()
