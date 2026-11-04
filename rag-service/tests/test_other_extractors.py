from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from rag_indexer.extraction import (
    DocumentExtractor,
    DocxExtractor,
    ExtractionError,
    HtmlExtractor,
    TextExtractor,
)

HTML = """
<html><body><article>
<h1>Инструкция П-6</h1>
<p>Настоящая инструкция применяется во всех случаях приемки.</p>
<h2>1. Общие положения</h2>
<ul><li>Первый пункт</li><li>Второй пункт</li></ul>
<table>
<tr><th>Наименование</th><th>Количество</th></tr>
<tr><td>Товар</td><td>10</td></tr>
</table>
<p>Заключительный абзац.</p>
</article></body></html>
"""


def test_text_extractor_builds_blocks(tmp_path: Path) -> None:
    path = tmp_path / "instruction.txt"
    path.write_text(
        "1 Область применения\n\n"
        "Настоящий стандарт устанавливает требования.\n\n"
        "1.1 Первый пункт инструкции.\n",
        encoding="utf-8",
    )

    document = TextExtractor().extract(path)

    kinds = [block.kind for block in document.blocks]
    assert "heading" in kinds
    assert "paragraph" in kinds
    assert document.metadata["engines"] == ["text"]
    assert not any("\n" in block.text for block in document.blocks)


def test_html_extractor_builds_blocks(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_text(HTML, encoding="utf-8")

    document = HtmlExtractor().extract(path)

    kinds = [block.kind for block in document.blocks]
    assert "heading" in kinds
    assert "list_item" in kinds
    assert "table" in kinds
    assert any("Наименование" in block.text for block in document.blocks)


def test_docx_extractor_builds_blocks(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("Инструкция", level=1)
    document.add_paragraph("Первый абзац.")
    document.add_paragraph("Первый пункт", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Наименование"
    table.cell(0, 1).text = "Количество"
    table.cell(1, 0).text = "Товар"
    table.cell(1, 1).text = "10"
    path = tmp_path / "instruction.docx"
    document.save(path)

    extracted = DocxExtractor().extract(path)

    kinds = [block.kind for block in extracted.blocks]
    assert "heading" in kinds
    assert "list_item" in kinds
    assert "table" in kinds
    assert any("Наименование" in block.text for block in extracted.blocks)


def test_document_extractor_dispatches_by_suffix(tmp_path: Path) -> None:
    path = tmp_path / "instruction.txt"
    path.write_text("1 Область применения\n\nНастоящий стандарт.", encoding="utf-8")

    document = asyncio.run(DocumentExtractor().extract(path))

    assert document.metadata["engines"] == ["text"]


def test_document_extractor_uses_mime_without_suffix(tmp_path: Path) -> None:
    path = tmp_path / "blob-without-extension"
    path.write_text("1 Общие положения\n\nТекст.", encoding="utf-8")

    document = asyncio.run(
        DocumentExtractor().extract(path, mime="text/plain; charset=utf-8")
    )

    assert document.metadata["engines"] == ["text"]


def test_document_extractor_uses_original_name_suffix(tmp_path: Path) -> None:
    path = tmp_path / "blob-without-extension"
    path.write_text("1 Общие положения\n\nТекст.", encoding="utf-8")

    document = asyncio.run(
        DocumentExtractor().extract(path, original_name="instruction.txt")
    )

    assert document.metadata["engines"] == ["text"]


def test_document_extractor_rejects_unknown_suffix(tmp_path: Path) -> None:
    path = tmp_path / "document.bin"
    path.write_bytes(b"\x00\x01")

    with pytest.raises(ExtractionError):
        asyncio.run(DocumentExtractor().extract(path))
