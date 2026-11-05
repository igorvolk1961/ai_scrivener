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
            _block(
                "Наименование | Количество\nТовар | 10",
                kind="table",
            ),
        ]
    )

    chunks = ClauseAwareChunker().chunk(document)

    assert len(chunks) == 1
    assert chunks[0].kind == "table"


def test_chunker_extracts_article_clause() -> None:
    document = _document([_block("Статья 1. Область применения")])

    chunks = ClauseAwareChunker().chunk(document)

    assert chunks[0].clause == "Статья 1"


def test_chunker_extracts_heading_number_as_clause() -> None:
    document = _document([_block("1 Область применения", kind="heading", heading_level=1)])

    chunks = ClauseAwareChunker().chunk(document)

    assert chunks[0].clause == "1"


def test_chunker_does_not_treat_date_as_clause() -> None:
    document = _document([_block("1965 г. N П-6 введен в действие.")])
    dotted = _document([_block("16.09.2020 введены новые правила.")])

    chunks = ClauseAwareChunker().chunk(document)
    dotted_chunks = ClauseAwareChunker().chunk(dotted)

    assert chunks[0].clause == ""
    assert dotted_chunks[0].clause == ""


def test_chunker_splits_inline_clauses() -> None:
    document = _document([_block("1. Первый пункт. 2. Второй пункт.")])

    chunks = ClauseAwareChunker(
        ChunkerOptions(target_tokens=2, max_tokens=100, min_tokens=1)
    ).chunk(document)

    assert len(chunks) == 2
    assert [chunk.clause for chunk in chunks] == ["1", "2"]


def test_chunker_extracts_clause_with_trailing_dot() -> None:
    document = _document(
        [
            _block("1.1. Первый пункт."),
            _block("1.2. Второй пункт."),
        ]
    )

    chunks = ClauseAwareChunker(
        ChunkerOptions(target_tokens=2, max_tokens=100, min_tokens=1)
    ).chunk(document)

    assert [chunk.clause for chunk in chunks] == ["1.1", "1.2"]


def test_chunker_splits_table_rows_with_header() -> None:
    header = "Наименование | Количество | Примечание"
    rows = [
        f"Товар {index} | {index} | " + "описание " * 5
        for index in range(5)
    ]
    document = _document([_block("\n".join([header, *rows]), kind="table")])

    chunks = ClauseAwareChunker(
        ChunkerOptions(target_tokens=10, max_tokens=25, min_tokens=1)
    ).chunk(document)

    assert len(chunks) > 1
    assert all(chunk.text.startswith(header) for chunk in chunks)


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


def test_chunker_does_not_merge_distinct_clauses() -> None:
    document = _document(
        [
            _block(
                "28. Акты приемки регистрируются. "
                "29. Претензия предъявляется отправителю. "
                "30. По получении претензии руководитель рассматривает её."
            )
        ]
    )

    chunks = ClauseAwareChunker(
        ChunkerOptions(target_tokens=500, max_tokens=1000, min_tokens=1)
    ).chunk(document)

    assert [chunk.clause for chunk in chunks] == ["28", "29", "30"]


def test_chunker_keeps_inline_clause_marker() -> None:
    document = _document(
        [
            _block(
                "2 УХЛ4 УХЛ4.1 У5 04 04.1 Т5 ТС2 В5 "
                "(Введен дополнительно, Изм. № 4). "
                "2.8. В условное обозначение изделия вводят буквы и цифры."
            )
        ]
    )

    chunks = ClauseAwareChunker(
        ChunkerOptions(target_tokens=500, max_tokens=1000, min_tokens=1)
    ).chunk(document)

    assert any(chunk.clause == "2.8" for chunk in chunks)
    assert any("2.8." in chunk.text for chunk in chunks)


def test_chunker_inherits_heading_clause_for_body() -> None:
    document = _document(
        [
            _block(
                "17.2 Основные виды материальных запасов",
                kind="heading",
                heading_level=2,
            ),
            _block("Материальные запасы делятся на производственные и товарные."),
        ]
    )

    chunks = ClauseAwareChunker().chunk(document)

    assert len(chunks) == 1
    assert chunks[0].clause == "17.2"


def test_chunker_does_not_treat_list_items_as_clauses() -> None:
    document = _document(
        [
            _block(
                "58. При погрузке груза в таре необходимо соблюдать требования: "
                "1) тара загружается не более номинальной массы брутто; "
                "2) груз находится ниже уровня бортов; "
                "3) стенки тары находятся в закрытом положении."
            )
        ]
    )

    chunks = ClauseAwareChunker(
        ChunkerOptions(target_tokens=500, max_tokens=1000, min_tokens=1)
    ).chunk(document)

    assert any(chunk.clause == "58" for chunk in chunks)
    assert all(chunk.clause in {"", "58"} for chunk in chunks)


def test_chunker_does_not_take_table_number_as_clause() -> None:
    document = _document(
        [
            _block(
                "2 УХЛ4 УХЛ4.1 У5 04 04.1 Т5 ТС2\n"
                "Наименование | Значение",
                kind="table",
            )
        ]
    )

    chunks = ClauseAwareChunker().chunk(document)

    assert all(chunk.clause == "" for chunk in chunks)


def test_chunker_does_not_merge_small_tail_with_other_clause() -> None:
    document = _document(
        [
            _block("1. Первый пункт."),
            _block("2. Второй пункт."),
        ]
    )

    chunks = ClauseAwareChunker(
        ChunkerOptions(target_tokens=2, max_tokens=100, min_tokens=50)
    ).chunk(document)

    assert [chunk.clause for chunk in chunks] == ["1", "2"]
