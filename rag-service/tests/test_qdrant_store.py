from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from qdrant_client import AsyncQdrantClient, models

from rag_service.chunking import TextChunk
from rag_service.models import IndexChunk, SearchFilters
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
    assert client.create_payload_index.await_count == 16


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


def test_search_applies_folder_employee_and_purpose_filters() -> None:
    client = AsyncMock()
    store = _store(client)
    client.query_points.return_value = SimpleNamespace(points=[])
    asyncio.run(
        store.search(
            [1.0, 2.0, 3.0],
            SearchFilters(
                source_types=["document"],
                folders=["folder-1"],
                employees=["ГенДиректор"],
                purposes=["Сформированные"],
            ),
            limit=10,
            min_score=0.0,
        )
    )
    conditions = client.query_points.await_args.kwargs["query_filter"].must
    keys = {
        condition.key: condition.match.any
        for condition in conditions
        if hasattr(condition, "key") and hasattr(condition.match, "any")
    }
    assert keys["metadata.folders"] == ["folder-1"]
    assert keys["metadata.employees"] == ["ГенДиректор"]
    assert keys["metadata.purposes"] == ["Сформированные"]


def test_upsert_chunks_builds_structured_payload() -> None:
    client = AsyncMock()
    store = _store(client)
    store._client = client
    document = IndexedDocument(
        source_id="sha-1",
        version="1",
        title="ГОСТ",
        metadata={"doc_type": "ГОСТ", "status": "verified"},
    )
    chunk = IndexChunk(
        index=0,
        text="Текст пункта",
        embedding_text="Документ: ГОСТ\nПункт: 4.1\nТекст: Текст пункта",
        section_path=["4", "4.1"],
        clause="4.1",
        page_start=3,
        parent_id="sha-1:4.1",
    )
    count = asyncio.run(
        store.upsert_chunks(
            "knowledge_material",
            document,
            [chunk],
            [[1.0, 2.0, 3.0]],
            [models.SparseVector(indices=[1], values=[1.0])],
        )
    )

    assert count == 1
    point = client.upsert.await_args.kwargs["points"][0]
    assert point.payload["section_path"] == ["4", "4.1"]
    assert point.payload["clause"] == "4.1"
    assert point.payload["parent_id"] == "sha-1:4.1"
    assert point.payload["status"] == "verified"
    assert point.vector["sparse"].indices == [1]


def test_search_hybrid_uses_prefetch_and_rrf() -> None:
    client = AsyncMock()
    store = _store(client)
    client.query_points.return_value = SimpleNamespace(points=[])
    asyncio.run(
        store.search_hybrid(
            [1.0, 2.0, 3.0],
            models.SparseVector(indices=[1], values=[1.0]),
            SearchFilters(source_types=["knowledge_material"]),
            limit=10,
            hnsw_ef=128,
        )
    )

    kwargs = client.query_points.await_args.kwargs
    assert len(kwargs["prefetch"]) == 2
    assert kwargs["query"].fusion == models.Fusion.RRF


def test_switch_alias_replaces_existing_alias() -> None:
    client = AsyncMock()
    store = _store(client)
    client.get_aliases.return_value = SimpleNamespace(
        aliases=[SimpleNamespace(alias_name="current")]
    )
    asyncio.run(store.switch_alias("current", "test_v2"))

    operations = client.update_collection_aliases.await_args.kwargs[
        "change_aliases_operations"
    ]
    assert len(operations) == 2
    assert isinstance(operations[0], models.DeleteAliasOperation)
    assert isinstance(operations[1], models.CreateAliasOperation)


def test_fetch_parent_chunks_sorts_and_limits() -> None:
    client = AsyncMock()
    store = _store(client)
    first = SimpleNamespace(
        score=0.0,
        payload={
            "source_type": "knowledge_material",
            "source_id": "sha-1",
            "version": "1",
            "title": "ГОСТ",
            "chunk_index": 0,
            "text": "первый",
            "metadata": {},
        },
    )
    second = SimpleNamespace(
        score=0.0,
        payload={
            "source_type": "knowledge_material",
            "source_id": "sha-1",
            "version": "1",
            "title": "ГОСТ",
            "chunk_index": 1,
            "text": "второй",
            "metadata": {},
        },
    )
    client.scroll.return_value = ([second, first], None)
    results = asyncio.run(
        store.fetch_parent_chunks("knowledge_material", "sha-1", "sha-1:4.1", 20)
    )

    assert [result.chunk_index for result in results] == [0, 1]
    assert client.scroll.await_args.kwargs["limit"] == 20
