from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from qdrant_client import AsyncQdrantClient, models

from rag_service.chunking import TextChunk
from rag_service.models import SearchFilters, SearchResult

logger = logging.getLogger(__name__)


class VectorStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class IndexedDocument:
    source_id: str
    version: str
    title: str
    metadata: dict[str, Any]


class VectorStore(Protocol):
    async def ensure_collection(self, dimension: int) -> None: ...

    async def health(self) -> bool: ...

    async def close(self) -> None: ...

    async def upsert(
        self,
        source_type: str,
        document: IndexedDocument,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> int: ...

    async def replace(
        self,
        source_type: str,
        documents: list[IndexedDocument],
        chunks: list[list[TextChunk]],
        vectors: list[list[list[float]]],
    ) -> int: ...

    async def delete(self, source_type: str, source_id: str) -> bool: ...

    async def search(
        self,
        vector: list[float],
        filters: SearchFilters,
        limit: int,
        min_score: float,
    ) -> list[SearchResult]: ...


def point_id(source_type: str, source_id: str, version: str, chunk_index: int) -> str:
    key = f"ai-scrivener:{source_type}:{source_id}:{version}:{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _source_filter(source_type: str, source_id: str | None = None) -> models.Filter:
    must: list[models.Condition] = [
        models.FieldCondition(key="source_type", match=models.MatchValue(value=source_type))
    ]
    if source_id is not None:
        must.append(
            models.FieldCondition(key="source_id", match=models.MatchValue(value=source_id))
        )
    return models.Filter(must=must)


class QdrantStore:
    def __init__(
        self,
        url: str,
        collection: str,
        api_key: str | None = None,
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self._client = client or AsyncQdrantClient(url=url, api_key=api_key)
        self._collection = collection

    async def close(self) -> None:
        await self._client.close()

    async def health(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:
            logger.exception("qdrant health check failed")
            return False

    async def ensure_collection(self, dimension: int) -> None:
        exists = await self._client.collection_exists(self._collection)
        if exists:
            info = await self._client.get_collection(self._collection)
            vectors = info.config.params.vectors
            size = vectors.size if hasattr(vectors, "size") else vectors["size"]
            if size != dimension:
                raise VectorStoreError(
                    f"collection {self._collection} has dimension {size}, expected {dimension}"
                )
            return
        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        )
        for field_name, schema in (
            ("source_type", models.PayloadSchemaType.KEYWORD),
            ("source_id", models.PayloadSchemaType.KEYWORD),
            ("doc_type", models.PayloadSchemaType.KEYWORD),
            ("position_ids", models.PayloadSchemaType.KEYWORD),
            ("active", models.PayloadSchemaType.BOOL),
            ("metadata.folders", models.PayloadSchemaType.KEYWORD),
            ("metadata.employees", models.PayloadSchemaType.KEYWORD),
            ("metadata.purposes", models.PayloadSchemaType.KEYWORD),
        ):
            await self._client.create_payload_index(
                collection_name=self._collection,
                field_name=field_name,
                field_schema=schema,
            )

    async def _delete_filter(self, filter_: models.Filter) -> None:
        await self._client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(filter=filter_),
            wait=True,
        )

    async def delete(self, source_type: str, source_id: str) -> bool:
        await self._delete_filter(_source_filter(source_type, source_id))
        return True

    async def upsert(
        self,
        source_type: str,
        document: IndexedDocument,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> int:
        if len(chunks) != len(vectors):
            raise VectorStoreError("chunks and vectors count mismatch")
        await self.delete(source_type, document.source_id)
        points = [
            models.PointStruct(
                id=point_id(source_type, document.source_id, document.version, chunk.index),
                vector=vector,
                payload={
                    "source_type": source_type,
                    "source_id": document.source_id,
                    "version": document.version,
                    "title": document.title,
                    "chunk_index": chunk.index,
                    "text": chunk.text,
                    "active": True,
                    "doc_type": document.metadata.get("doc_type"),
                    "position_ids": document.metadata.get("position_ids", []),
                    "metadata": document.metadata,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        if points:
            await self._client.upsert(
                collection_name=self._collection,
                points=points,
                wait=True,
            )
        return len(points)

    async def replace(
        self,
        source_type: str,
        documents: list[IndexedDocument],
        chunks: list[list[TextChunk]],
        vectors: list[list[list[float]]],
    ) -> int:
        if not (len(documents) == len(chunks) == len(vectors)):
            raise VectorStoreError("documents, chunks and vectors count mismatch")
        await self._delete_filter(_source_filter(source_type))
        total = 0
        for document, document_chunks, document_vectors in zip(
            documents, chunks, vectors, strict=True
        ):
            if len(document_chunks) != len(document_vectors):
                raise VectorStoreError("chunks and vectors count mismatch")
            total += await self.upsert(source_type, document, document_chunks, document_vectors)
        return total

    async def search(
        self,
        vector: list[float],
        filters: SearchFilters,
        limit: int,
        min_score: float,
    ) -> list[SearchResult]:
        must: list[models.Condition] = [
            models.FieldCondition(key="active", match=models.MatchValue(value=filters.active))
        ]
        if filters.source_types:
            must.append(
                models.FieldCondition(
                    key="source_type",
                    match=models.MatchAny(any=filters.source_types),
                )
            )
        if filters.doc_types:
            must.append(
                models.FieldCondition(
                    key="doc_type",
                    match=models.MatchAny(any=filters.doc_types),
                )
            )
        if filters.position_ids:
            must.append(
                models.FieldCondition(
                    key="position_ids",
                    match=models.MatchAny(any=filters.position_ids),
                )
            )
        for field_name, values in (
            ("metadata.folders", filters.folders),
            ("metadata.employees", filters.employees),
            ("metadata.purposes", filters.purposes),
        ):
            if values:
                must.append(
                    models.FieldCondition(
                        key=field_name,
                        match=models.MatchAny(any=values),
                    )
                )
        response = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            query_filter=models.Filter(must=must),
            limit=limit,
            score_threshold=min_score,
            with_payload=True,
            with_vectors=False,
        )
        results: list[SearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                SearchResult(
                    score=float(point.score),
                    source_type=str(payload.get("source_type", "")),
                    source_id=str(payload.get("source_id", "")),
                    version=str(payload.get("version", "")),
                    title=str(payload.get("title", "")),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    text=str(payload.get("text", "")),
                    metadata=dict(payload.get("metadata", {})),
                )
            )
        return results
