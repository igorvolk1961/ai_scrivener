from __future__ import annotations

import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rag_indexer.extraction.models import Block
from rag_indexer.ocr.models import BBox, OcrDocument, OcrLine

CLAUSE_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[.)]?|(?:п|ст|подп|разд|гл|прил)\.?\s*\d+|[IVXLC]+[.)])\s+",
    re.IGNORECASE,
)
HEADING_NUMBER_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s+[А-ЯЁA-Z]")
HEADING_WORD_RE = re.compile(
    r"^\s*(?:РАЗДЕЛ|ГЛАВА|СТАТЬЯ|ПРИЛОЖЕНИЕ|ТАБЛИЦА)\b",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"^\s*(?:[-–—•]|[а-яё]\))\s+", re.IGNORECASE)
TABLE_RE = re.compile(r"(?:\t|\s{3,})")
SENTENCE_END_RE = re.compile(r"[.!?…][\"'»)]?$")
UPPER_OR_NUMBER_START_RE = re.compile(r"^[\"'«(]?[A-ZА-ЯЁ0-9]")


@dataclass(frozen=True)
class MergerOptions:
    line_gap_ratio: float = 1.3
    indent_ratio: float = 1.5
    column_gap_ratio: float = 0.15
    heading_max_chars: int = 120
    median_char_width_ratio: float = 0.3


def _union_bbox(boxes: list[BBox]) -> BBox | None:
    if not boxes:
        return None
    return BBox(
        x0=min(box.x0 for box in boxes),
        y0=min(box.y0 for box in boxes),
        x1=max(box.x1 for box in boxes),
        y1=max(box.y1 for box in boxes),
    )


class LineToParagraphMerger:
    def __init__(self, options: MergerOptions | None = None) -> None:
        self._options = options or MergerOptions()

    def merge_document(
        self,
        document: OcrDocument,
        page_widths: Mapping[int, int] | None = None,
    ) -> list[Block]:
        lines = [line for page in document.pages for line in page.lines]
        engine_by_page = {page.page_number: page.engine for page in document.pages}
        return self.merge(lines, page_widths, engine_by_page)

    def merge(
        self,
        lines: Sequence[OcrLine],
        page_widths: Mapping[int, int] | None = None,
        engine_by_page: Mapping[int, str] | None = None,
    ) -> list[Block]:
        ordered = sorted(
            (line for line in lines if line.text.strip()),
            key=lambda line: (
                line.page_number,
                line.bbox.y0 if line.bbox else 0,
                line.bbox.x0 if line.bbox else 0,
            ),
        )
        if not ordered:
            return []
        heights = [
            line.bbox.height
            for line in ordered
            if line.bbox is not None and line.bbox.height > 0
        ]
        median_height = statistics.median(heights) if heights else 1.0
        indent_threshold = self._options.indent_ratio * max(
            1.0,
            median_height * self._options.median_char_width_ratio,
        )
        blocks: list[Block] = []
        current: list[OcrLine] = []
        for line in ordered:
            if current and self._starts_new_block(
                current[-1],
                line,
                median_height,
                indent_threshold,
                page_widths or {},
            ):
                blocks.append(
                    self._build_block(current, engine_by_page or {})
                )
                current = []
            current.append(line)
        if current:
            blocks.append(self._build_block(current, engine_by_page or {}))
        return blocks

    def _starts_new_block(
        self,
        previous: OcrLine,
        line: OcrLine,
        median_height: float,
        indent_threshold: float,
        page_widths: Mapping[int, int],
    ) -> bool:
        if previous.page_number != line.page_number:
            return True
        if _is_heading(previous.text, self._options.heading_max_chars):
            return True
        if _starts_new_block_text(line.text):
            return True
        if SENTENCE_END_RE.search(previous.text) and UPPER_OR_NUMBER_START_RE.match(
            line.text
        ):
            return True
        if previous.bbox is None or line.bbox is None:
            return False
        if line.bbox.y0 < previous.bbox.y0:
            return True
        if line.bbox.y0 - previous.bbox.y1 > self._options.line_gap_ratio * median_height:
            return True
        if abs(line.bbox.x0 - previous.bbox.x0) > indent_threshold:
            return True
        page_width = page_widths.get(line.page_number)
        if page_width and line.bbox.x0 - previous.bbox.x1 > (
            self._options.column_gap_ratio * page_width
        ):
            return True
        return _is_table_row(line.text) and not _is_table_row(previous.text)

    def _build_block(
        self,
        lines: list[OcrLine],
        engine_by_page: Mapping[int, str],
    ) -> Block:
        text = _join_lines([line.text for line in lines])
        boxes = [line.bbox for line in lines if line.bbox is not None]
        confidence = sum(line.confidence for line in lines) / len(lines)
        return Block(
            text=text,
            page_start=lines[0].page_number,
            page_end=lines[-1].page_number,
            kind=_classify_kind(
                lines[0].text,
                self._options.heading_max_chars,
            ),
            engine=engine_by_page.get(lines[0].page_number, "unknown"),
            confidence=confidence,
            bbox=_union_bbox(boxes),
            metadata={"line_count": len(lines)},
        )


def _starts_new_block_text(text: str) -> bool:
    stripped = text.strip()
    return bool(
        CLAUSE_RE.match(stripped)
        or HEADING_NUMBER_RE.match(stripped)
        or HEADING_WORD_RE.match(stripped)
        or BULLET_RE.match(stripped)
        or stripped.lower().startswith("таблица ")
    )


def _classify_kind(text: str, heading_max_chars: int) -> str:
    stripped = text.strip()
    if _is_table_row(stripped):
        return "table_row"
    if _is_heading(stripped, heading_max_chars):
        return "heading"
    if BULLET_RE.match(stripped):
        return "list_item"
    return "paragraph"


def _is_heading(text: str, heading_max_chars: int) -> bool:
    stripped = text.strip()
    is_heading = bool(
        HEADING_NUMBER_RE.match(stripped) or HEADING_WORD_RE.match(stripped)
    )
    return bool(
        is_heading
        and len(stripped) <= heading_max_chars
        and not SENTENCE_END_RE.search(stripped)
    )


def _is_table_row(text: str) -> bool:
    return bool(TABLE_RE.search(text.strip()))


def _join_lines(parts: Sequence[str]) -> str:
    if not parts:
        return ""
    result = parts[0].strip()
    for part in parts[1:]:
        current = part.strip()
        if not current:
            continue
        if result.endswith("-") and current[:1].islower():
            result = result[:-1] + current
        elif current[:1] in ",.;:)]}":
            result += current
        else:
            result += " " + current
    return " ".join(result.split())
