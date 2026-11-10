from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=20)
    locale: str = "ru"
    safe_search: bool = True


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source: str
    rank: int


class SearchResponse(BaseModel):
    results: list[SearchResult]
    provider: str
    latency_ms: int


def normalize_result(item: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "title": str(item.get("title") or ""),
        "url": str(item.get("url") or ""),
        "snippet": str(item.get("snippet") or ""),
        "source": str(item.get("source") or "internet"),
        "rank": rank,
    }
