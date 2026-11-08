from __future__ import annotations

from rag_indexer.extraction import Block, clean_block_headers


def _block(text: str) -> Block:
    return Block(
        text=text,
        page_start=1,
        page_end=1,
        kind="paragraph",
        engine="text_layer",
        confidence=1.0,
    )


def test_strips_page_header_and_continuation_marker() -> None:
    blocks = clean_block_headers([_block("2 ГОСТ 7000-80 Продолжение таблицы")])

    assert len(blocks) == 1
    assert blocks[0].text == "таблицы"


def test_strips_page_marker_before_header() -> None:
    blocks = clean_block_headers([_block("С. 2 ГОСТ 7000-80 Продолжение таблицы")])

    assert len(blocks) == 1
    assert blocks[0].text == "таблицы"


def test_strips_page_header_and_ocr_list_prefix() -> None:
    blocks = clean_block_headers([_block("ГОСТ 12.3.020-80 С. 2 и2.2. На транспортных путях")])

    assert len(blocks) == 1
    assert blocks[0].text == "2.2. На транспортных путях"


def test_keeps_normal_gost_reference() -> None:
    blocks = clean_block_headers([_block("ГОСТ 8737 устанавливает требования к упаковке.")])

    assert blocks[0].text == "ГОСТ 8737 устанавливает требования к упаковке."


def test_keeps_clause_block_unchanged() -> None:
    blocks = clean_block_headers([_block("1.1. Текстильные материалы")])

    assert blocks[0].text == "1.1. Текстильные материалы"


def test_drops_block_if_only_header_remains() -> None:
    blocks = clean_block_headers([_block("ГОСТ 7000-80 С. 5")])

    assert blocks == []
