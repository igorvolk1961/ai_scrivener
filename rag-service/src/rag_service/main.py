from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

from rag_service.chunking import ChunkingError, TextChunk, chunk_text
from rag_service.config import (
    ApplicationParameters,
    ConfigurationError,
    ServiceSettings,
    load_parameters,
    load_settings,
)
from rag_service.gigachat import GigaChatClient, GigaChatError
from rag_service.models import (
    DeleteResponse,
    HealthResponse,
    IndexItem,
    IndexRequest,
    IndexResponse,
    ReplaceRequest,
    SearchRequest,
    SearchResponse,
)
from rag_service.qdrant_store import IndexedDocument, QdrantStore, VectorStore, VectorStoreError

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    @property
    def dimension(self) -> int | None: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def probe_dimension(self) -> int: ...

    async def close(self) -> None: ...


def _require_token(
    request: Request, x_service_token: Annotated[str | None, Header()] = None
) -> None:
    settings: ServiceSettings = request.app.state.settings
    expected = settings.service_token.get_secret_value()
    if x_service_token is None or not secrets.compare_digest(x_service_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service token",
        )


def _embedder(request: Request) -> Embedder:
    return request.app.state.embedder


def _store(request: Request) -> VectorStore:
    return request.app.state.store


def _parameters(request: Request) -> ApplicationParameters:
    return request.app.state.parameters


async def _prepare_item(
    source_type: str,
    item: IndexItem,
    embedder: Embedder,
    parameters: ApplicationParameters,
) -> tuple[IndexedDocument, list[TextChunk], list[list[float]]]:
    chunks = chunk_text(
        item.text,
        chunk_size=parameters.rag.chunk_size_chars,
        overlap=parameters.rag.chunk_overlap_chars,
    )
    vectors = await embedder.embed([chunk.text for chunk in chunks])
    document = IndexedDocument(
        source_id=item.source_id,
        version=item.version,
        title=item.title,
        metadata=item.metadata,
    )
    return document, chunks, vectors


def create_app(
    parameters: ApplicationParameters | None = None,
    settings: ServiceSettings | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_parameters = parameters or load_parameters()
        resolved_settings = settings or load_settings()
        resolved_embedder = embedder or GigaChatClient(resolved_settings, resolved_parameters)
        resolved_store = store or QdrantStore(
            url=str(resolved_settings.qdrant_url),
            collection=str(resolved_settings.qdrant_collection),
            api_key=(
                resolved_settings.qdrant_api_key.get_secret_value()
                if resolved_settings.qdrant_api_key is not None
                else None
            ),
        )
        dimension = await resolved_embedder.probe_dimension()
        configured = resolved_parameters.rag.embedding_dimension
        if configured is not None and configured != dimension:
            raise ConfigurationError(
                f"configured embedding dimension {configured} does not match GigaChat {dimension}"
            )
        await resolved_store.ensure_collection(dimension)
        app.state.parameters = resolved_parameters
        app.state.settings = resolved_settings
        app.state.embedder = resolved_embedder
        app.state.store = resolved_store
        try:
            yield
        finally:
            await resolved_embedder.close()
            await resolved_store.close()

    app = FastAPI(title="ai_scrivener RAG", version="0.1.0", lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        resolved_store: VectorStore = request.app.state.store
        resolved_embedder: Embedder = request.app.state.embedder
        return HealthResponse(
            status="ok",
            qdrant=await resolved_store.health(),
            embedding_dimension=resolved_embedder.dimension,
        )

    @app.post(
        "/v1/search",
        response_model=SearchResponse,
        dependencies=[Depends(_require_token)],
    )
    async def search(request: Request, payload: SearchRequest) -> SearchResponse:
        resolved_parameters = _parameters(request)
        resolved_embedder = _embedder(request)
        resolved_store = _store(request)
        try:
            vector = (await resolved_embedder.embed([payload.query]))[0]
            results = await resolved_store.search(
                vector=vector,
                filters=payload.filters,
                limit=resolved_parameters.rag.top_k,
                min_score=resolved_parameters.rag.search_min_score,
            )
        except (GigaChatError, VectorStoreError) as error:
            logger.exception("search failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="search dependency failed",
            ) from error
        return SearchResponse(results=results)

    @app.post(
        "/v1/index/upsert",
        response_model=IndexResponse,
        dependencies=[Depends(_require_token)],
    )
    async def index_upsert(request: Request, payload: IndexRequest) -> IndexResponse:
        resolved_parameters = _parameters(request)
        resolved_embedder = _embedder(request)
        resolved_store = _store(request)
        indexed_chunks = 0
        try:
            for item in payload.items:
                document, chunks, vectors = await _prepare_item(
                    payload.source_type, item, resolved_embedder, resolved_parameters
                )
                indexed_chunks += await resolved_store.upsert(
                    payload.source_type, document, chunks, vectors
                )
        except (GigaChatError, VectorStoreError, ChunkingError) as error:
            logger.exception("index upsert failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="indexing dependency failed",
            ) from error
        logger.info(
            "indexed source_type=%s items=%s chunks=%s",
            payload.source_type,
            len(payload.items),
            indexed_chunks,
        )
        return IndexResponse(
            source_type=payload.source_type,
            indexed_items=len(payload.items),
            indexed_chunks=indexed_chunks,
        )

    @app.post(
        "/v1/index/replace",
        response_model=IndexResponse,
        dependencies=[Depends(_require_token)],
    )
    async def index_replace(request: Request, payload: ReplaceRequest) -> IndexResponse:
        resolved_parameters = _parameters(request)
        resolved_embedder = _embedder(request)
        resolved_store = _store(request)
        documents: list[IndexedDocument] = []
        all_chunks: list[list[TextChunk]] = []
        all_vectors: list[list[list[float]]] = []
        try:
            for item in payload.items:
                document, chunks, vectors = await _prepare_item(
                    payload.source_type, item, resolved_embedder, resolved_parameters
                )
                documents.append(document)
                all_chunks.append(chunks)
                all_vectors.append(vectors)
            indexed_chunks = await resolved_store.replace(
                payload.source_type, documents, all_chunks, all_vectors
            )
        except (GigaChatError, VectorStoreError, ChunkingError) as error:
            logger.exception("index replace failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="indexing dependency failed",
            ) from error
        logger.info(
            "replaced source_type=%s items=%s chunks=%s",
            payload.source_type,
            len(payload.items),
            indexed_chunks,
        )
        return IndexResponse(
            source_type=payload.source_type,
            indexed_items=len(payload.items),
            indexed_chunks=indexed_chunks,
        )

    @app.delete(
        "/v1/index/{source_type}/{source_id}",
        response_model=DeleteResponse,
        dependencies=[Depends(_require_token)],
    )
    async def index_delete(request: Request, source_type: str, source_id: str) -> DeleteResponse:
        resolved_store = _store(request)
        try:
            deleted = await resolved_store.delete(source_type, source_id)
        except VectorStoreError as error:
            logger.exception("index delete failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="indexing dependency failed",
            ) from error
        return DeleteResponse(source_type=source_type, source_id=source_id, deleted=deleted)

    return app


app = create_app()
