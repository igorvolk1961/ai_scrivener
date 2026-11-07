from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict
from typing import Protocol

from rag_service.config import ApplicationParameters
from rag_service.models import (
    RetrieveRequest,
    RetrieveResponse,
    RetrieveResult,
    SearchResult,
)
from rag_service.qdrant_store import VectorStore, VectorStoreError
from rag_service.rerank import Reranker
from rag_service.sparse import SparseEncoder


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _chunk_key(chunk: SearchResult) -> tuple[str, str, int]:
    return (chunk.source_type, chunk.source_id, chunk.chunk_index)


def _trim_to_token_budget(
    chunks: list[SearchResult],
    max_tokens: int,
) -> list[SearchResult]:
    if max_tokens <= 0:
        return []
    selected: list[SearchResult] = []
    used = 0
    for chunk in chunks:
        estimated = max(1, len(chunk.text) // 4)
        if selected and used + estimated > max_tokens:
            break
        selected.append(chunk)
        used += estimated
    return selected


class Retriever:
    def __init__(
        self,
        parameters: ApplicationParameters,
        embedder: Embedder,
        store: VectorStore,
        sparse: SparseEncoder | None = None,
        reranker: Reranker | None = None,
        documents_store: VectorStore | None = None,
    ) -> None:
        self._parameters = parameters
        self._embedder = embedder
        self._store = store
        self._documents_store = documents_store
        self._sparse = sparse
        self._reranker = reranker

    async def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        rag = self._parameters.rag
        store = self._store
        if request.scope == "documents":
            if self._documents_store is None:
                raise VectorStoreError("documents collection is not configured")
            if not request.filters.acl_principals:
                return RetrieveResponse(
                    query=request.query,
                    results=[],
                    diagnostics={
                        "scope": "documents",
                        "acl_principals_required": True,
                    },
                )
            store = self._documents_store
        query = request.query[: rag.query_max_chars]
        candidate_k = min(
            request.candidate_k or rag.candidate_k,
            max(rag.candidate_k, rag.top_k),
        )
        top_k = min(request.top_k or rag.top_k, candidate_k)
        group_size = request.group_size or rag.group_size
        sparse = self._sparse
        reranker = self._reranker
        use_hybrid = rag.hybrid_enabled and sparse is not None
        use_rerank = (
            request.rerank if request.rerank is not None else rag.rerank_enabled
        ) and reranker is not None

        started = time.perf_counter()
        dense_vector = (await self._embedder.embed([query]))[0]
        if use_hybrid and sparse is not None:
            sparse_query = await sparse.embed_query(query)
            candidates = await store.search_hybrid(
                dense_vector,
                sparse_query,
                request.filters,
                candidate_k,
                rag.hnsw_ef,
            )
        else:
            candidates = await store.search(
                dense_vector,
                request.filters,
                candidate_k,
                rag.search_min_score,
            )
        retrieval_ms = (time.perf_counter() - started) * 1000

        rerank_ms = 0.0
        rerank_succeeded = False
        rerank_error = ""
        if use_rerank and reranker is not None and candidates:
            rerank_started = time.perf_counter()
            rerank_limit = max(1, rag.rerank_candidate_limit)
            head = candidates[:rerank_limit]
            tail = candidates[rerank_limit:]
            documents = [candidate.embedding_text or candidate.text for candidate in head]
            try:
                scores = await asyncio.wait_for(
                    reranker.score(query, documents),
                    timeout=rag.rerank_timeout_seconds,
                )
            except TimeoutError:
                rerank_error = f"timeout after {rag.rerank_timeout_seconds:g}s"
                scores = None
            except Exception as error:
                rerank_error = str(error)[:200]
                scores = None
            if scores is not None:
                if len(scores) != len(head):
                    rerank_error = "reranker returned unexpected score count"
                else:
                    for candidate, raw_score in zip(head, scores, strict=True):
                        candidate.rerank_score = raw_score
                        candidate.score = _sigmoid(raw_score)
                        candidate.score_type = "rerank_sigmoid"
                    head.sort(key=lambda candidate: candidate.score, reverse=True)
                    candidates = [*head, *tail]
                    rerank_succeeded = True
                    if rag.search_min_score > 0:
                        candidates = [
                            candidate
                            for candidate in candidates
                            if candidate.score >= rag.search_min_score
                        ]
            rerank_ms = (time.perf_counter() - rerank_started) * 1000

        group_by_source = (
            request.group_by_source if request.group_by_source is not None else rag.group_by_source
        )
        include_parent = (
            request.include_parent if request.include_parent is not None else rag.include_parent
        )

        if group_by_source:
            results = self._group_by_source(
                candidates,
                top_k=top_k,
                group_size=group_size,
            )
        else:
            results = [
                RetrieveResult(
                    source_type=candidate.source_type,
                    source_id=candidate.source_id,
                    document_key=candidate.document_key
                    or f"{candidate.source_type}:{candidate.source_id}",
                    title=candidate.title,
                    score=candidate.score,
                    score_type=candidate.score_type,
                    metadata=candidate.metadata,
                    chunks=[candidate],
                )
                for candidate in candidates[:top_k]
            ]

        if include_parent:
            results = await self._with_parent_chunks(
                results,
                rag.context_max_tokens,
                store,
            )

        return RetrieveResponse(
            query=query,
            results=results,
            diagnostics={
                "scope": request.scope,
                "candidates": len(candidates),
                "returned": len(results),
                "hybrid": use_hybrid,
                "rerank": rerank_succeeded,
                "rerank_requested": use_rerank,
                "rerank_error": rerank_error,
                "retrieval_ms": round(retrieval_ms, 2),
                "rerank_ms": round(rerank_ms, 2),
            },
        )

    @staticmethod
    def _group_by_source(
        candidates: list[SearchResult],
        top_k: int,
        group_size: int,
    ) -> list[RetrieveResult]:
        groups: dict[str, list[SearchResult]] = defaultdict(list)
        for candidate in candidates:
            key = candidate.document_key or f"{candidate.source_type}:{candidate.source_id}"
            groups[key].append(candidate)

        ordered = sorted(
            groups.items(),
            key=lambda item: max(chunk.score for chunk in item[1]),
            reverse=True,
        )
        results: list[RetrieveResult] = []
        for key, chunks in ordered[:top_k]:
            ordered_chunks = sorted(
                chunks,
                key=lambda chunk: chunk.score,
                reverse=True,
            )[:group_size]
            best = ordered_chunks[0]
            results.append(
                RetrieveResult(
                    source_type=best.source_type,
                    source_id=best.source_id,
                    document_key=key,
                    title=best.title,
                    score=best.score,
                    score_type=best.score_type,
                    metadata=best.metadata,
                    chunks=ordered_chunks,
                )
            )
        return results

    async def _with_parent_chunks(
        self,
        results: list[RetrieveResult],
        max_tokens: int,
        store: VectorStore,
    ) -> list[RetrieveResult]:
        expanded: list[RetrieveResult] = []
        cache: dict[tuple[str, str, str], list[SearchResult]] = {}
        for result in results:
            merged: dict[tuple[str, str, int], SearchResult] = {
                _chunk_key(chunk): chunk for chunk in result.chunks
            }
            for chunk in result.chunks:
                if not chunk.parent_id:
                    continue
                cache_key = (chunk.source_type, chunk.source_id, chunk.parent_id)
                if cache_key not in cache:
                    cache[cache_key] = await store.fetch_parent_chunks(
                        chunk.source_type,
                        chunk.source_id,
                        chunk.parent_id,
                        self._parameters.rag.parent_chunk_limit,
                    )
                for parent_chunk in cache[cache_key]:
                    merged.setdefault(_chunk_key(parent_chunk), parent_chunk)
            chunks = sorted(merged.values(), key=lambda item: item.chunk_index)
            expanded.append(
                RetrieveResult(
                    source_type=result.source_type,
                    source_id=result.source_id,
                    document_key=result.document_key,
                    title=result.title,
                    score=result.score,
                    score_type=result.score_type,
                    metadata=result.metadata,
                    chunks=_trim_to_token_budget(chunks, max_tokens),
                )
            )
        return expanded
