from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from rag_service.chunking import TextChunk
from rag_service.config import ApplicationParameters, ServiceSettings, load_parameters
from rag_service.main import create_app
from rag_service.models import IndexChunk, SearchFilters, SearchResult
from rag_service.qdrant_store import IndexedDocument


class FakeEmbedder:
    def __init__(self, dimension: int = 3) -> None:
        self._dimension = dimension
        self.closed = False

    @property
    def dimension(self) -> int | None:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    async def probe_dimension(self) -> int:
        return self._dimension

    async def close(self) -> None:
        self.closed = True


class FakeStore:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, str], tuple[IndexedDocument, list[TextChunk]]] = {}
        self.dimension: int | None = None
        self.closed = False
        self.activated: list[tuple[str, str, str]] = []
        self.cleanup_calls: list[tuple[float, str | None]] = []
        self.alias: tuple[str, str] | None = None

    async def ensure_collection(self, dimension: int) -> None:
        self.dimension = dimension

    async def create_collection(self, collection_name: str, dimension: int) -> None:
        self.dimension = dimension

    async def switch_alias(self, alias: str, collection_name: str) -> None:
        self.alias = (alias, collection_name)

    async def collection_state(self) -> dict[str, Any]:
        return {
            "alias": "test_collection",
            "alias_target": "test_collection_v1",
            "collections": ["test_collection_v1"],
        }

    async def health(self) -> bool:
        return True

    async def close(self) -> None:
        self.closed = True

    async def upsert(
        self,
        source_type: str,
        document: IndexedDocument,
        chunks: list[TextChunk],
        vectors: list[list[float]],
        sparse_vectors: list[Any] | None = None,
    ) -> int:
        if len(chunks) != len(vectors):
            raise AssertionError("chunks and vectors mismatch")
        self.documents[(source_type, document.source_id)] = (document, chunks)
        return len(chunks)

    async def replace(
        self,
        source_type: str,
        documents: list[IndexedDocument],
        chunks: list[list[TextChunk]],
        vectors: list[list[list[float]]],
        sparse_vectors: list[list[Any] | None] | None = None,
    ) -> int:
        self.documents = {
            key: value for key, value in self.documents.items() if key[0] != source_type
        }
        total = 0
        for document, document_chunks, document_vectors in zip(
            documents, chunks, vectors, strict=True
        ):
            total += await self.upsert(source_type, document, document_chunks, document_vectors)
        return total

    async def upsert_chunks(
        self,
        source_type: str,
        document: IndexedDocument,
        chunks: list[IndexChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[Any] | None = None,
        replace_existing: bool = True,
        active: bool = True,
        collection_name: str | None = None,
    ) -> int:
        if len(chunks) != len(dense_vectors):
            raise AssertionError("chunks and vectors mismatch")
        text_chunks = [TextChunk(index=chunk.index, text=chunk.text) for chunk in chunks]
        self.documents[(source_type, document.source_id)] = (document, text_chunks)
        return len(chunks)

    async def activate_document(
        self,
        source_type: str,
        source_id: str,
        version: str,
        collection_name: str | None = None,
        keep_inactive: bool = False,
    ) -> bool:
        self.activated.append((source_type, source_id, version))
        return True

    async def update_payload(
        self,
        source_type: str,
        source_id: str,
        payload: dict[str, Any],
        version: str | None = None,
        collection_name: str | None = None,
    ) -> bool:
        key = (source_type, source_id)
        if key not in self.documents:
            return False
        document, _ = self.documents[key]
        document.metadata.update(payload)
        return True

    async def cleanup_inactive(
        self,
        older_than_hours: float,
        source_type: str | None = None,
    ) -> int:
        self.cleanup_calls.append((older_than_hours, source_type))
        return 0

    async def delete(
        self,
        source_type: str,
        source_id: str,
        collection_name: str | None = None,
    ) -> bool:
        existed = (source_type, source_id) in self.documents
        self.documents.pop((source_type, source_id), None)
        return existed

    def _results(
        self,
        filters: SearchFilters,
        limit: int,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        for (source_type, source_id), (document, chunks) in self.documents.items():
            if filters.source_types and source_type not in filters.source_types:
                continue
            for chunk in chunks[:1]:
                results.append(
                    SearchResult(
                        score=1.0,
                        source_type=source_type,
                        source_id=source_id,
                        version=document.version,
                        title=document.title,
                        chunk_index=chunk.index,
                        text=chunk.text,
                        embedding_text=chunk.text,
                        document_key=f"{source_type}:{source_id}",
                        metadata=document.metadata,
                    )
                )
        return results[:limit]

    async def search(
        self,
        vector: list[float],
        filters: SearchFilters,
        limit: int,
        min_score: float,
    ) -> list[SearchResult]:
        return self._results(filters, limit)

    async def search_hybrid(
        self,
        dense_vector: list[float],
        sparse_vector: Any,
        filters: SearchFilters,
        limit: int,
        hnsw_ef: int,
    ) -> list[SearchResult]:
        return self._results(filters, limit)

    async def fetch_parent_chunks(
        self,
        source_type: str,
        source_id: str,
        parent_id: str,
        limit: int,
    ) -> list[SearchResult]:
        return []


class FakeSparseEncoder:
    def __init__(self) -> None:
        self.closed = False

    async def embed_documents(self, texts: list[str]) -> list[Any]:
        return [object() for _ in texts]

    async def embed_query(self, text: str) -> Any:
        return object()

    async def close(self) -> None:
        self.closed = True


class FakeReranker:
    def __init__(self) -> None:
        self.closed = False

    async def score(self, query: str, documents: list[str]) -> list[float]:
        return [float(len(documents) - index) for index, _ in enumerate(documents)]

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def parameters() -> ApplicationParameters:
    resolved = load_parameters()
    resolved.rag.embedding_dimension = None
    resolved.rag.hybrid_enabled = False
    resolved.rag.rerank_enabled = False
    resolved.rag.include_parent = False
    return resolved


@pytest.fixture
def settings() -> ServiceSettings:
    return ServiceSettings(  # type: ignore[call-arg]
        _env_file=None,
        service_token=SecretStr("test-token"),
        qdrant_url="http://qdrant:6333",
        qdrant_collection="test_collection",
        gigachat_oauth_url="https://oauth.example/token",
        gigachat_api_url="https://embeddings.example/v1",
        gigachat_client_id="client",
        gigachat_client_secret=SecretStr("secret"),
        gigachat_scope="scope",
        gigachat_model="model",
    )


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def sparse_encoder() -> FakeSparseEncoder:
    return FakeSparseEncoder()


@pytest.fixture
def reranker() -> FakeReranker:
    return FakeReranker()


@pytest.fixture
def client(
    parameters: ApplicationParameters,
    settings: ServiceSettings,
    embedder: FakeEmbedder,
    store: FakeStore,
) -> Iterator[TestClient]:
    app = create_app(
        parameters=parameters,
        settings=settings,
        embedder=embedder,
        store=store,
        documents_store=store,
    )
    with TestClient(app) as test_client:
        yield test_client


AUTH_HEADERS = {"X-Service-Token": "test-token"}


def index_payload(source_id: str = "doc-1") -> dict[str, Any]:
    return {
        "source_type": "template",
        "items": [
            {
                "source_id": source_id,
                "version": "1",
                "title": "Исходящий документ",
                "text": "Текст шаблона для проверки индексации и поиска.",
                "metadata": {"doc_type": "ИсходящийДокумент"},
            }
        ],
    }
