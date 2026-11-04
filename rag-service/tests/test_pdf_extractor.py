from __future__ import annotations

from pathlib import Path

import pytest

from rag_indexer.extraction import (
    ExtractedDocument,
    ExtractionError,
    ExtractionOptions,
    LineToParagraphMerger,
    PdfExtractor,
)
from rag_indexer.ocr import OcrDocument, OcrLine, OcrPage
from rag_indexer.pdf import detect_pdf_text_layer

TEXT_PAGE = (
    "1. Настоящая инструкция применяется во всех случаях, когда стандартами "
    "и техническими условиями не установлен другой порядок приемки продукции. "
    "2. Получатель обязан обеспечить приемку товаров по количеству и качеству."
)


def _ocr_document(page_number: int = 2) -> OcrDocument:
    return OcrDocument(
        pages=[
            OcrPage(
                page_number=page_number,
                width=600,
                height=800,
                lines=[
                    OcrLine(
                        text="Сканированная страница с текстом.",
                        bbox=None,
                        confidence=0.9,
                        page_number=page_number,
                    )
                ],
                engine="paddleocr",
            )
        ]
    )


def test_build_document_combines_text_layer_and_ocr() -> None:
    report = detect_pdf_text_layer(
        Path("document.pdf"),
        page_texts=[TEXT_PAGE, ""],
    )

    document = PdfExtractor.build_document(
        Path("document.pdf"),
        report,
        {1: (600, 800), 2: (600, 800)},
        _ocr_document(),
        ExtractionOptions(),
        LineToParagraphMerger(),
    )

    assert isinstance(document, ExtractedDocument)
    assert document.page_count == 2
    assert document.metadata["text_layer_coverage"] == 0.5
    assert document.metadata["ocr_pages"] == [2]
    assert "text_layer" in document.metadata["engines"]
    assert "paddleocr" in document.metadata["engines"]
    assert "Сканированная страница" in document.text


def test_build_document_requires_ocr_page_for_scanned_page() -> None:
    report = detect_pdf_text_layer(
        Path("document.pdf"),
        page_texts=["", TEXT_PAGE],
    )

    with pytest.raises(ExtractionError):
        PdfExtractor.build_document(
            Path("document.pdf"),
            report,
            {1: (600, 800), 2: (600, 800)},
            None,
            ExtractionOptions(),
            LineToParagraphMerger(),
        )


def test_build_document_uses_text_layer_without_ocr() -> None:
    report = detect_pdf_text_layer(
        Path("document.pdf"),
        page_texts=[TEXT_PAGE],
    )

    document = PdfExtractor.build_document(
        Path("document.pdf"),
        report,
        {1: (600, 800)},
        None,
        ExtractionOptions(),
        LineToParagraphMerger(),
    )

    assert document.metadata["ocr_pages"] == []
    assert document.metadata["engines"] == ["text_layer"]
    assert "Настоящая инструкция" in document.text
