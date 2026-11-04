from __future__ import annotations

from rag_indexer.extraction import Block, PdfTable, merge_table_blocks, table_blocks


def _block(text: str, page: int = 1) -> Block:
    return Block(
        text=text,
        page_start=page,
        page_end=page,
        kind="paragraph",
        engine="test",
        confidence=1.0,
    )


def test_table_blocks_builds_table_block() -> None:
    blocks = table_blocks(
        [
            PdfTable(
                page_number=2,
                text="Наименование | Количество\nТовар | 10",
                rows=2,
                columns=2,
            )
        ]
    )

    assert len(blocks) == 1
    assert blocks[0].kind == "table"
    assert blocks[0].page_start == 2
    assert blocks[0].metadata["rows"] == 2


def test_merge_table_blocks_removes_table_fragment() -> None:
    table = PdfTable(
        page_number=1,
        text="Наименование | Количество\nТовар | 10",
        rows=2,
        columns=2,
    )
    blocks = [
        _block("Наименование | Количество"),
        _block("Обычный абзац инструкции."),
        _block("Товар | 10"),
    ]

    merged = merge_table_blocks(blocks, [table])

    assert [block.kind for block in merged] == ["paragraph", "table"]
    assert merged[0].text == "Обычный абзац инструкции."


def test_merge_table_blocks_sorts_by_page() -> None:
    table = PdfTable(
        page_number=1,
        text="A | B\n1 | 2",
        rows=2,
        columns=2,
    )
    blocks = [_block("Текст на второй странице.", page=2)]

    merged = merge_table_blocks(blocks, [table])

    assert [block.page_start for block in merged] == [1, 2]
