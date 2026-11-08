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
    client.get_aliases.return_value = SimpleNamespace(aliases=[])
    client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=3)))
    )
    asyncio.run(store.ensure_collection(3))

    client.create_collection.assert_awaited_once()
    assert client.create_payload_index.await_count == 25


def test_ensure_collection_resolves_alias_target() -> None:
    client = AsyncMock()
    store = _store(client)
    client.get_aliases.return_value = SimpleNamespace(
        aliases=[
            SimpleNamespace(
                alias_name="test",
                collection_name="knowledge_v2",
            )
        ]
    )
    client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=3)))
    )

    asyncio.run(store.ensure_collection(3))

    client.get_collection.assert_awaited_once_with("knowledge_v2")
    client.create_collection.assert_not_awaited()


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


def test_search_applies_acl_and_current_version_filters() -> None:
    client = AsyncMock()
    store = _store(client)
    client.query_points.return_value = SimpleNamespace(points=[])

    asyncio.run(
        store.search(
            [1.0, 2.0, 3.0],
            SearchFilters(
                source_types=["document_internal"],
                family_ids=["family-1"],
                is_current=True,
                acl_principals=["user:1", "position:2"],
            ),
            limit=10,
            min_score=0.0,
        )
    )

    query_filter = client.query_points.await_args.kwargs["query_filter"]
    conditions = query_filter.must
    keys = {condition.key for condition in conditions}
    assert "family_id" in keys
    assert "is_current" in keys
    assert "acl_principals" in keys
    assert query_filter.must_not
    assert query_filter.must_not[0].key == "acl_deny_principals"


def test_upsert_chunks_builds_document_payload() -> None:
    client = AsyncMock()
    store = _store(client)
    document = IndexedDocument(
        source_id="doc-1",
        version="v1",
        title="Приказ",
        metadata={
            "family_id": "family-1",
            "status": "approved",
            "is_current": True,
            "acl_principals": ["user:1"],
            "acl_deny_principals": ["user:2"],
            "acl_version": "acl-v1",
            "doc_kind": "Внутренний",
            "registration_number": "12",
        },
    )

    asyncio.run(
        store.upsert_chunks(
            "document_internal",
            document,
            [IndexChunk(index=0, text="Текст")],
            [[1.0, 2.0, 3.0]],
            replace_existing=False,
            active=False,
        )
    )

    point = client.upsert.await_args.kwargs["points"][0]
    assert point.payload["document_key"] == "document_internal:family-1"
    assert point.payload["family_id"] == "family-1"
    assert point.payload["is_current"] is True
    assert point.payload["acl_principals"] == ["user:1"]
    assert point.payload["acl_deny_principals"] == ["user:2"]
    assert point.payload["active"] is False


def test_update_payload_updates_existing_source() -> None:
    client = AsyncMock()
    store = _store(client)
    client.count.return_value = SimpleNamespace(count=1)

    updated = asyncio.run(
        store.update_payload(
            "document_internal",
            "doc-1",
            {"active": False, "is_current": False},
            version="v1",
        )
    )

    assert updated is True
    client.set_payload.assert_awaited_once()
    payload = client.set_payload.await_args.kwargs["payload"]
    assert payload["active"] is False
    assert payload["is_current"] is False


def test_activate_document_can_keep_old_versions_inactive() -> None:
    client = AsyncMock()
    store = _store(client)
    client.count.return_value = SimpleNamespace(count=1)

    activated = asyncio.run(
        store.activate_document(
            "document_internal",
            "doc-1",
            "v2",
            keep_inactive=True,
        )
    )

    assert activated is True
    assert client.set_payload.await_count == 2
    client.delete.assert_not_awaited()


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


def test_upsert_chunks_can_append_without_delete() -> None:
    client = AsyncMock()
    store = _store(client)
    document = IndexedDocument(
        source_id="sha-1",
        version="1",
        title="ГОСТ",
        metadata={},
    )
    chunk = IndexChunk(index=0, text="Текст")

    count = asyncio.run(
        store.upsert_chunks(
            "knowledge_material",
            document,
            [chunk],
            [[1.0, 2.0, 3.0]],
            replace_existing=False,
        )
    )

    assert count == 1
    client.delete.assert_not_awaited()
    client.upsert.assert_awaited_once()


def test_activate_document_marks_version_and_removes_others() -> None:
    client = AsyncMock()
    store = _store(client)
    client.count.return_value = SimpleNamespace(count=1)

    activated = asyncio.run(store.activate_document("knowledge_material", "sha-1", "v2"))

    assert activated is True
    client.set_payload.assert_awaited_once()
    client.delete.assert_awaited_once()


def test_activate_document_returns_false_without_points() -> None:
    client = AsyncMock()
    store = _store(client)
    client.count.return_value = SimpleNamespace(count=0)

    activated = asyncio.run(store.activate_document("knowledge_material", "sha-1", "v2"))

    assert activated is False
    client.set_payload.assert_not_awaited()
    client.delete.assert_not_awaited()


def test_cleanup_inactive_deletes_old_staging_points() -> None:
    client = AsyncMock()
    store = _store(client)
    client.count.return_value = SimpleNamespace(count=2)

    deleted = asyncio.run(store.cleanup_inactive(24, "knowledge_material"))

    assert deleted == 2
    client.delete.assert_awaited_once()
    filter_ = client.delete.await_args.kwargs["points_selector"].filter
    keys = {condition.key for condition in filter_.must}
    assert keys == {"active", "created_at", "source_type"}


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

    operations = client.update_collection_aliases.await_args.kwargs["change_aliases_operations"]
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
    results = asyncio.run(store.fetch_parent_chunks("knowledge_material", "sha-1", "sha-1:4.1", 20))

    assert [result.chunk_index for result in results] == [0, 1]
    assert client.scroll.await_args.kwargs["limit"] == 20
