from __future__ import annotations

import re

from rag_indexer.extraction.models import Block

PAGE_HEADER_RE = re.compile(
    r"^\s*(?:\d+\s+)?ГОСТ(?:\s+Р)?\s+\d+(?:\.\d+)*[-\u2013\u2014]\d+\s+"
    r"(?=(?:С\.\s*\d+|Продолжение|Примечание|Таблица)\b)",
    re.IGNORECASE,
)
PAGE_MARKER_RE = re.compile(
    r"^\s*(?:С\.\s*\d+|Продолжение|Примечание)(?:\s+|$)",
    re.IGNORECASE,
)
OCR_LIST_PREFIX_RE = re.compile(r"^\s*[иИ](?=\d)")


def clean_block_headers(blocks: list[Block]) -> list[Block]:
    cleaned: list[Block] = []
    for block in blocks:
        text = block.text
        previous = None
        while text != previous:
            previous = text
            text = PAGE_HEADER_RE.sub("", text)
            text = PAGE_MARKER_RE.sub("", text)
            text = OCR_LIST_PREFIX_RE.sub("", text)
        text = text.strip()
        if not text:
            continue
        if text != block.text:
            block = _replace_text(block, text)
        cleaned.append(block)
    return cleaned


def _replace_text(block: Block, text: str) -> Block:
    return Block(
        text=text,
        page_start=block.page_start,
        page_end=block.page_end,
        kind=block.kind,
        engine=block.engine,
        confidence=block.confidence,
        bbox=block.bbox,
        metadata=block.metadata,
    )
