from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rag_indexer.extraction.models import Block, ExtractionError

MIN_TABLE_FRAGMENT_CHARS = 8
MIN_TABLE_ROWS = 2
MIN_TABLE_COLUMNS = 2
MIN_TABLE_CHARS = 20


@dataclass(frozen=True)
class PdfTable:
    page_number: int
    text: str
    rows: int
    columns: int
    bbox: tuple[float, float, float, float] | None = None


def extract_pdf_tables(
    path: Path,
    page_numbers: set[int] | None = None,
) -> list[PdfTable]:
    try:
        import pdfplumber
    except ImportError as error:
        raise ExtractionError(
            "pdfplumber is required for PDF tables; install the 'indexer' extra"
        ) from error
    tables: list[PdfTable] = []
    with pdfplumber.open(str(path)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            if page_numbers is not None and index not in page_numbers:
                continue
            for found in page.find_tables():
                rows = _clean_rows(found.extract())
                if len(rows) < MIN_TABLE_ROWS:
                    continue
                columns = max(len(row) for row in rows)
                if columns < MIN_TABLE_COLUMNS:
                    continue
                text = "\n".join(" | ".join(row) for row in rows).strip()
                if len(text) < MIN_TABLE_CHARS:
                    continue
                bbox = found.bbox
                tables.append(
                    PdfTable(
                        page_number=index,
                        text=text,
                        rows=len(rows),
                        columns=columns,
                        bbox=(
                            float(bbox[0]),
                            float(bbox[1]),
                            float(bbox[2]),
                            float(bbox[3]),
                        )
                        if bbox
                        else None,
                    )
                )
    return tables


def table_blocks(tables: list[PdfTable]) -> list[Block]:
    return [
        Block(
            text=table.text,
            page_start=table.page_number,
            page_end=table.page_number,
            kind="table",
            engine="pdfplumber",
            confidence=1.0,
            metadata={
                "rows": table.rows,
                "columns": table.columns,
                "bbox": table.bbox,
            },
        )
        for table in tables
    ]


def merge_table_blocks(blocks: list[Block], tables: list[PdfTable]) -> list[Block]:
    if not tables:
        return blocks
    table_texts = [" ".join(table.text.split()) for table in tables]
    filtered = [
        block
        for block in blocks
        if not _is_table_fragment(block.text, table_texts)
    ]
    merged = [*filtered, *table_blocks(tables)]
    merged.sort(key=lambda block: block.page_start)
    return merged


def _is_table_fragment(text: str, table_texts: list[str]) -> bool:
    normalized = " ".join(text.split())
    if len(normalized) < MIN_TABLE_FRAGMENT_CHARS:
        return False
    return any(normalized in table_text for table_text in table_texts)


def _clean_rows(rows: list[list[str | None]]) -> list[list[str]]:
    cleaned: list[list[str]] = []
    for row in rows:
        values = [
            " ".join(str(cell or "").split())
            for cell in row
        ]
        if any(values):
            cleaned.append(values)
    return cleaned
