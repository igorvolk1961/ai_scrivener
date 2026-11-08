from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from rag_indexer.extraction.models import Block, ExtractedDocument

CLAUSE_RE = re.compile(
    r"^\s*("
    r"\d+(?:\.\d+)+\.?"
    r"|\d+[.)]"
    r"|[IVXLC]+[.)]"
    r"|[а-яё]\)"
    r"|(?:п|ст)\.\s*\d+(?:\.\d+)*"
    r"|(?:статья|пункт|подпункт|раздел|глава|приложение)\s+\d+(?:\.\d+)*\.?"
    r")\s+",
    re.IGNORECASE,
)
HEADING_CLAUSE_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(?=[А-ЯЁA-Z])")
DATE_CLAUSE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.(?:19|20)\d{2}$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;:])\s+")
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class ChunkerOptions:
    target_tokens: int = 350
    max_tokens: int = 600
    min_tokens: int = 80
    overlap_sentences: int = 1


@dataclass
class Section:
    index: int
    path: list[str]
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Chunk:
    index: int
    text: str
    embedding_text: str
    section_path: list[str]
    section_text: str
    clause: str
    page_start: int | None
    page_end: int | None
    kind: str
    parent_id: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    char_start: int | None = None
    char_end: int | None = None


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


class StructureBuilder:
    def build(self, document: ExtractedDocument) -> list[Section]:
        sections: list[Section] = []
        path: list[str] = []
        current: Section | None = None
        for block in document.blocks:
            if block.kind == "heading":
                level = _heading_level(block)
                path = [*path[: max(0, level - 1)], block.text.strip()]
                current = Section(index=len(sections), path=list(path), blocks=[block])
                sections.append(current)
                continue
            if current is None or current.path != path:
                current = Section(index=len(sections), path=list(path))
                sections.append(current)
            current.blocks.append(block)
        return sections


class ClauseAwareChunker:
    def __init__(self, options: ChunkerOptions | None = None) -> None:
        self._options = options or ChunkerOptions()
        self._builder = StructureBuilder()

    def chunk(
        self,
        document: ExtractedDocument,
        source_id: str | None = None,
    ) -> list[Chunk]:
        resolved_source = source_id or document.source_path.name
        chunks: list[Chunk] = []
        for section in self._builder.build(document):
            chunks.extend(
                self._chunk_section(
                    document.title,
                    section,
                    resolved_source,
                )
            )
        for index, chunk in enumerate(chunks):
            chunk.index = index
        return chunks

    def _chunk_section(
        self,
        title: str,
        section: Section,
        source_id: str,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        buffer: list[Block] = []
        carry_clause = ""

        def flush() -> None:
            nonlocal carry_clause
            if not buffer:
                return
            chunk = self._make_chunk(
                title,
                section,
                source_id,
                buffer,
                carry_clause,
            )
            chunks.append(chunk)
            if chunk.clause:
                carry_clause = chunk.clause
            buffer.clear()

        def has_body() -> bool:
            return any(item.kind != "heading" for item in buffer)

        def buffer_clause() -> str:
            for item in buffer:
                if item.kind == "heading":
                    continue
                clause = _block_clause(item)
                if clause:
                    return clause
            return carry_clause

        for block in section.blocks:
            if not block.text.strip():
                continue
            if block.kind == "heading":
                flush()
                buffer.append(block)
                continue
            expanded = (
                self._split_table(block) if block.kind == "table" else self._split_clauses(block)
            )
            for expanded_block in expanded:
                if expanded_block.kind == "table":
                    flush()
                    buffer.append(expanded_block)
                    flush()
                    continue
                parts = (
                    self._split_block(expanded_block)
                    if estimate_tokens(expanded_block.text) > self._options.max_tokens
                    else [expanded_block]
                )
                for part in parts:
                    part_clause = _block_clause(part)
                    if buffer and has_body() and part_clause and buffer_clause() != part_clause:
                        flush()
                    candidate = "\n\n".join(item.text for item in [*buffer, part])
                    if buffer and estimate_tokens(candidate) > self._options.target_tokens:
                        flush()
                    buffer.append(part)
        flush()
        return self._merge_small_tail(title, section, source_id, chunks)

    def _make_chunk(
        self,
        title: str,
        section: Section,
        source_id: str,
        blocks: list[Block],
        carry_clause: str = "",
    ) -> Chunk:
        text = "\n\n".join(block.text.strip() for block in blocks if block.text.strip())
        clause = _chunk_clause(blocks, section, carry_clause)
        kinds = {block.kind for block in blocks}
        if "table" in kinds:
            kind = "table"
        elif kinds == {"heading"}:
            kind = "heading"
        elif "heading" in kinds:
            kind = "paragraph"
        else:
            kind = blocks[0].kind
        section_text = " → ".join(section.path)
        return Chunk(
            index=0,
            text=text,
            embedding_text=_context_text(title, section.path, clause, text),
            section_path=list(section.path),
            section_text=section_text,
            clause=clause,
            page_start=blocks[0].page_start,
            page_end=blocks[-1].page_end,
            kind=kind,
            parent_id=f"{source_id}:section:{section.index}",
            metadata={
                "section_index": section.index,
                "block_kinds": sorted(kinds),
            },
        )

    def _split_clauses(self, block: Block) -> list[Block]:
        if block.kind in {"heading", "table"}:
            return [block]
        text = block.text.strip()
        if not text:
            return []
        groups: list[str] = []
        current: list[str] = []
        for line in (line.strip() for line in text.splitlines() if line.strip()):
            if current and CLAUSE_RE.match(line):
                groups.append(" ".join(current))
                current = [line]
                continue
            current.append(line)
        if current:
            groups.append(" ".join(current))
        if len(groups) == 1:
            groups = [
                part.strip()
                for part in re.split(
                    r"(?<=[.!?;:])\s+(?=\d+(?:\.\d+)*[.)]?\s+[А-ЯЁA-Z])",
                    groups[0],
                )
                if part.strip()
            ]
        if len(groups) <= 1:
            return [block]
        return [_with_clause(block, group) for group in groups]

    def _split_table(self, block: Block) -> list[Block]:
        rows = [row.strip() for row in block.text.splitlines() if row.strip()]
        if len(rows) <= 1:
            return [block]
        header = rows[0]
        parts: list[str] = []
        current = [header]
        current_tokens = estimate_tokens(header)
        for row in rows[1:]:
            row_tokens = estimate_tokens(row)
            if len(current) > 1 and current_tokens + row_tokens > self._options.max_tokens:
                parts.append("\n".join(current))
                current = [header, row]
                current_tokens = estimate_tokens(header) + row_tokens
                continue
            current.append(row)
            current_tokens += row_tokens
        if len(current) > 1:
            parts.append("\n".join(current))
        if not parts:
            return [block]
        return [replace(block, text=part) for part in parts]

    def _split_block(self, block: Block) -> list[Block]:
        sentences = [
            sentence.strip() for sentence in SENTENCE_SPLIT_RE.split(block.text) if sentence.strip()
        ]
        if len(sentences) <= 1:
            return [
                replace(block, text=part)
                for part in _split_words(block.text, self._options.max_tokens)
            ]
        parts: list[str] = []
        current: list[str] = []
        for sentence in sentences:
            candidate = " ".join([*current, sentence])
            if current and estimate_tokens(candidate) > self._options.max_tokens:
                parts.append(" ".join(current))
                overlap = current[-self._options.overlap_sentences :]
                current = [*overlap, sentence] if overlap else [sentence]
                if estimate_tokens(" ".join(current)) > self._options.max_tokens:
                    current = [sentence]
                continue
            current.append(sentence)
        if current:
            parts.append(" ".join(current))
        return [replace(block, text=part) for part in parts]

    def _merge_small_tail(
        self,
        title: str,
        section: Section,
        source_id: str,
        chunks: list[Chunk],
    ) -> list[Chunk]:
        while len(chunks) > 1 and estimate_tokens(chunks[-1].text) < self._options.min_tokens:
            previous = chunks[-2]
            if previous.kind == "table" or chunks[-1].kind == "table":
                break
            if previous.clause and chunks[-1].clause and previous.clause != chunks[-1].clause:
                break
            merged_text = f"{previous.text}\n\n{chunks[-1].text}"
            if estimate_tokens(merged_text) > self._options.max_tokens:
                break
            merged = self._make_chunk(
                title,
                section,
                source_id,
                [
                    Block(
                        text=merged_text,
                        page_start=previous.page_start or 1,
                        page_end=chunks[-1].page_end or previous.page_end or 1,
                        kind=previous.kind,
                        engine="merged",
                        confidence=1.0,
                        metadata={"clause": previous.clause} if previous.clause else {},
                    )
                ],
                previous.clause,
            )
            chunks[-2:] = [merged]
        return chunks


def _heading_level(block: Block) -> int:
    value = block.metadata.get("heading_level")
    return int(value) if isinstance(value, int) and value > 0 else 1


def _extract_clause(text: str, *, heading: bool = False) -> str:
    stripped = text.strip()
    match = CLAUSE_RE.match(stripped)
    if match:
        raw = match.group(1).strip()
        value = raw.rstrip(".)").strip()
        if not heading and raw.endswith(")"):
            return ""
        if not heading and re.fullmatch(r"[IVXLC]+", value):
            return ""
        return "" if DATE_CLAUSE_RE.match(value) else value

    if heading:
        heading_match = HEADING_CLAUSE_RE.match(stripped)
        if heading_match:
            value = heading_match.group(1).rstrip(".)")
            return "" if DATE_CLAUSE_RE.match(value) else value
    return ""


def _block_clause(block: Block) -> str:
    value = block.metadata.get("clause")
    if isinstance(value, str) and value:
        return value
    return _extract_clause(block.text, heading=block.kind == "heading")


def _section_clause(section: Section) -> str:
    for block in reversed(section.blocks):
        if block.kind == "heading":
            clause = _block_clause(block)
            if clause:
                return clause
    return ""


def _chunk_clause(
    blocks: list[Block],
    section: Section,
    carry_clause: str,
) -> str:
    for block in blocks:
        if block.kind == "heading":
            continue
        clause = _block_clause(block)
        if clause:
            return clause
    for block in blocks:
        if block.kind != "heading":
            continue
        clause = _block_clause(block)
        if clause:
            return clause
    return _section_clause(section) or carry_clause


def _with_clause(block: Block, text: str) -> Block:
    metadata = dict(block.metadata)
    clause = _extract_clause(text, heading=block.kind == "heading")
    if clause:
        metadata["clause"] = clause
    else:
        metadata.pop("clause", None)
    return replace(block, text=text, metadata=metadata)


def _context_text(
    title: str,
    section_path: list[str],
    clause: str,
    text: str,
) -> str:
    lines = [f"Документ: {title}"]
    if section_path:
        lines.append(f"Раздел: {' → '.join(section_path)}")
    if clause:
        lines.append(f"Пункт: {clause}")
    lines.append(f"Текст: {text}")
    return "\n".join(lines)


def _split_words(text: str, max_tokens: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    parts: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and estimate_tokens(candidate) > max_tokens:
            parts.append(" ".join(current))
            current = [word]
            continue
        current.append(word)
    if current:
        parts.append(" ".join(current))
    return parts
