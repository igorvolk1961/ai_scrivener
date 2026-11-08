from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TextLayerOptions:
    min_chars_per_page: int = 80
    min_words_per_page: int = 10
    min_printable_ratio: float = 0.8
    min_content_ratio: float = 0.5


@dataclass(frozen=True)
class PageTextLayer:
    page_number: int
    text: str
    char_count: int
    word_count: int
    printable_ratio: float
    content_ratio: float
    is_textual: bool


@dataclass
class TextLayerReport:
    pages: list[PageTextLayer] = field(default_factory=list)

    @property
    def textual_pages(self) -> list[PageTextLayer]:
        return [page for page in self.pages if page.is_textual]

    @property
    def scanned_pages(self) -> list[PageTextLayer]:
        return [page for page in self.pages if not page.is_textual]

    @property
    def coverage(self) -> float:
        if not self.pages:
            return 0.0
        return len(self.textual_pages) / len(self.pages)

    @property
    def requires_ocr(self) -> bool:
        return bool(self.scanned_pages)

    @property
    def fully_textual(self) -> bool:
        return bool(self.pages) and not self.requires_ocr


def classify_page_text(
    page_number: int,
    text: str,
    options: TextLayerOptions | None = None,
) -> PageTextLayer:
    resolved = options or TextLayerOptions()
    normalized = text.strip()
    char_count = len(normalized)
    word_count = len(normalized.split())
    printable_ratio = sum(1 for char in text if char.isprintable()) / len(text) if text else 0.0
    content_ratio = (
        sum(1 for char in normalized if char.isalnum()) / char_count if char_count else 0.0
    )
    is_textual = (
        char_count >= resolved.min_chars_per_page
        and word_count >= resolved.min_words_per_page
        and printable_ratio >= resolved.min_printable_ratio
        and content_ratio >= resolved.min_content_ratio
    )
    return PageTextLayer(
        page_number=page_number,
        text=normalized,
        char_count=char_count,
        word_count=word_count,
        printable_ratio=printable_ratio,
        content_ratio=content_ratio,
        is_textual=is_textual,
    )


def _extract_page_texts(path: Path) -> list[str]:
    try:
        import pypdfium2 as pdfium
    except ImportError as error:
        raise RuntimeError(
            "pypdfium2 is required for PDF text-layer detection; install the 'indexer' extra"
        ) from error
    document = pdfium.PdfDocument(str(path))
    try:
        texts: list[str] = []
        for index in range(len(document)):
            page = document[index]
            text_page = page.get_textpage()
            texts.append(text_page.get_text_range())
        return texts
    finally:
        document.close()


def detect_pdf_text_layer(
    path: Path,
    options: TextLayerOptions | None = None,
    *,
    page_texts: Sequence[str] | None = None,
) -> TextLayerReport:
    texts = list(page_texts) if page_texts is not None else _extract_page_texts(path)
    return TextLayerReport(
        pages=[classify_page_text(index + 1, text, options) for index, text in enumerate(texts)]
    )
