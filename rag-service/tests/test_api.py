from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from rag_service.config import ApplicationParameters, ConfigurationError, ServiceSettings
from rag_service.main import create_app

from .conftest import (
    AUTH_HEADERS,
    FakeEmbedder,
    FakeReranker,
    FakeSparseEncoder,
    FakeStore,
    index_payload,
)


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["qdrant"] is True


def test_search_without_token(client: TestClient) -> None:
    response = client.post("/v1/search", json={"query": "документ"})
    assert response.status_code == 200


def test_index_and_search(client: TestClient, store: FakeStore) -> None:
    response = client.post("/v1/index/upsert", json=index_payload(), headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["indexed_items"] == 1
    assert response.json()["indexed_chunks"] >= 1
    assert ("template", "doc-1") in store.documents

    search = client.post(
        "/v1/search",
        json={"query": "исходящий документ", "filters": {"source_types": ["template"]}},
        headers=AUTH_HEADERS,
    )
    assert search.status_code == 200
    results = search.json()["results"]
    assert len(results) == 1
    assert results[0]["source_id"] == "doc-1"


def test_replace_removes_stale_documents(client: TestClient, store: FakeStore) -> None:
    client.post("/v1/index/upsert", json=index_payload("doc-1"), headers=AUTH_HEADERS)
    client.post("/v1/index/upsert", json=index_payload("doc-2"), headers=AUTH_HEADERS)

    response = client.post(
        "/v1/index/replace",
        json=index_payload("doc-1"),
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert ("template", "doc-1") in store.documents
    assert ("template", "doc-2") not in store.documents


def test_create_collection_and_switch_alias(client: TestClient, store: FakeStore) -> None:
    created = client.post(
        "/v1/admin/collections",
        json={"name": "knowledge_v3"},
        headers=AUTH_HEADERS,
    )
    switched = client.post(
        "/v1/admin/alias",
        json={"alias": "knowledge_current", "collection": "knowledge_v3"},
        headers=AUTH_HEADERS,
    )

    assert created.status_code == 200
    assert created.json()["name"] == "knowledge_v3"
    assert switched.status_code == 200
    assert store.alias == ("knowledge_current", "knowledge_v3")


def test_activate_document(client: TestClient, store: FakeStore) -> None:
    response = client.post(
        "/v1/index/activate",
        json={
            "source_type": "knowledge_material",
            "source_id": "sha-1",
            "version": "v2",
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["activated"] is True
    assert store.activated == [("knowledge_material", "sha-1", "v2")]


def test_cleanup_inactive(client: TestClient, store: FakeStore) -> None:
    response = client.post(
        "/v1/index/cleanup",
        json={"older_than_hours": 12, "source_type": "knowledge_material"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["deleted"] == 0
    assert store.cleanup_calls == [(12, "knowledge_material")]


def test_delete_document(client: TestClient, store: FakeStore) -> None:
    client.post("/v1/index/upsert", json=index_payload(), headers=AUTH_HEADERS)
    response = client.delete("/v1/index/template/doc-1", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert ("template", "doc-1") not in store.documents


def test_delete_document_uses_documents_scope(
    parameters: ApplicationParameters,
    settings: ServiceSettings,
    embedder: FakeEmbedder,
    store: FakeStore,
) -> None:
    documents_store = FakeStore()
    app = create_app(
        parameters=parameters,
        settings=settings,
        embedder=embedder,
        store=store,
        documents_store=documents_store,
    )
    with TestClient(app) as scoped_client:
        response = scoped_client.delete(
            "/v1/index/document_internal/doc-1?scope=documents",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    assert documents_store.delete_calls == [("document_internal", "doc-1")]
    assert store.delete_calls == []


def test_cleanup_inactive_uses_documents_scope(
    parameters: ApplicationParameters,
    settings: ServiceSettings,
    embedder: FakeEmbedder,
    store: FakeStore,
) -> None:
    documents_store = FakeStore()
    app = create_app(
        parameters=parameters,
        settings=settings,
        embedder=embedder,
        store=store,
        documents_store=documents_store,
    )
    with TestClient(app) as scoped_client:
        response = scoped_client.post(
            "/v1/index/cleanup",
            json={
                "older_than_hours": 12,
                "source_type": "document_internal",
                "scope": "documents",
            },
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    assert documents_store.cleanup_calls == [(12, "document_internal")]
    assert store.cleanup_calls == []


def test_configured_dimension_mismatch_fails_startup(
    parameters: ApplicationParameters,
    settings: ServiceSettings,
    embedder: FakeEmbedder,
    store: FakeStore,
) -> None:
    mismatched = parameters.model_copy(deep=True)
    mismatched.rag.embedding_dimension = 5
    app = create_app(parameters=mismatched, settings=settings, embedder=embedder, store=store)
    with pytest.raises(ConfigurationError), TestClient(app):
        pass


def test_retrieve_uses_hybrid_and_rerank(
    parameters: ApplicationParameters,
    settings: ServiceSettings,
    embedder: FakeEmbedder,
    store: FakeStore,
) -> None:
    hybrid = parameters.model_copy(deep=True)
    hybrid.rag.hybrid_enabled = True
    hybrid.rag.rerank_enabled = True
    hybrid.rag.include_parent = False
    app = create_app(
        parameters=hybrid,
        settings=settings,
        embedder=embedder,
        store=store,
        sparse_encoder=FakeSparseEncoder(),
        reranker=FakeReranker(),
    )
    with TestClient(app) as client:
        indexed = client.post(
            "/v1/index/upsert",
            json=index_payload("doc-1"),
            headers=AUTH_HEADERS,
        )
        assert indexed.status_code == 200
        response = client.post(
            "/v1/retrieve",
            json={
                "query": "исходящий документ",
                "filters": {"source_types": ["template"]},
            },
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["diagnostics"]["hybrid"] is True
    assert body["diagnostics"]["rerank"] is True
    assert body["results"][0]["source_id"] == "doc-1"
    assert body["results"][0]["score_type"] == "rerank_sigmoid"
    assert body["results"][0]["chunks"][0]["text"]


def test_index_chunks_accepts_structured_chunks(
    client: TestClient,
    store: FakeStore,
) -> None:
    payload = {
        "source_type": "knowledge_material",
        "document": {
            "source_id": "sha-1",
            "version": "2026-01-01",
            "title": "ГОСТ 2.101-2016",
            "metadata": {"doc_type": "ГОСТ", "status": "verified"},
        },
        "chunks": [
            {
                "index": 0,
                "text": "Текст пункта 4.2.1",
                "embedding_text": "Документ: ГОСТ\nПункт: 4.2.1\nТекст: Текст пункта 4.2.1",
                "section_path": ["4", "4.2"],
                "clause": "4.2.1",
                "page_start": 12,
                "parent_id": "sha-1:4.2",
            }
        ],
    }
    response = client.post("/v1/index/chunks", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["indexed_chunks"] == 1
    assert ("knowledge_material", "sha-1") in store.documents


def test_index_document_text_updates_metadata_and_scope(
    client: TestClient,
    store: FakeStore,
) -> None:
    snapshot = {
        "source_id": "doc-1",
        "family_id": "family-1",
        "version": "content-v1",
        "title": "Приказ о назначении",
        "doc_type": "Приказ",
        "doc_kind": "Внутренний",
        "status": "approved",
        "is_current": True,
        "acl_principals": ["user:1", "position:2"],
        "acl_deny_principals": [],
        "acl_version": "acl-v1",
    }
    response = client.post(
        "/v1/index/document",
        data={
            "source_type": "document_internal",
            "document": json.dumps(snapshot, ensure_ascii=False),
            "text": "1. Общие положения\n\n1.1. Настоящий приказ устанавливает порядок.",
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["indexed_chunks"] >= 1
    assert body["requires_ocr"] is False
    assert ("document_internal", "doc-1") in store.documents
    assert store.activated[-1] == ("document_internal", "doc-1", "content-v1")

    retrieved = client.post(
        "/v1/retrieve",
        json={
            "query": "порядок назначения",
            "scope": "documents",
            "filters": {
                "source_types": ["document_internal"],
                "is_current": True,
                "acl_principals": ["user:1"],
            },
        },
        headers=AUTH_HEADERS,
    )
    assert retrieved.status_code == 200
    assert retrieved.json()["diagnostics"]["scope"] == "documents"
    assert retrieved.json()["results"][0]["source_id"] == "doc-1"


def test_index_metadata_updates_existing_document(
    client: TestClient,
    store: FakeStore,
) -> None:
    snapshot = {
        "source_id": "doc-1",
        "family_id": "family-1",
        "version": "content-v1",
        "title": "Приказ",
    }
    indexed = client.post(
        "/v1/index/document",
        data={
            "source_type": "document_internal",
            "document": json.dumps(snapshot, ensure_ascii=False),
            "text": "Текст приказа.",
        },
        headers=AUTH_HEADERS,
    )
    assert indexed.status_code == 200

    response = client.post(
        "/v1/index/metadata",
        json={
            "source_type": "document_internal",
            "source_id": "doc-1",
            "version": "content-v1",
            "payload": {"active": False, "is_current": False},
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["updated"] is True
    document, _ = store.documents[("document_internal", "doc-1")]
    assert document.metadata["active"] is False
    assert document.metadata["is_current"] is False


def test_index_document_base64_accepts_file(
    client: TestClient,
    store: FakeStore,
) -> None:
    snapshot = {
        "source_id": "doc-file-1",
        "family_id": "family-file-1",
        "version": "content-v1",
        "title": "Акт обследования",
    }
    response = client.post(
        "/v1/index/document/base64",
        json={
            "source_type": "document_internal",
            "document": snapshot,
            "text": "1. Общие сведения",
            "file_base64": "0J/RgNC40LrQsNC3IDEu",
            "file_name": "act.txt",
            "mime": "text/plain",
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["indexed_chunks"] >= 1
    assert ("document_internal", "doc-file-1") in store.documents
