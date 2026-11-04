from __future__ import annotations

import re
from pathlib import Path

from rag_indexer.extraction.models import Block, ExtractedDocument, ExtractionError

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
EMPHASIS_RE = re.compile(r"(\*\*|__)(.+?)\1")
CODE_RE = re.compile(r"`(.+?)`")
LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")


class HtmlExtractor:
    def extract(self, path: Path) -> ExtractedDocument:
        try:
            import trafilatura
        except ImportError as error:
            raise ExtractionError(
                "trafilatura is required for HTML extraction; install the 'indexer' extra"
            ) from error
        html = path.read_text(encoding="utf-8", errors="replace")
        try:
            markdown = trafilatura.extract(
                html,
                output_format="markdown",
                include_links=False,
                include_tables=True,
                include_formatting=True,
                favor_recall=True,
            )
        except Exception as error:
            raise ExtractionError(f"failed to extract HTML {path}") from error
        if not markdown:
            raise ExtractionError(f"no readable content found in HTML {path}")
        return ExtractedDocument(
            source_path=path,
            title=path.stem,
            page_count=1,
            blocks=_blocks_from_markdown(markdown),
            metadata={"mime": "text/html", "engines": ["html"]},
        )


def _blocks_from_markdown(markdown: str) -> list[Block]:
    blocks: list[Block] = []
    paragraph: list[str] = []
    table: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = _clean_markdown(" ".join(paragraph)).strip()
            if text:
                blocks.append(_block(text, "paragraph"))
            paragraph.clear()

    def flush_table() -> None:
        if table:
            text = "\n".join(table).strip()
            if text:
                blocks.append(_block(text, "table"))
            table.clear()

    for line in markdown.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            flush_table()
            blocks.append(
                _block(
                    _clean_markdown(heading.group(2)).strip(),
                    "heading",
                    {"heading_level": len(heading.group(1))},
                )
            )
            continue
        if TABLE_RE.match(line):
            flush_paragraph()
            if not TABLE_SEPARATOR_RE.match(line):
                table.append(line)
            continue
        flush_table()
        item = LIST_RE.match(line)
        if item:
            flush_paragraph()
            blocks.append(_block(_clean_markdown(item.group(1)).strip(), "list_item"))
            continue
        if not line.strip():
            flush_paragraph()
            continue
        paragraph.append(line.strip())
    flush_paragraph()
    flush_table()
    return blocks


def _clean_markdown(text: str) -> str:
    cleaned = LINK_RE.sub(r"\1", text)
    cleaned = EMPHASIS_RE.sub(r"\2", cleaned)
    cleaned = CODE_RE.sub(r"\1", cleaned)
    return " ".join(cleaned.split())


def _block(text: str, kind: str, metadata: dict[str, int] | None = None) -> Block:
    return Block(
        text=text,
        page_start=1,
        page_end=1,
        kind=kind,
        engine="html",
        confidence=1.0,
        metadata=metadata or {},
    )
