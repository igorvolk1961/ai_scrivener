from __future__ import annotations

import html
import re
from pathlib import Path

from rag_indexer.chunking import Chunk, ChunkerOptions, ClauseAwareChunker
from rag_indexer.extraction.document import DocumentExtractor
from rag_indexer.extraction.models import Block, ExtractedDocument
from rag_service.models import IndexChunk

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MAX_HEADING_LENGTH = 160
_CLAUSE_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)+\.?|\d+[.)]|[IVXLC]+[.)]|[а-яё]\)|"
    r"(?:статья|пункт|подпункт|раздел|глава|приложение)\s+\d+(?:\.\d+)*\.?)\s+",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"раздел|глава|часть|приложение|"
    r"\d+(?:\.\d+)*[.)]?\s+[А-ЯЁA-Z]"
    r")",
    re.IGNORECASE,
)


class DocumentBuildError(ValueError):
    pass


def _plain_text(value: str) -> str:
    text = html.unescape(value)
    if "<" in text and ">" in text:
        text = _HTML_TAG_RE.sub(" ", text)
    lines = [" ".join(line.split()) for line in text.replace("\r\n", "\n").split("\n")]
    result: list[str] = []
    for line in lines:
        if line or (result and result[-1]):
            result.append(line)
    return "\n".join(result).strip()


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LENGTH:
        return False
    if _CLAUSE_RE.match(stripped):
        return False
    if _HEADING_RE.match(stripped):
        return True
    if stripped.endswith((".", "!", "?", ";", ":")):
        return False
    return stripped.upper() == stripped and any(ch.isalpha() for ch in stripped)


def text_blocks(text: str) -> list[Block]:
    normalized = _plain_text(text)
    if not normalized:
        return []
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        content = "\n".join(paragraph).strip()
        paragraph.clear()
        if not content:
            return
        blocks.append(
            Block(
                text=content,
                page_start=1,
                page_end=1,
                kind="paragraph",
                engine="1c",
                confidence=1.0,
            )
        )

    for line in normalized.split("\n"):
        if not line.strip():
            flush_paragraph()
            continue
        if _is_heading(line):
            flush_paragraph()
            blocks.append(
                Block(
                    text=line.strip(),
                    page_start=1,
                    page_end=1,
                    kind="heading",
                    engine="1c",
                    confidence=1.0,
                    metadata={"heading_level": _heading_level(line)},
                )
            )
            continue
        paragraph.append(line.strip())
    flush_paragraph()
    return blocks


def _heading_level(line: str) -> int:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", line)
    if not match:
        return 1
    return match.group(1).count(".") + 1


def _dedupe_blocks(blocks: list[Block]) -> list[Block]:
    seen: set[str] = set()
    result: list[Block] = []
    for block in blocks:
        key = " ".join(block.text.split()).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(block)
    return result


async def build_extracted_document(
    *,
    title: str,
    text: str | None,
    file_path: Path | None,
    mime: str | None,
    original_name: str | None,
) -> tuple[ExtractedDocument, bool]:
    blocks = text_blocks(text or "")
    requires_ocr = False
    if file_path is not None:
        extracted = await DocumentExtractor().extract(
            file_path,
            mime=mime,
            original_name=original_name,
        )
        suffix = file_path.suffix.lower()
        requires_ocr = suffix == ".pdf" and not extracted.blocks
        blocks.extend(extracted.blocks)
    if not blocks:
        if requires_ocr:
            return (
                ExtractedDocument(
                    source_path=file_path or Path(f"{title or 'document'}.txt"),
                    title=title,
                    page_count=0,
                    blocks=[],
                    metadata={"mime": mime or "application/pdf", "engines": ["file"]},
                ),
                True,
            )
        raise DocumentBuildError("document has no text and no extractable file content")
    document = ExtractedDocument(
        source_path=file_path or Path(f"{title or 'document'}.txt"),
        title=title,
        page_count=max((block.page_end for block in blocks), default=1),
        blocks=_dedupe_blocks(blocks),
        metadata={
            "mime": mime or "text/plain",
            "engines": ["1c", "file"] if file_path is not None else ["1c"],
        },
    )
    return document, requires_ocr


def chunk_document(
    document: ExtractedDocument,
    *,
    source_id: str,
    options: ChunkerOptions,
) -> list[IndexChunk]:
    chunks: list[Chunk] = ClauseAwareChunker(options).chunk(document, source_id=source_id)
    return [_to_index_chunk(chunk) for chunk in chunks]


def _to_index_chunk(chunk: Chunk) -> IndexChunk:
    return IndexChunk(
        index=chunk.index,
        text=chunk.text,
        embedding_text=chunk.embedding_text,
        section_path=chunk.section_path,
        section_text=chunk.section_text,
        clause=chunk.clause,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        kind=chunk.kind,
        parent_id=chunk.parent_id,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        metadata=chunk.metadata,
    )
