from __future__ import annotations

import re
from pathlib import Path

from rag_indexer.extraction.models import Block, ExtractedDocument, ExtractionError

HEADING_RE = re.compile(r"^(?:heading|заголовок)\s*(\d+)", re.IGNORECASE)
LIST_RE = re.compile(r"(?:list|список)", re.IGNORECASE)


class DocxExtractor:
    def extract(self, path: Path) -> ExtractedDocument:
        try:
            from docx import Document
            from docx.oxml.ns import qn
            from docx.table import Table
            from docx.text.paragraph import Paragraph
        except ImportError as error:
            raise ExtractionError(
                "python-docx is required for DOCX extraction; install the 'indexer' extra"
            ) from error
        try:
            document = Document(str(path))
        except Exception as error:
            raise ExtractionError(f"failed to open DOCX {path}") from error
        blocks: list[Block] = []
        for child in document.element.body.iterchildren():
            if child.tag == qn("w:p"):
                block = self._paragraph_block(Paragraph(child, document))
                if block is not None:
                    blocks.append(block)
            elif child.tag == qn("w:tbl"):
                block = self._table_block(Table(child, document))
                if block is not None:
                    blocks.append(block)
        return ExtractedDocument(
            source_path=path,
            title=path.stem,
            page_count=1,
            blocks=blocks,
            metadata={
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "engines": ["docx"],
            },
        )

    @staticmethod
    def _paragraph_block(paragraph: object) -> Block | None:
        text = str(getattr(paragraph, "text", "")).strip()
        if not text:
            return None
        style = getattr(getattr(paragraph, "style", None), "name", "") or ""
        kind = "paragraph"
        metadata: dict[str, object] = {}
        heading = HEADING_RE.match(style)
        if heading:
            kind = "heading"
            metadata["heading_level"] = int(heading.group(1))
        elif LIST_RE.search(style):
            kind = "list_item"
        return Block(
            text=text,
            page_start=1,
            page_end=1,
            kind=kind,
            engine="docx",
            confidence=1.0,
            metadata=metadata,
        )

    @staticmethod
    def _table_block(table: object) -> Block | None:
        rows = getattr(table, "rows", [])
        lines: list[str] = []
        column_count = 0
        for row in rows:
            cells = [str(getattr(cell, "text", "")).strip() for cell in row.cells]
            column_count = max(column_count, len(cells))
            line = " | ".join(cells).strip()
            if line:
                lines.append(line)
        if not lines:
            return None
        return Block(
            text="\n".join(lines),
            page_start=1,
            page_end=1,
            kind="table",
            engine="docx",
            confidence=1.0,
            metadata={"rows": len(lines), "columns": column_count},
        )
