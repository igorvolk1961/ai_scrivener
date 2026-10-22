from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from rag_service.chunking import TextChunk
from rag_service.config import ApplicationParameters, ServiceSettings, load_parameters
from rag_service.main import create_app
from rag_service.models import SearchFilters, SearchResult
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

    async def ensure_collection(self, dimension: int) -> None:
        self.dimension = dimension

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

    async def delete(self, source_type: str, source_id: str) -> bool:
        existed = (source_type, source_id) in self.documents
        self.documents.pop((source_type, source_id), None)
        return existed

    async def search(
        self,
        vector: list[float],
        filters: SearchFilters,
        limit: int,
        min_score: float,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        for (source_type, source_id), (document, chunks) in self.documents.items():
            if filters.source_types and source_type not in filters.source_types:
                continue
            first = chunks[0]
            results.append(
                SearchResult(
                    score=1.0,
                    source_type=source_type,
                    source_id=source_id,
                    version=document.version,
                    title=document.title,
                    chunk_index=first.index,
                    text=first.text,
                    metadata=document.metadata,
                )
            )
        return results[:limit]


@pytest.fixture
def parameters() -> ApplicationParameters:
    resolved = load_parameters()
    resolved.rag.embedding_dimension = None
    return resolved


@pytest.fixture
def settings() -> ServiceSettings:
    return ServiceSettings(
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
def client(
    parameters: ApplicationParameters,
    settings: ServiceSettings,
    embedder: FakeEmbedder,
    store: FakeStore,
) -> Iterator[TestClient]:
    app = create_app(parameters=parameters, settings=settings, embedder=embedder, store=store)
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
