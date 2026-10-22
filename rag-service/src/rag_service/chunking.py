from __future__ import annotations

from dataclasses import dataclass


class ChunkingError(ValueError):
    pass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ChunkingError("chunk size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ChunkingError("overlap must be non-negative and less than chunk size")
    normalized = normalize_text(text)
    if not normalized:
        return []
    chunks: list[TextChunk] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            split_at = normalized.rfind(" ", start, end)
            if split_at > start:
                end = split_at
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(TextChunk(index=len(chunks), text=chunk))
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks
