from __future__ import annotations

import pytest

from rag_service.chunking import (
    ChunkingError,
    chunk_structured_text,
    chunk_text,
    normalize_paragraphs,
    normalize_text,
)


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


def test_normalize_paragraphs_keeps_line_breaks() -> None:
    assert normalize_paragraphs("  один\n\n два\tтри ") == "один\n\nдва три"


def test_structured_chunk_keeps_paragraphs_and_clause_lines() -> None:
    text = "1. Первый пункт.\n2. Второй пункт.\n\nПриложение А."
    chunks = chunk_structured_text(text, chunk_size=1000, overlap=100)

    assert len(chunks) == 1
    assert "1. Первый пункт.\n2. Второй пункт." in chunks[0].text
    assert "Приложение А." in chunks[0].text


def test_structured_chunk_splits_long_paragraph_by_sentences() -> None:
    text = " ".join(["Предложение для проверки."] * 40)
    chunks = chunk_structured_text(text, chunk_size=100, overlap=10)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
