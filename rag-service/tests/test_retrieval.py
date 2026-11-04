from __future__ import annotations

import asyncio
from typing import Any, cast

from rag_service.config import ApplicationParameters
from rag_service.models import RetrieveRequest, SearchFilters, SearchResult
from rag_service.qdrant_store import VectorStore
from rag_service.retrieval import Retriever


class StubEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


class StubStore:
    def __init__(self, candidates: list[SearchResult]) -> None:
        self._candidates = candidates
        self.requested_limit: int | None = None

    async def search(
        self,
        vector: list[float],
        filters: SearchFilters,
        limit: int,
        min_score: float,
    ) -> list[SearchResult]:
        self.requested_limit = limit
        return self._candidates[:limit]

    async def search_hybrid(
        self,
        dense_vector: list[float],
        sparse_vector: Any,
        filters: SearchFilters,
        limit: int,
        hnsw_ef: int,
    ) -> list[SearchResult]:
        self.requested_limit = limit
        return self._candidates[:limit]

    async def fetch_parent_chunks(
        self,
        source_type: str,
        source_id: str,
        parent_id: str,
        limit: int,
    ) -> list[SearchResult]:
        return []


class StubReranker:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores

    async def score(self, query: str, documents: list[str]) -> list[float]:
        return self._scores[: len(documents)]

    async def close(self) -> None:
        return None


def _candidate(
    source_id: str,
    chunk_index: int,
    score: float,
) -> SearchResult:
    return SearchResult(
        score=score,
        source_type="knowledge_material",
        source_id=source_id,
        version="1",
        title=source_id,
        chunk_index=chunk_index,
        text=f"{source_id}-{chunk_index}",
        embedding_text=f"{source_id}-{chunk_index}",
        document_key=f"knowledge_material:{source_id}",
        metadata={},
    )


def _parameters() -> ApplicationParameters:
    from rag_service.config import load_parameters

    parameters = load_parameters()
    parameters.rag.hybrid_enabled = False
    parameters.rag.rerank_enabled = False
    parameters.rag.include_parent = False
    parameters.rag.top_k = 2
    parameters.rag.candidate_k = 10
    parameters.rag.group_size = 1
    parameters.rag.group_by_source = True
    return parameters


def test_retrieve_groups_chunks_by_source() -> None:
    candidates = [
        _candidate("doc-a", 0, 0.9),
        _candidate("doc-a", 1, 0.8),
        _candidate("doc-b", 0, 0.7),
    ]
    store = StubStore(candidates)
    retriever = Retriever(
        _parameters(),
        StubEmbedder(),
        cast(VectorStore, store),
    )

    response = asyncio.run(
        retriever.retrieve(RetrieveRequest(query="документ", filters=SearchFilters()))
    )

    assert [result.source_id for result in response.results] == ["doc-a", "doc-b"]
    assert len(response.results[0].chunks) == 1
    assert response.results[0].chunks[0].chunk_index == 0
    assert response.diagnostics["candidates"] == 3
    assert response.diagnostics["hybrid"] is False


def test_retrieve_applies_reranker_order() -> None:
    candidates = [
        _candidate("doc-a", 0, 0.9),
        _candidate("doc-b", 0, 0.1),
    ]
    parameters = _parameters()
    parameters.rag.rerank_enabled = True
    retriever = Retriever(
        parameters,
        StubEmbedder(),
        cast(VectorStore, StubStore(candidates)),
        reranker=StubReranker([0.0, 5.0]),
    )

    response = asyncio.run(
        retriever.retrieve(
            RetrieveRequest(
                query="документ",
                filters=SearchFilters(),
                rerank=True,
            )
        )
    )

    assert response.results[0].source_id == "doc-b"
    assert response.results[0].score_type == "rerank_sigmoid"
    assert response.diagnostics["rerank"] is True
