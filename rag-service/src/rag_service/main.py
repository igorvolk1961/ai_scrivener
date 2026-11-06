from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Protocol, cast
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse

from rag_service.chunking import ChunkingError, TextChunk, chunk_structured_text
from rag_service.cloudru import CloudRuEmbedder, CloudRuError, CloudRuReranker
from rag_service.config import (
    ApplicationParameters,
    ConfigurationError,
    ServiceSettings,
    load_parameters,
    load_settings,
)
from rag_service.corpus import CorpusResolver
from rag_service.gigachat import GigaChatClient, GigaChatError
from rag_service.models import (
    ActivateRequest,
    ActivateResponse,
    CleanupRequest,
    CleanupResponse,
    CreateCollectionRequest,
    CreateCollectionResponse,
    DeleteResponse,
    DocumentChunk,
    DocumentTextResponse,
    HealthResponse,
    IndexChunksRequest,
    IndexChunksResponse,
    IndexItem,
    IndexRequest,
    IndexResponse,
    PdfLinkResponse,
    ReplaceRequest,
    RetrieveRequest,
    RetrieveResponse,
    SearchRequest,
    SearchResponse,
    SwitchAliasRequest,
    SwitchAliasResponse,
)
from rag_service.pdf_conversion import PdfConversionError, PdfConverter
from rag_service.qdrant_store import IndexedDocument, QdrantStore, VectorStore, VectorStoreError
from rag_service.rerank import FastEmbedReranker, Reranker, RerankerError
from rag_service.retrieval import Retriever
from rag_service.sparse import FastEmbedSparseEncoder, SparseEncoder, SparseEncoderError
from rag_service.view_tokens import create_view_token, verify_view_token

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    @property
    def dimension(self) -> int | None: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def probe_dimension(self) -> int: ...

    async def close(self) -> None: ...


def _service_token_valid(settings: ServiceSettings, value: str | None) -> bool:
    expected = settings.service_token.get_secret_value()
    return value is not None and secrets.compare_digest(value, expected)


def _require_token(
    request: Request, x_service_token: Annotated[str | None, Header()] = None
) -> None:
    settings: ServiceSettings = request.app.state.settings
    if not _service_token_valid(settings, x_service_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service token",
        )


def _embedder(request: Request) -> Embedder:
    return cast(Embedder, request.app.state.embedder)


def _store(request: Request) -> VectorStore:
    return cast(VectorStore, request.app.state.store)


def _sparse_encoder(request: Request) -> SparseEncoder | None:
    return cast(SparseEncoder | None, request.app.state.sparse_encoder)


def _retriever(request: Request) -> Retriever:
    return cast(Retriever, request.app.state.retriever)


def _parameters(request: Request) -> ApplicationParameters:
    return cast(ApplicationParameters, request.app.state.parameters)


async def _prepare_item(
    source_type: str,
    item: IndexItem,
    embedder: Embedder,
    parameters: ApplicationParameters,
) -> tuple[IndexedDocument, list[TextChunk], list[list[float]]]:
    chunks = chunk_structured_text(
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
    sparse_encoder: SparseEncoder | None = None,
    reranker: Reranker | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_parameters = parameters or load_parameters()
        resolved_settings = settings or load_settings()
        if embedder is not None:
            resolved_embedder = embedder
        elif resolved_settings.embedding_provider == "cloudru":
            resolved_embedder = CloudRuEmbedder(resolved_settings, resolved_parameters)
        elif resolved_settings.embedding_provider == "gigachat":
            resolved_embedder = GigaChatClient(resolved_settings, resolved_parameters)
        else:
            raise ConfigurationError("RAG_EMBEDDING_PROVIDER must be 'gigachat' or 'cloudru'")
        resolved_store = store or QdrantStore(
            url=str(resolved_settings.qdrant_url),
            collection=str(resolved_settings.qdrant_collection),
            api_key=(
                resolved_settings.qdrant_api_key.get_secret_value()
                if resolved_settings.qdrant_api_key is not None
                else None
            ),
        )
        resolved_sparse = sparse_encoder
        if resolved_sparse is None and resolved_parameters.rag.hybrid_enabled:
            resolved_sparse = FastEmbedSparseEncoder(
                resolved_parameters.rag.sparse_model,
                resolved_parameters.rag.sparse_language,
                resolved_parameters.rag.sparse_avg_len,
            )
        resolved_reranker = reranker
        if resolved_reranker is None and resolved_parameters.rag.rerank_enabled:
            if resolved_settings.rerank_provider == "cloudru":
                resolved_reranker = CloudRuReranker(
                    resolved_settings,
                    resolved_parameters,
                )
            elif resolved_settings.rerank_provider == "fastembed":
                resolved_reranker = FastEmbedReranker(
                    resolved_parameters.rag.rerank_model,
                    resolved_parameters.rag.rerank_batch_size,
                )
            else:
                raise ConfigurationError("RAG_RERANK_PROVIDER must be 'fastembed' or 'cloudru'")
        dimension = await resolved_embedder.probe_dimension()
        configured = resolved_parameters.rag.embedding_dimension
        if configured is not None and configured != dimension:
            raise ConfigurationError(
                f"configured embedding dimension {configured} does not match GigaChat {dimension}"
            )
        await resolved_store.ensure_collection(dimension)
        app.state.parameters = resolved_parameters
        app.state.settings = resolved_settings
        app.state.corpus = CorpusResolver(
            resolved_settings.corpus_manifest,
            resolved_settings.corpus_dir,
        )
        app.state.pdf_converter = PdfConverter(
            resolved_settings.pdf_cache_dir,
            resolved_settings.pdf_conversion_timeout_seconds,
        )
        app.state.embedder = resolved_embedder
        app.state.dimension = dimension
        app.state.store = resolved_store
        app.state.sparse_encoder = resolved_sparse
        app.state.reranker = resolved_reranker
        app.state.retriever = Retriever(
            resolved_parameters,
            resolved_embedder,
            resolved_store,
            resolved_sparse,
            resolved_reranker,
        )
        try:
            yield
        finally:
            await resolved_embedder.close()
            if resolved_sparse is not None:
                await resolved_sparse.close()
            if resolved_reranker is not None:
                await resolved_reranker.close()
            await resolved_store.close()

    app = FastAPI(title="ai_scrivener RAG", version="0.1.0", lifespan=lifespan)

    @app.post(
        "/v1/admin/collections",
        response_model=CreateCollectionResponse,
        dependencies=[Depends(_require_token)],
    )
    async def create_collection_endpoint(
        request: Request, payload: CreateCollectionRequest
    ) -> CreateCollectionResponse:
        try:
            await _store(request).create_collection(
                payload.name,
                request.app.state.dimension,
            )
        except VectorStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="collection creation failed",
            ) from error
        return CreateCollectionResponse(name=payload.name)

    @app.post(
        "/v1/admin/alias",
        response_model=SwitchAliasResponse,
        dependencies=[Depends(_require_token)],
    )
    async def switch_alias_endpoint(
        request: Request, payload: SwitchAliasRequest
    ) -> SwitchAliasResponse:
        try:
            await _store(request).switch_alias(payload.alias, payload.collection)
        except VectorStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="alias switch failed",
            ) from error
        return SwitchAliasResponse(
            alias=payload.alias,
            collection=payload.collection,
        )

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        resolved_store: VectorStore = request.app.state.store
        resolved_embedder: Embedder = request.app.state.embedder
        collection_state: dict[str, Any] | None = None
        try:
            collection_state = await resolved_store.collection_state()
        except Exception:
            logger.exception("collection state lookup failed")
        return HealthResponse(
            status="ok",
            qdrant=await resolved_store.health(),
            embedding_dimension=resolved_embedder.dimension,
            collection_state=collection_state,
        )

    @app.get(
        "/v1/documents/{source_id}/text",
        response_model=DocumentTextResponse,
        dependencies=[Depends(_require_token)],
    )
    async def document_text(
        request: Request,
        source_id: str,
        source_type: str = "knowledge_material",
    ) -> DocumentTextResponse:
        resolved_store: VectorStore = request.app.state.store
        try:
            chunks = await resolved_store.fetch_source_chunks(source_type, source_id)
        except VectorStoreError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="document text lookup failed",
            ) from error
        if not chunks:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
        first = chunks[0]
        return DocumentTextResponse(
            source_type=first.source_type,
            source_id=first.source_id,
            version=first.version,
            title=first.title,
            doc_type=str(first.metadata.get("doc_type", "")),
            text="\n\n".join(chunk.text for chunk in chunks),
            chunks=[
                DocumentChunk(
                    chunk_index=chunk.chunk_index,
                    clause=chunk.clause,
                    section_path=chunk.section_path,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    kind=chunk.kind,
                    text=chunk.text,
                )
                for chunk in chunks
            ],
        )

    @app.get(
        "/v1/documents/{source_id}/file",
        dependencies=[Depends(_require_token)],
    )
    async def document_file(request: Request, source_id: str) -> FileResponse:
        resolver: CorpusResolver = request.app.state.corpus
        resolved = resolver.resolve(source_id)
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="document file not found"
            )
        return FileResponse(
            path=resolved.path,
            media_type=resolved.mime,
            filename=resolved.original_name,
        )

    @app.post(
        "/v1/documents/{source_id}/pdf-link",
        response_model=PdfLinkResponse,
        dependencies=[Depends(_require_token)],
    )
    async def document_pdf_link(request: Request, source_id: str) -> PdfLinkResponse:
        resolver: CorpusResolver = request.app.state.corpus
        if resolver.resolve(source_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="document not found"
            )
        settings: ServiceSettings = request.app.state.settings
        token = create_view_token(
            settings.service_token.get_secret_value(),
            source_id,
            settings.pdf_view_token_ttl_seconds,
        )
        base_url = settings.pdf_public_base_url.rstrip("/")
        return PdfLinkResponse(
            url=f"{base_url}/v1/documents/{source_id}/pdf?token={token}"
        )

    @app.get("/v1/documents/{source_id}/pdf")
    async def document_pdf(
        request: Request,
        source_id: str,
        token: str | None = None,
        x_service_token: Annotated[str | None, Header()] = None,
    ) -> FileResponse:
        settings: ServiceSettings = request.app.state.settings
        authorized = (
            verify_view_token(settings.service_token.get_secret_value(), source_id, token)
            if token is not None
            else _service_token_valid(settings, x_service_token)
        )
        if not authorized:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid access token",
            )
        resolver: CorpusResolver = request.app.state.corpus
        resolved = resolver.resolve(source_id)
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="document not found"
            )
        converter: PdfConverter = request.app.state.pdf_converter
        try:
            pdf_path = await converter.to_pdf(source_id, resolved)
        except PdfConversionError as error:
            logger.exception("PDF conversion failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="PDF conversion failed",
            ) from error
        filename = f"{Path(resolved.original_name).stem}.pdf"
        ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "document.pdf"
        disposition = (
            f'inline; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(filename)}"
        )
        return FileResponse(
            path=pdf_path,
            media_type="application/pdf",
            headers={"Content-Disposition": disposition},
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
        except (CloudRuError, GigaChatError, VectorStoreError) as error:
            logger.exception("search failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="search dependency failed",
            ) from error
        return SearchResponse(results=results)

    @app.post(
        "/v1/retrieve",
        response_model=RetrieveResponse,
        dependencies=[Depends(_require_token)],
    )
    async def retrieve(request: Request, payload: RetrieveRequest) -> RetrieveResponse:
        try:
            return await _retriever(request).retrieve(payload)
        except (
            CloudRuError,
            GigaChatError,
            VectorStoreError,
            SparseEncoderError,
            RerankerError,
        ) as error:
            logger.exception("retrieve failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="retrieval dependency failed",
            ) from error

    @app.post(
        "/v1/index/upsert",
        response_model=IndexResponse,
        dependencies=[Depends(_require_token)],
    )
    async def index_upsert(request: Request, payload: IndexRequest) -> IndexResponse:
        resolved_parameters = _parameters(request)
        resolved_embedder = _embedder(request)
        resolved_store = _store(request)
        sparse = _sparse_encoder(request)
        indexed_chunks = 0
        try:
            for item in payload.items:
                document, chunks, vectors = await _prepare_item(
                    payload.source_type, item, resolved_embedder, resolved_parameters
                )
                sparse_vectors = (
                    await sparse.embed_documents([chunk.text for chunk in chunks])
                    if sparse is not None
                    else None
                )
                indexed_chunks += await resolved_store.upsert(
                    payload.source_type,
                    document,
                    chunks,
                    vectors,
                    sparse_vectors,
                )
        except (
            CloudRuError,
            GigaChatError,
            VectorStoreError,
            SparseEncoderError,
            ChunkingError,
        ) as error:
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
        sparse = _sparse_encoder(request)
        documents: list[IndexedDocument] = []
        all_chunks: list[list[TextChunk]] = []
        all_vectors: list[list[list[float]]] = []
        all_sparse_vectors: list[list[Any] | None] = []
        try:
            for item in payload.items:
                document, chunks, vectors = await _prepare_item(
                    payload.source_type, item, resolved_embedder, resolved_parameters
                )
                documents.append(document)
                all_chunks.append(chunks)
                all_vectors.append(vectors)
                all_sparse_vectors.append(
                    await sparse.embed_documents([chunk.text for chunk in chunks])
                    if sparse is not None
                    else None
                )
            indexed_chunks = await resolved_store.replace(
                payload.source_type,
                documents,
                all_chunks,
                all_vectors,
                all_sparse_vectors,
            )
        except (
            CloudRuError,
            GigaChatError,
            VectorStoreError,
            SparseEncoderError,
            ChunkingError,
        ) as error:
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

    @app.post(
        "/v1/index/chunks",
        response_model=IndexChunksResponse,
        dependencies=[Depends(_require_token)],
    )
    async def index_chunks(request: Request, payload: IndexChunksRequest) -> IndexChunksResponse:
        resolved_embedder = _embedder(request)
        resolved_store = _store(request)
        sparse = _sparse_encoder(request)
        document = IndexedDocument(
            source_id=payload.document.source_id,
            version=payload.document.version,
            title=payload.document.title,
            metadata=payload.document.metadata,
        )
        texts = [chunk.embedding_text or chunk.text for chunk in payload.chunks]
        try:
            dense_vectors = await resolved_embedder.embed(texts)
            sparse_vectors = await sparse.embed_documents(texts) if sparse is not None else None
            indexed_chunks = await resolved_store.upsert_chunks(
                payload.source_type,
                document,
                payload.chunks,
                dense_vectors,
                sparse_vectors,
                replace_existing=payload.replace_existing,
                active=payload.active,
                collection_name=payload.target_collection,
            )
        except (CloudRuError, GigaChatError, VectorStoreError, SparseEncoderError) as error:
            logger.exception("index chunks failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="indexing dependency failed",
            ) from error
        logger.info(
            "indexed chunks source_type=%s source_id=%s chunks=%s",
            payload.source_type,
            payload.document.source_id,
            indexed_chunks,
        )
        return IndexChunksResponse(
            source_type=payload.source_type,
            source_id=payload.document.source_id,
            version=payload.document.version,
            indexed_chunks=indexed_chunks,
        )

    @app.post(
        "/v1/index/activate",
        response_model=ActivateResponse,
        dependencies=[Depends(_require_token)],
    )
    async def activate_document(request: Request, payload: ActivateRequest) -> ActivateResponse:
        try:
            activated = await _store(request).activate_document(
                payload.source_type,
                payload.source_id,
                payload.version,
                payload.target_collection,
            )
        except VectorStoreError as error:
            logger.exception("activate document failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="activation dependency failed",
            ) from error
        return ActivateResponse(
            source_type=payload.source_type,
            source_id=payload.source_id,
            version=payload.version,
            activated=activated,
        )

    @app.post(
        "/v1/index/cleanup",
        response_model=CleanupResponse,
        dependencies=[Depends(_require_token)],
    )
    async def cleanup_inactive(request: Request, payload: CleanupRequest) -> CleanupResponse:
        try:
            deleted = await _store(request).cleanup_inactive(
                payload.older_than_hours,
                payload.source_type,
            )
        except VectorStoreError as error:
            logger.exception("cleanup inactive points failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="cleanup dependency failed",
            ) from error
        return CleanupResponse(deleted=deleted)

    @app.delete(
        "/v1/index/{source_type}/{source_id}",
        response_model=DeleteResponse,
        dependencies=[Depends(_require_token)],
    )
    async def index_delete(
        request: Request,
        source_type: str,
        source_id: str,
        target_collection: str | None = None,
    ) -> DeleteResponse:
        resolved_store = _store(request)
        try:
            deleted = await resolved_store.delete(
                source_type,
                source_id,
                target_collection,
            )
        except VectorStoreError as error:
            logger.exception("index delete failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="indexing dependency failed",
            ) from error
        return DeleteResponse(source_type=source_type, source_id=source_id, deleted=deleted)

    return app


app = create_app()
