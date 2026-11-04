from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from rag_indexer.ocr.models import OcrLine, OcrPage

DIGITS_RE = re.compile(r"\d+")
MIN_PREFIX_TOKENS = 2


@dataclass(frozen=True)
class BoilerplateOptions:
    min_pages: int = 3
    min_page_ratio: float = 0.5
    edge_lines: int = 2
    top_zone_ratio: float = 0.12
    bottom_zone_ratio: float = 0.12
    min_chars: int = 3
    max_chars: int = 200


@dataclass(frozen=True)
class RemovedLine:
    page_number: int
    text: str
    reason: str


@dataclass
class BoilerplateResult:
    pages: list[OcrPage]
    removed: list[RemovedLine] = field(default_factory=list)
    repeated_texts: list[str] = field(default_factory=list)


def normalize_boilerplate_text(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return DIGITS_RE.sub("#", normalized).strip()


def _common_token_prefix(texts: Sequence[str]) -> str:
    if not texts:
        return ""
    token_lists = [text.split() for text in texts]
    prefix: list[str] = []
    for tokens in zip(*token_lists, strict=False):
        if len(set(tokens)) == 1:
            prefix.append(tokens[0])
            continue
        break
    return " ".join(prefix)


def _is_edge_line(
    line: OcrLine,
    index: int,
    line_count: int,
    page_height: int,
    options: BoilerplateOptions,
) -> bool:
    if line.bbox is not None and page_height > 0:
        center = (line.bbox.y0 + line.bbox.y1) / 2
        return (
            center <= page_height * options.top_zone_ratio
            or center >= page_height * (1 - options.bottom_zone_ratio)
        )
    effective = max(1, min(options.edge_lines, line_count // 3))
    return index < effective or index >= line_count - effective


class BoilerplateFilter:
    def __init__(self, options: BoilerplateOptions | None = None) -> None:
        self._options = options or BoilerplateOptions()

    def apply(self, pages: Sequence[OcrPage]) -> BoilerplateResult:
        if len(pages) < self._options.min_pages:
            return BoilerplateResult(pages=list(pages))
        threshold = max(
            self._options.min_pages,
            math.ceil(len(pages) * self._options.min_page_ratio),
        )
        pages_with_text = self._collect_repeated(pages, threshold)
        if not pages_with_text:
            return BoilerplateResult(pages=list(pages))
        repeated = set(pages_with_text)
        filtered: list[OcrPage] = []
        removed: list[RemovedLine] = []
        for page in pages:
            new_lines: list[OcrLine] = []
            for index, line in enumerate(page.lines):
                if not _is_edge_line(
                    line,
                    index,
                    len(page.lines),
                    page.height,
                    self._options,
                ):
                    new_lines.append(line)
                    continue
                normalized = normalize_boilerplate_text(line.text)
                if normalized in repeated:
                    removed.append(
                        RemovedLine(
                            page_number=page.page_number,
                            text=line.text,
                            reason="exact",
                        )
                    )
                    continue
                stripped = self._strip_prefix(line, repeated)
                if stripped is not None:
                    new_lines.append(stripped)
                    removed.append(
                        RemovedLine(
                            page_number=page.page_number,
                            text=line.text[: len(line.text) - len(stripped.text)].strip(),
                            reason="prefix",
                        )
                    )
                    continue
                new_lines.append(line)
            if not new_lines:
                new_lines = list(page.lines)
            filtered.append(
                OcrPage(
                    page_number=page.page_number,
                    width=page.width,
                    height=page.height,
                    lines=new_lines,
                    engine=page.engine,
                )
            )
        return BoilerplateResult(
            pages=filtered,
            removed=removed,
            repeated_texts=sorted(repeated),
        )

    def _collect_repeated(
        self,
        pages: Sequence[OcrPage],
        threshold: int,
    ) -> dict[str, set[int]]:
        occurrences: dict[str, set[int]] = {}
        for page in pages:
            for index, line in enumerate(page.lines):
                if not _is_edge_line(
                    line,
                    index,
                    len(page.lines),
                    page.height,
                    self._options,
                ):
                    continue
                normalized = normalize_boilerplate_text(line.text)
                if (
                    len(normalized) < self._options.min_chars
                    or len(normalized) > self._options.max_chars
                ):
                    continue
                occurrences.setdefault(normalized, set()).add(page.page_number)
        repeated = {
            text: page_numbers
            for text, page_numbers in occurrences.items()
            if len(page_numbers) >= threshold
        }
        for prefix in self._common_edge_prefixes(pages, threshold):
            if prefix and len(prefix) <= self._options.max_chars:
                repeated.setdefault(prefix, {page.page_number for page in pages})
        return repeated

    def _common_edge_prefixes(
        self,
        pages: Sequence[OcrPage],
        threshold: int,
    ) -> set[str]:
        prefixes: set[str] = set()
        for edge in ("top", "bottom"):
            texts: list[str] = []
            for page in pages:
                edge_lines = [
                    line
                    for index, line in enumerate(page.lines)
                    if _is_edge_line(
                        line,
                        index,
                        len(page.lines),
                        page.height,
                        self._options,
                    )
                ]
                if not edge_lines:
                    continue
                line = edge_lines[0] if edge == "top" else edge_lines[-1]
                normalized = normalize_boilerplate_text(line.text)
                if normalized:
                    texts.append(normalized)
            if len(texts) < threshold:
                continue
            prefix = _common_token_prefix(texts)
            if len(prefix.split()) >= MIN_PREFIX_TOKENS:
                prefixes.add(prefix)
        return prefixes

    def _strip_prefix(
        self,
        line: OcrLine,
        repeated: set[str],
    ) -> OcrLine | None:
        original_tokens = line.text.split()
        normalized_tokens = [
            normalize_boilerplate_text(token) for token in original_tokens
        ]
        for text in sorted(repeated, key=len, reverse=True):
            prefix_tokens = text.split()
            if len(text) < self._options.min_chars:
                continue
            if len(prefix_tokens) >= len(original_tokens):
                continue
            if normalized_tokens[: len(prefix_tokens)] != prefix_tokens:
                continue
            remainder = " ".join(original_tokens[len(prefix_tokens) :]).lstrip(
                " .:;—-"
            )
            if not remainder:
                continue
            return OcrLine(
                text=remainder,
                bbox=line.bbox,
                confidence=line.confidence,
                page_number=line.page_number,
            )
        return None
