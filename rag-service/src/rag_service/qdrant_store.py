from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from qdrant_client import AsyncQdrantClient, models

from rag_service.chunking import TextChunk
from rag_service.models import IndexChunk, SearchFilters, SearchResult

logger = logging.getLogger(__name__)

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"
DATE_ONLY_LENGTH = len("YYYY-MM-DD")
DEFAULT_QDRANT_TIMEOUT = 60


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

    async def create_collection(self, collection_name: str, dimension: int) -> None: ...

    async def switch_alias(self, alias: str, collection_name: str) -> None: ...

    async def collection_state(self) -> dict[str, Any]: ...

    async def health(self) -> bool: ...

    async def close(self) -> None: ...

    async def upsert(
        self,
        source_type: str,
        document: IndexedDocument,
        chunks: list[TextChunk],
        vectors: list[list[float]],
        sparse_vectors: list[models.SparseVector] | None = None,
    ) -> int: ...

    async def replace(
        self,
        source_type: str,
        documents: list[IndexedDocument],
        chunks: list[list[TextChunk]],
        vectors: list[list[list[float]]],
        sparse_vectors: list[list[models.SparseVector] | None] | None = None,
    ) -> int: ...

    async def upsert_chunks(
        self,
        source_type: str,
        document: IndexedDocument,
        chunks: list[IndexChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[models.SparseVector] | None = None,
        replace_existing: bool = True,
        active: bool = True,
        collection_name: str | None = None,
    ) -> int: ...

    async def activate_document(
        self,
        source_type: str,
        source_id: str,
        version: str,
        collection_name: str | None = None,
        keep_inactive: bool = False,
    ) -> bool: ...

    async def update_payload(
        self,
        source_type: str,
        source_id: str,
        payload: dict[str, Any],
        version: str | None = None,
        collection_name: str | None = None,
    ) -> bool: ...

    async def cleanup_inactive(
        self,
        older_than_hours: float,
        source_type: str | None = None,
    ) -> int: ...

    async def delete(
        self,
        source_type: str,
        source_id: str,
        collection_name: str | None = None,
    ) -> bool: ...

    async def search(
        self,
        vector: list[float],
        filters: SearchFilters,
        limit: int,
        min_score: float,
    ) -> list[SearchResult]: ...

    async def search_hybrid(
        self,
        dense_vector: list[float],
        sparse_vector: models.SparseVector,
        filters: SearchFilters,
        limit: int,
        hnsw_ef: int,
    ) -> list[SearchResult]: ...

    async def fetch_parent_chunks(
        self,
        source_type: str,
        source_id: str,
        parent_id: str,
        limit: int,
    ) -> list[SearchResult]: ...

    async def fetch_source_chunks(
        self,
        source_type: str,
        source_id: str,
        limit: int = 10000,
        collection_name: str | None = None,
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


def _filter_conditions(filters: SearchFilters) -> list[models.Condition]:
    conditions: list[models.Condition] = []
    if filters.active is not None:
        conditions.append(
            models.FieldCondition(key="active", match=models.MatchValue(value=filters.active))
        )
    if filters.is_current is not None:
        conditions.append(
            models.FieldCondition(
                key="is_current",
                match=models.MatchValue(value=filters.is_current),
            )
        )
    for field_name, values in (
        ("source_type", filters.source_types),
        ("doc_type", filters.doc_types),
        ("status", filters.statuses),
        ("authority", filters.authorities),
        ("document_key", filters.document_keys),
        ("family_id", filters.family_ids),
        ("position_ids", filters.position_ids),
        ("metadata.folders", filters.folders),
        ("metadata.employees", filters.employees),
        ("metadata.purposes", filters.purposes),
        ("acl_principals", filters.acl_principals),
    ):
        if values:
            conditions.append(
                models.FieldCondition(key=field_name, match=models.MatchAny(any=values))
            )
    return conditions


def _filter_must_not(filters: SearchFilters) -> list[models.Condition]:
    principals = [*filters.acl_principals, *filters.acl_deny_principals]
    if not principals:
        return []
    return [
        models.FieldCondition(
            key="acl_deny_principals",
            match=models.MatchAny(any=principals),
        )
    ]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _rfc3339(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if len(value) == DATE_ONLY_LENGTH and value[4] == "-" and value[7] == "-":
        return f"{value}T00:00:00Z"
    return value


def _payload_to_result(point: object, score_type: str) -> SearchResult:
    payload = getattr(point, "payload", None) or {}
    source_type = str(payload.get("source_type", ""))
    source_id = str(payload.get("source_id", ""))
    return SearchResult(
        score=float(getattr(point, "score", 0.0)),
        source_type=source_type,
        source_id=source_id,
        version=str(payload.get("version", "")),
        title=str(payload.get("title", "")),
        chunk_index=int(payload.get("chunk_index", 0)),
        text=str(payload.get("text", "")),
        metadata=dict(payload.get("metadata", {})),
        embedding_text=str(payload.get("embedding_text", "")),
        document_key=str(payload.get("document_key", f"{source_type}:{source_id}")),
        family_id=str(payload.get("family_id", "")),
        is_current=payload.get("is_current"),
        section_path=_string_list(payload.get("section_path")),
        section_text=str(payload.get("section_text", "")),
        clause=str(payload.get("clause", "")),
        page_start=payload.get("page_start"),
        page_end=payload.get("page_end"),
        kind=str(payload.get("kind", "text")),
        parent_id=payload.get("parent_id"),
        char_start=payload.get("char_start"),
        char_end=payload.get("char_end"),
        score_type=score_type,
    )


class QdrantStore:
    def __init__(
        self,
        url: str,
        collection: str,
        api_key: str | None = None,
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self._client = client or AsyncQdrantClient(
            url=url,
            api_key=api_key,
            timeout=DEFAULT_QDRANT_TIMEOUT,
        )
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

    async def _alias_target(self, alias: str | None = None) -> str | None:
        aliases = await self._client.get_aliases()
        items = getattr(aliases, "aliases", None)
        if not isinstance(items, list):
            return None
        name = alias or self._collection
        for item in items:
            if item.alias_name == name:
                return str(item.collection_name)
        return None

    async def collection_state(self) -> dict[str, Any]:
        target = await self._alias_target()
        collections = await self._client.get_collections()
        return {
            "alias": self._collection,
            "alias_target": target,
            "collections": sorted(item.name for item in collections.collections),
        }

    async def ensure_collection(self, dimension: int) -> None:
        target = await self._alias_target()
        if target is None:
            if await self._client.collection_exists(self._collection):
                target = self._collection
            else:
                target = f"{self._collection}_v1_{int(datetime.now(UTC).timestamp())}"
                await self.create_collection(target, dimension)
                await self.switch_alias(self._collection, target)
        info = await self._client.get_collection(target)
        vectors = info.config.params.vectors
        if vectors is None:
            raise VectorStoreError(f"collection {target} has no vector configuration")
        if isinstance(vectors, dict):
            dense = vectors.get(DENSE_VECTOR)
            if dense is None:
                raise VectorStoreError(f"collection {target} has no named {DENSE_VECTOR} vector")
            size = dense.size
        else:
            size = vectors.size
        if size != dimension:
            raise VectorStoreError(
                f"collection {target} has dimension {size}, expected {dimension}"
            )

    async def create_collection(self, collection_name: str, dimension: int) -> None:
        await self._client.create_collection(
            collection_name=collection_name,
            vectors_config={
                DENSE_VECTOR: models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        for field_name, schema in (
            ("source_type", models.PayloadSchemaType.KEYWORD),
            ("source_id", models.PayloadSchemaType.KEYWORD),
            ("document_key", models.PayloadSchemaType.KEYWORD),
            ("family_id", models.PayloadSchemaType.KEYWORD),
            ("doc_type", models.PayloadSchemaType.KEYWORD),
            ("doc_kind", models.PayloadSchemaType.KEYWORD),
            ("registration_number", models.PayloadSchemaType.KEYWORD),
            ("status", models.PayloadSchemaType.KEYWORD),
            ("authority", models.PayloadSchemaType.KEYWORD),
            ("position_ids", models.PayloadSchemaType.KEYWORD),
            ("parent_id", models.PayloadSchemaType.KEYWORD),
            ("kind", models.PayloadSchemaType.KEYWORD),
            ("acl_principals", models.PayloadSchemaType.KEYWORD),
            ("acl_deny_principals", models.PayloadSchemaType.KEYWORD),
            ("active", models.PayloadSchemaType.BOOL),
            ("is_current", models.PayloadSchemaType.BOOL),
            ("page_start", models.PayloadSchemaType.INTEGER),
            ("published_at", models.PayloadSchemaType.DATETIME),
            ("document_date", models.PayloadSchemaType.DATETIME),
            ("approved_at", models.PayloadSchemaType.DATETIME),
            ("effective_from", models.PayloadSchemaType.DATETIME),
            ("created_at", models.PayloadSchemaType.DATETIME),
            ("metadata.folders", models.PayloadSchemaType.KEYWORD),
            ("metadata.employees", models.PayloadSchemaType.KEYWORD),
            ("metadata.purposes", models.PayloadSchemaType.KEYWORD),
        ):
            await self._client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema,
            )

    async def switch_alias(self, alias: str, collection_name: str) -> None:
        aliases = await self._client.get_aliases()
        operations: list[models.AliasOperations] = []
        if any(item.alias_name == alias for item in aliases.aliases):
            operations.append(
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))
            )
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=collection_name,
                    alias_name=alias,
                )
            )
        )
        await self._client.update_collection_aliases(change_aliases_operations=operations)

    async def _delete_filter(
        self,
        filter_: models.Filter,
        collection_name: str | None = None,
    ) -> None:
        await self._client.delete(
            collection_name=collection_name or self._collection,
            points_selector=models.FilterSelector(filter=filter_),
            wait=True,
        )

    async def delete(
        self,
        source_type: str,
        source_id: str,
        collection_name: str | None = None,
    ) -> bool:
        await self._delete_filter(
            _source_filter(source_type, source_id),
            collection_name,
        )
        return True

    def _base_payload(
        self,
        source_type: str,
        document: IndexedDocument,
        *,
        chunk_index: int,
        text: str,
        embedding_text: str,
        section_path: list[str] | None = None,
        section_text: str = "",
        clause: str = "",
        page_start: int | None = None,
        page_end: int | None = None,
        kind: str = "text",
        parent_id: str | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
        metadata: dict[str, Any] | None = None,
        active: bool = True,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        merged_metadata = {**document.metadata, **(metadata or {})}
        family_id = str(merged_metadata.get("family_id", "") or "")
        document_key = (
            f"{source_type}:{family_id}" if family_id else f"{source_type}:{document.source_id}"
        )
        return {
            "source_type": source_type,
            "source_id": document.source_id,
            "version": document.version,
            "document_key": document_key,
            "family_id": family_id,
            "title": document.title,
            "chunk_index": chunk_index,
            "text": text,
            "embedding_text": embedding_text,
            "section_path": section_path or [],
            "section_text": section_text,
            "clause": clause,
            "page_start": page_start,
            "page_end": page_end,
            "kind": kind,
            "parent_id": parent_id,
            "char_start": char_start,
            "char_end": char_end,
            "active": active,
            "is_current": bool(merged_metadata.get("is_current", True)),
            "created_at": created_at or datetime.now(UTC).isoformat(),
            "doc_type": merged_metadata.get("doc_type"),
            "doc_kind": merged_metadata.get("doc_kind"),
            "registration_number": merged_metadata.get("registration_number"),
            "document_date": _rfc3339(merged_metadata.get("document_date")),
            "approved_at": _rfc3339(merged_metadata.get("approved_at")),
            "status": merged_metadata.get("status"),
            "authority": merged_metadata.get("authority"),
            "published_at": _rfc3339(merged_metadata.get("published_at")),
            "effective_from": _rfc3339(merged_metadata.get("effective_from")),
            "position_ids": merged_metadata.get("position_ids", []),
            "acl_principals": merged_metadata.get("acl_principals", []),
            "acl_deny_principals": merged_metadata.get("acl_deny_principals", []),
            "acl_version": merged_metadata.get("acl_version", ""),
            "content_hash": merged_metadata.get("content_hash", ""),
            "file_hash": merged_metadata.get("file_hash", ""),
            "superseded_by": merged_metadata.get("superseded_by"),
            "superseded_at": _rfc3339(merged_metadata.get("superseded_at")),
            "metadata": merged_metadata,
        }

    async def upsert(
        self,
        source_type: str,
        document: IndexedDocument,
        chunks: list[TextChunk],
        vectors: list[list[float]],
        sparse_vectors: list[models.SparseVector] | None = None,
    ) -> int:
        if len(chunks) != len(vectors):
            raise VectorStoreError("chunks and vectors count mismatch")
        if sparse_vectors is not None and len(chunks) != len(sparse_vectors):
            raise VectorStoreError("chunks and sparse vectors count mismatch")
        await self.delete(source_type, document.source_id)
        points = []
        for position, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            point_vector: dict[str, Any] = {DENSE_VECTOR: vector}
            if sparse_vectors is not None:
                point_vector[SPARSE_VECTOR] = sparse_vectors[position]
            points.append(
                models.PointStruct(
                    id=point_id(
                        source_type,
                        document.source_id,
                        document.version,
                        chunk.index,
                    ),
                    vector=point_vector,
                    payload=self._base_payload(
                        source_type,
                        document,
                        chunk_index=chunk.index,
                        text=chunk.text,
                        embedding_text=chunk.text,
                    ),
                )
            )
        if points:
            await self._client.upsert(
                collection_name=self._collection,
                points=points,
                wait=True,
            )
        return len(points)

    async def upsert_chunks(
        self,
        source_type: str,
        document: IndexedDocument,
        chunks: list[IndexChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[models.SparseVector] | None = None,
        replace_existing: bool = True,
        active: bool = True,
        collection_name: str | None = None,
    ) -> int:
        if len(chunks) != len(dense_vectors):
            raise VectorStoreError("chunks and dense vectors count mismatch")
        if sparse_vectors is not None and len(chunks) != len(sparse_vectors):
            raise VectorStoreError("chunks and sparse vectors count mismatch")
        if replace_existing:
            await self.delete(source_type, document.source_id, collection_name)
        points = []
        for position, (chunk, vector) in enumerate(zip(chunks, dense_vectors, strict=True)):
            point_vector: dict[str, Any] = {DENSE_VECTOR: vector}
            if sparse_vectors is not None:
                point_vector[SPARSE_VECTOR] = sparse_vectors[position]
            points.append(
                models.PointStruct(
                    id=point_id(
                        source_type,
                        document.source_id,
                        document.version,
                        chunk.index,
                    ),
                    vector=point_vector,
                    payload=self._base_payload(
                        source_type,
                        document,
                        chunk_index=chunk.index,
                        text=chunk.text,
                        embedding_text=chunk.embedding_text or chunk.text,
                        section_path=chunk.section_path,
                        section_text=chunk.section_text,
                        clause=chunk.clause,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        kind=chunk.kind,
                        parent_id=chunk.parent_id,
                        char_start=chunk.char_start,
                        char_end=chunk.char_end,
                        metadata=chunk.metadata,
                        active=active,
                    ),
                )
            )
        if points:
            await self._client.upsert(
                collection_name=collection_name or self._collection,
                points=points,
                wait=True,
            )
        return len(points)

    async def activate_document(
        self,
        source_type: str,
        source_id: str,
        version: str,
        collection_name: str | None = None,
        keep_inactive: bool = False,
    ) -> bool:
        target_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_type",
                    match=models.MatchValue(value=source_type),
                ),
                models.FieldCondition(
                    key="source_id",
                    match=models.MatchValue(value=source_id),
                ),
                models.FieldCondition(
                    key="version",
                    match=models.MatchValue(value=version),
                ),
            ]
        )
        count = await self._client.count(
            collection_name=collection_name or self._collection,
            count_filter=target_filter,
            exact=True,
        )
        if count.count == 0:
            return False
        await self._client.set_payload(
            collection_name=collection_name or self._collection,
            payload={"active": True, "is_current": True},
            points=target_filter,
            wait=True,
        )
        old_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_type",
                    match=models.MatchValue(value=source_type),
                ),
                models.FieldCondition(
                    key="source_id",
                    match=models.MatchValue(value=source_id),
                ),
            ],
            must_not=[
                models.FieldCondition(
                    key="version",
                    match=models.MatchValue(value=version),
                )
            ],
        )
        if keep_inactive:
            await self._client.set_payload(
                collection_name=collection_name or self._collection,
                payload={"active": False, "is_current": False},
                points=old_filter,
                wait=True,
            )
        else:
            await self._delete_filter(old_filter, collection_name)
        return True

    async def update_payload(
        self,
        source_type: str,
        source_id: str,
        payload: dict[str, Any],
        version: str | None = None,
        collection_name: str | None = None,
    ) -> bool:
        target_filter = _source_filter(source_type, source_id)
        if version is not None:
            target_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_type",
                        match=models.MatchValue(value=source_type),
                    ),
                    models.FieldCondition(
                        key="source_id",
                        match=models.MatchValue(value=source_id),
                    ),
                    models.FieldCondition(
                        key="version",
                        match=models.MatchValue(value=version),
                    ),
                ]
            )
        count = await self._client.count(
            collection_name=collection_name or self._collection,
            count_filter=target_filter,
            exact=True,
        )
        if count.count == 0:
            return False
        await self._client.set_payload(
            collection_name=collection_name or self._collection,
            payload=payload,
            points=target_filter,
            wait=True,
        )
        return True

    async def cleanup_inactive(
        self,
        older_than_hours: float,
        source_type: str | None = None,
    ) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        must: list[models.Condition] = [
            models.FieldCondition(
                key="active",
                match=models.MatchValue(value=False),
            ),
            models.FieldCondition(
                key="created_at",
                range=models.DatetimeRange(lt=cutoff),
            ),
        ]
        if source_type is not None:
            must.append(
                models.FieldCondition(
                    key="source_type",
                    match=models.MatchValue(value=source_type),
                )
            )
        filter_ = models.Filter(must=must)
        count = await self._client.count(
            collection_name=self._collection,
            count_filter=filter_,
            exact=True,
        )
        if count.count:
            await self._delete_filter(filter_)
        return int(count.count)

    async def replace(
        self,
        source_type: str,
        documents: list[IndexedDocument],
        chunks: list[list[TextChunk]],
        vectors: list[list[list[float]]],
        sparse_vectors: list[list[models.SparseVector] | None] | None = None,
    ) -> int:
        if not (len(documents) == len(chunks) == len(vectors)):
            raise VectorStoreError("documents, chunks and vectors count mismatch")
        if sparse_vectors is not None and len(documents) != len(sparse_vectors):
            raise VectorStoreError("documents and sparse vectors count mismatch")
        await self._delete_filter(_source_filter(source_type))
        total = 0
        for position, (document, document_chunks, document_vectors) in enumerate(
            zip(documents, chunks, vectors, strict=True)
        ):
            if len(document_chunks) != len(document_vectors):
                raise VectorStoreError("chunks and vectors count mismatch")
            document_sparse = sparse_vectors[position] if sparse_vectors is not None else None
            total += await self.upsert(
                source_type,
                document,
                document_chunks,
                document_vectors,
                document_sparse,
            )
        return total

    async def search(
        self,
        vector: list[float],
        filters: SearchFilters,
        limit: int,
        min_score: float,
    ) -> list[SearchResult]:
        response = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            using=DENSE_VECTOR,
            query_filter=models.Filter(
                must=_filter_conditions(filters),
                must_not=_filter_must_not(filters),
            ),
            limit=limit,
            score_threshold=min_score,
            with_payload=True,
            with_vectors=False,
        )
        return [_payload_to_result(point, "dense") for point in response.points]

    async def search_hybrid(
        self,
        dense_vector: list[float],
        sparse_vector: models.SparseVector,
        filters: SearchFilters,
        limit: int,
        hnsw_ef: int,
    ) -> list[SearchResult]:
        if not sparse_vector.indices:
            return await self.search(dense_vector, filters, limit, 0.0)
        response = await self._client.query_points(
            collection_name=self._collection,
            prefetch=[
                models.Prefetch(
                    query=dense_vector,
                    using=DENSE_VECTOR,
                    limit=limit,
                    params=models.SearchParams(hnsw_ef=hnsw_ef),
                ),
                models.Prefetch(
                    query=sparse_vector,
                    using=SPARSE_VECTOR,
                    limit=limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=models.Filter(
                must=_filter_conditions(filters),
                must_not=_filter_must_not(filters),
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [_payload_to_result(point, "rrf") for point in response.points]

    async def fetch_source_chunks(
        self,
        source_type: str,
        source_id: str,
        limit: int = 10000,
        collection_name: str | None = None,
    ) -> list[SearchResult]:
        collection = collection_name or self._collection
        base_filter = _source_filter(source_type, source_id)
        must = base_filter.must if isinstance(base_filter.must, list) else [base_filter.must]
        must = [condition for condition in must if condition is not None]
        must.append(models.FieldCondition(key="active", match=models.MatchValue(value=True)))
        scroll_filter = models.Filter(must=must)
        results: list[SearchResult] = []
        offset: Any = None
        while len(results) < limit:
            points, offset = await self._client.scroll(
                collection_name=collection,
                scroll_filter=scroll_filter,
                limit=min(512, limit - len(results)),
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            results.extend(_payload_to_result(point, "scroll") for point in points)
            if offset is None:
                break
        results.sort(key=lambda item: item.chunk_index)
        return results

    async def fetch_parent_chunks(
        self,
        source_type: str,
        source_id: str,
        parent_id: str,
        limit: int,
    ) -> list[SearchResult]:
        points, _ = await self._client.scroll(
            collection_name=self._collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_type",
                        match=models.MatchValue(value=source_type),
                    ),
                    models.FieldCondition(
                        key="source_id",
                        match=models.MatchValue(value=source_id),
                    ),
                    models.FieldCondition(
                        key="parent_id",
                        match=models.MatchValue(value=parent_id),
                    ),
                    models.FieldCondition(
                        key="active",
                        match=models.MatchValue(value=True),
                    ),
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        results = [_payload_to_result(point, "parent") for point in points]
        return sorted(results, key=lambda result: result.chunk_index)
