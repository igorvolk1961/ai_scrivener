from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class OcrEngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class BBox:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return max(0, self.x1 - self.x0)

    @property
    def height(self) -> int:
        return max(0, self.y1 - self.y0)


@dataclass(frozen=True)
class PageImage:
    page_number: int
    path: Path
    width: int
    height: int
    mime_type: str = "image/png"


@dataclass(frozen=True)
class OcrLine:
    text: str
    bbox: BBox | None
    confidence: float
    page_number: int


@dataclass
class OcrPage:
    page_number: int
    width: int
    height: int
    lines: list[OcrLine]
    engine: str
    fallback_reason: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def average_confidence(self) -> float:
        if not self.lines:
            return 0.0
        return sum(line.confidence for line in self.lines) / len(self.lines)


@dataclass
class OcrDocument:
    pages: list[OcrPage]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OcrOptions:
    languages: tuple[str, ...] = ("ru", "en")
    model: str = "page"
    min_confidence: float = 0.7
    min_chars: int = 20


class OcrEngine(Protocol):
    name: str

    async def recognize(self, pages: list[PageImage], options: OcrOptions) -> OcrDocument: ...

    async def close(self) -> None: ...
