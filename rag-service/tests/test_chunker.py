from __future__ import annotations

from pathlib import Path

from rag_indexer.chunking import (
    ChunkerOptions,
    ClauseAwareChunker,
    StructureBuilder,
    estimate_tokens,
)
from rag_indexer.extraction import Block, ExtractedDocument


def _block(
    text: str,
    kind: str = "paragraph",
    page: int = 1,
    heading_level: int | None = None,
) -> Block:
    metadata = {"heading_level": heading_level} if heading_level is not None else {}
    return Block(
        text=text,
        page_start=page,
        page_end=page,
        kind=kind,
        engine="test",
        confidence=1.0,
        metadata=metadata,
    )


def _document(blocks: list[Block]) -> ExtractedDocument:
    return ExtractedDocument(
        source_path=Path("instruction.pdf"),
        title="Инструкция П-6",
        page_count=3,
        blocks=blocks,
    )


def test_structure_builder_tracks_heading_path() -> None:
    document = _document(
        [
            _block("1 Общие положения", kind="heading", heading_level=1),
            _block("1.1 Первый пункт."),
            _block("2 Требования", kind="heading", heading_level=2),
            _block("2.1 Второй пункт."),
        ]
    )

    sections = StructureBuilder().build(document)

    assert [section.path for section in sections] == [
        ["1 Общие положения"],
        ["1 Общие положения", "2 Требования"],
    ]
    assert len(sections[0].blocks) == 2
    assert len(sections[1].blocks) == 2


def test_chunker_adds_context_and_clause() -> None:
    document = _document(
        [
            _block("1 Общие положения", kind="heading", heading_level=1),
            _block("1.1 Настоящая инструкция применяется.", page=2),
        ]
    )

    chunks = ClauseAwareChunker().chunk(document, source_id="sha-1")

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.index == 0
    assert chunk.section_path == ["1 Общие положения"]
    assert chunk.clause == "1.1"
    assert "Документ: Инструкция П-6" in chunk.embedding_text
    assert "Раздел: 1 Общие положения" in chunk.embedding_text
    assert "Пункт: 1.1" in chunk.embedding_text
    assert chunk.parent_id == "sha-1:section:0"
    assert chunk.page_start == 1
    assert chunk.page_end == 2


def test_chunker_splits_long_text() -> None:
    long_text = " ".join(["Настоящий пункт применяется для проверки."] * 80)
    document = _document([_block(long_text)])

    chunks = ClauseAwareChunker(ChunkerOptions(max_tokens=100, target_tokens=80)).chunk(
        document
    )

    assert len(chunks) > 1
    assert all(estimate_tokens(chunk.text) <= 100 for chunk in chunks)


def test_chunker_keeps_table_kind() -> None:
    document = _document(
        [
            _block("Наименование | Количество", kind="table"),
            _block("Товар | 10", kind="table"),
        ]
    )

    chunks = ClauseAwareChunker().chunk(document)

    assert len(chunks) == 1
    assert chunks[0].kind == "table"


def test_chunker_merges_small_tail() -> None:
    document = _document(
        [
            _block("1 Общие положения", kind="heading", heading_level=1),
            _block("Короткий текст."),
        ]
    )

    chunks = ClauseAwareChunker(
        ChunkerOptions(target_tokens=20, max_tokens=100, min_tokens=50)
    ).chunk(document)

    assert len(chunks) == 1
    assert "1 Общие положения" in chunks[0].text
