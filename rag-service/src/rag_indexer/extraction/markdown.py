from __future__ import annotations

from rag_indexer.extraction.models import ExtractedDocument

MAX_HEADING_DEPTH = 6


def render_markdown(document: ExtractedDocument) -> str:
    lines = [f"# {document.title}", ""]
    last_page: int | None = None
    for block in document.blocks:
        if block.page_start != last_page:
            lines.append(f"<!-- page {block.page_start} -->")
            lines.append("")
            last_page = block.page_start
        if block.kind == "heading":
            level = block.metadata.get("heading_level", 1)
            depth = level if isinstance(level, int) and 1 <= level <= MAX_HEADING_DEPTH else 1
            lines.append(f"{'#' * depth} {block.text}")
        elif block.kind == "table":
            lines.append(block.text)
        elif block.kind == "list_item":
            lines.append(f"- {block.text}")
        else:
            lines.append(block.text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"
