from __future__ import annotations

import re
from dataclasses import dataclass


class ChunkingError(ValueError):
    pass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def normalize_paragraphs(text: str) -> str:
    lines = [
        " ".join(line.split())
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    normalized = "\n".join(lines)
    while "\n\n\n" in normalized:
        normalized = normalized.replace("\n\n\n", "\n\n")
    return normalized.strip()


def _split_long_paragraph(paragraph: str, chunk_size: int, overlap: int) -> list[str]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?;:])\s+", paragraph) if part.strip()]
    if len(sentences) <= 1:
        return [item.text for item in chunk_text(paragraph, chunk_size, overlap)]
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for sentence in sentences:
        extra = len(sentence) + (1 if current else 0)
        if current and current_length + extra > chunk_size:
            chunks.append(" ".join(current))
            current = [sentence]
            current_length = len(sentence)
            continue
        current.append(sentence)
        current_length += extra
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_structured_text(text: str, chunk_size: int, overlap: int) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ChunkingError("chunk size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ChunkingError("overlap must be non-negative and less than chunk size")
    normalized = normalize_paragraphs(text)
    if not normalized:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in paragraphs:
        parts = (
            [paragraph]
            if len(paragraph) <= chunk_size
            else _split_long_paragraph(paragraph, chunk_size, overlap)
        )
        for part in parts:
            extra = len(part) + (2 if current else 0)
            if current and current_length + extra > chunk_size:
                chunks.append("\n\n".join(current))
                current = [part]
                current_length = len(part)
                continue
            current.append(part)
            current_length += extra
    if current:
        chunks.append("\n\n".join(current))
    return [TextChunk(index=index, text=chunk) for index, chunk in enumerate(chunks)]


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
