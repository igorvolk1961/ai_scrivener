from __future__ import annotations

from pathlib import Path

from rag_indexer.pdf import (
    TextLayerOptions,
    classify_page_text,
    detect_pdf_text_layer,
)

TEXT_PAGE = (
    "1. Настоящая инструкция применяется во всех случаях, когда стандартами "
    "и техническими условиями не установлен другой порядок приемки продукции. "
    "2. Получатель обязан обеспечить приемку товаров по количеству и качеству."
)


def test_classify_text_page_as_textual() -> None:
    page = classify_page_text(1, TEXT_PAGE)

    assert page.is_textual is True
    assert page.char_count >= 80
    assert page.word_count >= 10
    assert page.content_ratio > 0.5


def test_classify_empty_page_as_scanned() -> None:
    page = classify_page_text(2, "   \n\t ")

    assert page.is_textual is False
    assert page.char_count == 0


def test_classify_garbage_as_scanned() -> None:
    page = classify_page_text(3, "### %%% *** !!! " * 20)

    assert page.char_count >= 80
    assert page.is_textual is False
    assert page.content_ratio < 0.5


def test_detect_mixed_pdf_requires_ocr_for_scanned_pages() -> None:
    report = detect_pdf_text_layer(
        Path("document.pdf"),
        page_texts=[TEXT_PAGE, "", TEXT_PAGE],
    )

    assert report.coverage == 2 / 3
    assert report.requires_ocr is True
    assert report.fully_textual is False
    assert [page.page_number for page in report.scanned_pages] == [2]


def test_detect_textual_pdf_does_not_require_ocr() -> None:
    report = detect_pdf_text_layer(
        Path("document.pdf"),
        page_texts=[TEXT_PAGE, TEXT_PAGE],
    )

    assert report.requires_ocr is False
    assert report.fully_textual is True
    assert report.coverage == 1.0


def test_detect_with_custom_thresholds() -> None:
    report = detect_pdf_text_layer(
        Path("document.pdf"),
        TextLayerOptions(min_chars_per_page=10, min_words_per_page=2),
        page_texts=["Короткий текст"],
    )

    assert report.fully_textual is True
