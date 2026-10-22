from __future__ import annotations

import pytest

from rag_service.chunking import ChunkingError, chunk_text, normalize_text


def test_chunk_text_splits_long_text() -> None:
    text = " ".join(["слово"] * 400)
    chunks = chunk_text(text, chunk_size=100, overlap=10)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


def test_chunk_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ChunkingError):
        chunk_text("текст", chunk_size=100, overlap=100)


def test_chunk_text_returns_empty_for_blank_text() -> None:
    assert chunk_text("   \n\t ", chunk_size=100, overlap=10) == []


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("  один\n\n два\tтри ") == "один два три"
