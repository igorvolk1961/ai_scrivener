from __future__ import annotations

from pathlib import Path

from rag_indexer.extraction import Block, ExtractedDocument, render_markdown


def test_render_markdown_preserves_blocks() -> None:
    document = ExtractedDocument(
        source_path=Path("doc.pdf"),
        title="Инструкция",
        page_count=2,
        blocks=[
            Block(
                text="1 Общие положения",
                page_start=1,
                page_end=1,
                kind="heading",
                engine="text_layer",
                confidence=1.0,
                metadata={"heading_level": 1},
            ),
            Block(
                text="Текст пункта.",
                page_start=1,
                page_end=1,
                kind="paragraph",
                engine="text_layer",
                confidence=1.0,
            ),
            Block(
                text="Наименование | Количество\nТовар | 10",
                page_start=2,
                page_end=2,
                kind="table",
                engine="pdfplumber",
                confidence=1.0,
            ),
        ],
    )

    markdown = render_markdown(document)

    assert markdown.startswith("# Инструкция")
    assert "<!-- page 1 -->" in markdown
    assert "<!-- page 2 -->" in markdown
    assert "# 1 Общие положения" in markdown
    assert "Текст пункта." in markdown
    assert "Товар | 10" in markdown
