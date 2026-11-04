from __future__ import annotations

from pathlib import Path

from rag_indexer.extraction import (
    BoilerplateFilter,
    ExtractionOptions,
    LineToParagraphMerger,
    PdfExtractor,
)
from rag_indexer.extraction.boilerplate import normalize_boilerplate_text
from rag_indexer.ocr import BBox, OcrLine, OcrPage
from rag_indexer.pdf import detect_pdf_text_layer

HEADER = "энер г е ти к а инно в аций"
FOOTER = "ИНН/КПП 7603051960/760301001"
BODY = "1. Настоящая инструкция применяется во всех случаях приемки."


def _line(text: str, top: int, page: int) -> OcrLine:
    return OcrLine(
        text=text,
        bbox=BBox(10, top, 500, top + 20),
        confidence=0.95,
        page_number=page,
    )


def _page(page_number: int, body_top: int = 200) -> OcrPage:
    return OcrPage(
        page_number=page_number,
        width=600,
        height=800,
        lines=[
            _line(HEADER, 10, page_number),
            _line(BODY, body_top, page_number),
            _line(FOOTER, 760, page_number),
        ],
        engine="paddleocr",
    )


def test_removes_repeated_header_and_footer() -> None:
    result = BoilerplateFilter().apply([_page(1), _page(2), _page(3)])

    assert result.removed
    assert len(result.pages) == 3
    assert all(len(page.lines) == 1 for page in result.pages)
    assert result.pages[0].lines[0].text == BODY
    assert normalize_boilerplate_text(HEADER) in result.repeated_texts
    assert normalize_boilerplate_text(FOOTER) in result.repeated_texts
    assert "#" not in result.repeated_texts


def test_does_not_remove_repeated_text_in_body() -> None:
    pages = [_page(page_number, body_top=200) for page_number in (1, 2, 3)]
    pages[0] = OcrPage(
        page_number=1,
        width=600,
        height=800,
        lines=[_line(HEADER, 200, 1), _line(BODY, 220, 1)],
        engine="paddleocr",
    )

    result = BoilerplateFilter().apply(pages)

    assert result.pages[0].lines[0].text == HEADER


def test_strips_header_prefix_and_keeps_body() -> None:
    bodies = {
        1: "Первый пункт.",
        2: "Второй пункт.",
        3: "Третий пункт.",
    }
    pages = [
        OcrPage(
            page_number=page_number,
            width=600,
            height=800,
            lines=[
                _line(f"{HEADER} {body}", 10, page_number),
                _line(body, 200, page_number),
            ],
            engine="paddleocr",
        )
        for page_number, body in bodies.items()
    ]

    result = BoilerplateFilter().apply(pages)

    assert result.pages[0].lines[0].text == "Первый пункт."
    assert any(item.reason == "prefix" for item in result.removed)


def test_strips_header_prefix_with_page_number() -> None:
    suffixes = ["Продолжение", "Таблица", "Примечание"]
    pages = [
        OcrPage(
            page_number=index,
            width=600,
            height=800,
            lines=[
                _line(f"{index} ГОСТ 7000-80 {suffix}", 10, index),
                _line(BODY, 200, index),
            ],
            engine="paddleocr",
        )
        for index, suffix in enumerate(suffixes, start=1)
    ]

    result = BoilerplateFilter().apply(pages)

    assert result.pages[0].lines[0].text == "Продолжение"
    assert any(item.reason == "prefix" for item in result.removed)


def test_single_page_is_not_filtered() -> None:
    result = BoilerplateFilter().apply([_page(1)])

    assert len(result.pages[0].lines) == 3
    assert result.removed == []


def test_pdf_extractor_reports_boilerplate_removal() -> None:
    page_text = f"{HEADER}\n{BODY}\n{FOOTER}"
    report = detect_pdf_text_layer(
        Path("document.pdf"),
        page_texts=[page_text, page_text, page_text],
    )

    document = PdfExtractor.build_document(
        Path("document.pdf"),
        report,
        {1: (600, 800), 2: (600, 800), 3: (600, 800)},
        None,
        ExtractionOptions(),
        LineToParagraphMerger(),
    )

    assert HEADER not in document.text
    assert FOOTER not in document.text
    assert document.metadata["boilerplate_removed"] == 6
