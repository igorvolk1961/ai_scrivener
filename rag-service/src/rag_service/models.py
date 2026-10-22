from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_types: list[str] = Field(default_factory=list)
    doc_types: list[str] = Field(default_factory=list)
    active: bool = True
    position_ids: list[str] = Field(default_factory=list)


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


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SearchResult]


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


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    qdrant: bool
    embedding_dimension: int | None
