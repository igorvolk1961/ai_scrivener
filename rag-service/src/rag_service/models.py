from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_types: list[str] = Field(default_factory=list)
    doc_types: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    authorities: list[str] = Field(default_factory=list)
    document_keys: list[str] = Field(default_factory=list)
    family_ids: list[str] = Field(default_factory=list)
    active: bool = True
    is_current: bool | None = None
    position_ids: list[str] = Field(default_factory=list)
    folders: list[str] = Field(default_factory=list)
    employees: list[str] = Field(default_factory=list)
    purposes: list[str] = Field(default_factory=list)
    acl_principals: list[str] = Field(default_factory=list)
    acl_deny_principals: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    source_type: str
    source_id: str
    version: str
    title: str
    chunk_index: int
    text: str
    metadata: dict[str, Any]
    embedding_text: str = ""
    document_key: str = ""
    family_id: str = ""
    is_current: bool | None = None
    section_path: list[str] = Field(default_factory=list)
    section_text: str = ""
    clause: str = ""
    page_start: int | None = None
    page_end: int | None = None
    kind: str = "text"
    parent_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    rerank_score: float | None = None
    score_type: str = "dense"


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SearchResult]
    diagnostics: dict[str, Any] | None = None


class IndexItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1)
    items: list[IndexItem] = Field(min_length=1)


class ReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1)
    items: list[IndexItem]


class IndexResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    indexed_items: int
    indexed_chunks: int


class DeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    deleted: bool


class RetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    scope: Literal["knowledge", "documents"] = "knowledge"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int | None = Field(default=None, ge=1, le=100)
    candidate_k: int | None = Field(default=None, ge=1, le=500)
    group_by_source: bool | None = None
    group_size: int | None = Field(default=None, ge=1, le=20)
    rerank: bool | None = None
    include_parent: bool | None = None


class RetrieveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    document_key: str
    title: str
    score: float
    score_type: str
    metadata: dict[str, Any]
    chunks: list[SearchResult]


class RetrieveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    results: list[RetrieveResult]
    diagnostics: dict[str, Any]


class IndexChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    text: str = Field(min_length=1)
    embedding_text: str | None = None
    section_path: list[str] = Field(default_factory=list)
    section_text: str = ""
    clause: str = ""
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    kind: str = "text"
    parent_id: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexChunksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1)
    document: IndexDocument
    chunks: list[IndexChunk] = Field(min_length=1)
    replace_existing: bool = True
    active: bool = True
    target_collection: str | None = None


class IndexChunksResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    version: str
    indexed_chunks: int


class ActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    target_collection: str | None = None


class ActivateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    version: str
    activated: bool


class CleanupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    older_than_hours: float = Field(default=24, gt=0)
    source_type: str | None = None


class CleanupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: int


class CreateCollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)


class CreateCollectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class SwitchAliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1)
    collection: str = Field(min_length=1)


class SwitchAliasResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str
    collection: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    qdrant: bool
    embedding_dimension: int | None
    collection_state: dict[str, Any] | None = None
    documents_collection_state: dict[str, Any] | None = None


class DocumentChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_index: int
    clause: str = ""
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    kind: str = "text"
    text: str


class DocumentTextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    version: str
    title: str
    doc_type: str = ""
    text: str
    chunks: list[DocumentChunk]


class PdfLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str


class DocumentSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    family_id: str = ""
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    doc_type: str = ""
    doc_kind: str = ""
    registration_number: str = ""
    document_date: str | None = None
    status: str = "approved"
    approved_at: str | None = None
    effective_from: str | None = None
    is_current: bool = True
    content_hash: str = ""
    file_hash: str = ""
    acl_principals: list[str] = Field(default_factory=list)
    acl_deny_principals: list[str] = Field(default_factory=list)
    acl_version: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentIndexResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    version: str
    indexed_chunks: int
    content_hash: str
    requires_ocr: bool = False


class DocumentBase64Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1)
    document: DocumentSnapshot
    text: str | None = None
    file_base64: str | None = None
    file_name: str | None = None
    mime: str | None = None


class MetadataUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    version: str | None = None
    payload: dict[str, Any] = Field(min_length=1)


class MetadataUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    updated: bool
