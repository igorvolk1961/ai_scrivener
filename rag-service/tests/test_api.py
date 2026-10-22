from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_service.config import ApplicationParameters, ConfigurationError, ServiceSettings
from rag_service.main import create_app

from .conftest import AUTH_HEADERS, FakeEmbedder, FakeStore, index_payload


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["qdrant"] is True


def test_search_requires_token(client: TestClient) -> None:
    response = client.post("/v1/search", json={"query": "документ"})
    assert response.status_code == 401


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


def test_delete_document(client: TestClient, store: FakeStore) -> None:
    client.post("/v1/index/upsert", json=index_payload(), headers=AUTH_HEADERS)
    response = client.delete("/v1/index/template/doc-1", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert ("template", "doc-1") not in store.documents


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
