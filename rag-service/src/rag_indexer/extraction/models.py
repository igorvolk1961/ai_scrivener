from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag_indexer.ocr.models import BBox


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Block:
    text: str
    page_start: int
    page_end: int
    kind: str
    engine: str
    confidence: float
    bbox: BBox | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedDocument:
    source_path: Path
    title: str
    page_count: int
    blocks: list[Block]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)
