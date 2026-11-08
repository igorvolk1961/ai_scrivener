from __future__ import annotations

from rag_indexer.extraction import LineToParagraphMerger
from rag_indexer.ocr import BBox, OcrLine


def _line(
    text: str,
    top: int,
    *,
    left: int = 10,
    page: int = 1,
    confidence: float = 0.95,
) -> OcrLine:
    return OcrLine(
        text=text,
        bbox=BBox(left, top, left + 400, top + 20),
        confidence=confidence,
        page_number=page,
    )


def test_merges_lines_into_paragraph() -> None:
    blocks = LineToParagraphMerger().merge(
        [
            _line("Настоящая инструкция применяется во всех", 0),
            _line("случаях приемки продукции.", 22),
        ],
        page_widths={1: 1000},
    )

    assert len(blocks) == 1
    assert blocks[0].kind == "paragraph"
    assert blocks[0].text == ("Настоящая инструкция применяется во всех случаях приемки продукции.")


def test_starts_new_block_after_sentence_and_capital() -> None:
    blocks = LineToParagraphMerger().merge(
        [
            _line("Первый абзац закончен.", 0),
            _line("Второй абзац начинается.", 22),
        ],
        page_widths={1: 1000},
    )

    assert len(blocks) == 2


def test_starts_new_block_on_clause_number() -> None:
    blocks = LineToParagraphMerger().merge(
        [
            _line("1. Настоящая инструкция применяется.", 0),
            _line("2. Получатель обязан принять товар.", 22),
        ],
        page_widths={1: 1000},
    )

    assert len(blocks) == 2
    assert blocks[0].text.startswith("1.")
    assert blocks[1].text.startswith("2.")


def test_joins_hyphenated_line() -> None:
    blocks = LineToParagraphMerger().merge(
        [
            _line("государствен-", 0),
            _line("ной приемки", 22),
        ],
        page_widths={1: 1000},
    )

    assert len(blocks) == 1
    assert "государственной приемки" in blocks[0].text


def test_starts_new_block_on_vertical_gap() -> None:
    blocks = LineToParagraphMerger().merge(
        [
            _line("Первый абзац", 0),
            _line("Второй абзац", 80),
        ],
        page_widths={1: 1000},
    )

    assert len(blocks) == 2


def test_classifies_heading() -> None:
    blocks = LineToParagraphMerger().merge(
        [_line("1 Область применения", 0)],
        page_widths={1: 1000},
    )

    assert len(blocks) == 1
    assert blocks[0].kind == "heading"


def test_date_line_is_not_a_heading() -> None:
    blocks = LineToParagraphMerger().merge(
        [_line("1965 г. N П-6 (с изменениями, внесенными постановлениями)", 0)],
        page_widths={1: 1000},
    )

    assert blocks[0].kind == "paragraph"


def test_keeps_text_layer_lines_without_bbox() -> None:
    blocks = LineToParagraphMerger().merge(
        [
            OcrLine(
                text="1. Первый пункт.",
                bbox=None,
                confidence=1.0,
                page_number=1,
            ),
            OcrLine(
                text="2. Второй пункт.",
                bbox=None,
                confidence=1.0,
                page_number=1,
            ),
        ],
        engine_by_page={1: "text_layer"},
    )

    assert len(blocks) == 2
    assert blocks[0].engine == "text_layer"
