from __future__ import annotations

import asyncio
from pathlib import Path

from rag_indexer.ocr import (
    BaseOcrEngine,
    BBox,
    FallbackOcrEngine,
    FallbackPolicy,
    OcrEngineError,
    OcrLine,
    OcrOptions,
    OcrPage,
    PaddleOcrEngine,
    PageImage,
    YandexOcrEngine,
)


class FakeEngine(BaseOcrEngine):
    def __init__(
        self,
        name: str,
        *,
        text: str = "Распознанный текст пункта",
        confidence: float = 0.95,
        error_pages: set[int] | None = None,
    ) -> None:
        self.name = name
        self._text = text
        self._confidence = confidence
        self._error_pages = error_pages or set()
        self.calls: list[int] = []

    async def recognize_page(
        self,
        page: PageImage,
        options: OcrOptions,
    ) -> OcrPage:
        self.calls.append(page.page_number)
        if page.page_number in self._error_pages:
            raise OcrEngineError(f"{self.name} failed")
        lines = []
        if self._text:
            lines.append(
                OcrLine(
                    text=self._text,
                    bbox=BBox(0, 0, 100, 20),
                    confidence=self._confidence,
                    page_number=page.page_number,
                )
            )
        return OcrPage(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            lines=lines,
            engine=self.name,
        )


def _page(number: int = 1) -> PageImage:
    return PageImage(
        page_number=number,
        path=Path("page.png"),
        width=100,
        height=100,
    )


def test_router_keeps_primary_when_quality_is_good() -> None:
    primary = FakeEngine("paddleocr")
    fallback = FakeEngine("yandex")
    router = FallbackOcrEngine(primary, fallback)

    result = asyncio.run(router.recognize([_page()], OcrOptions()))

    assert result.pages[0].engine == "paddleocr"
    assert fallback.calls == []
    assert result.metadata["pages_with_fallback"] == 0


def test_router_falls_back_on_error() -> None:
    primary = FakeEngine("paddleocr", error_pages={1})
    fallback = FakeEngine("yandex")
    router = FallbackOcrEngine(primary, fallback)

    result = asyncio.run(router.recognize([_page()], OcrOptions()))

    assert result.pages[0].engine == "yandex"
    reason = result.pages[0].fallback_reason
    assert reason is not None
    assert reason.startswith("primary_error")
    assert result.metadata["pages_with_fallback"] == 1


def test_router_falls_back_on_low_confidence() -> None:
    primary = FakeEngine("paddleocr", confidence=0.2)
    fallback = FakeEngine("yandex")
    router = FallbackOcrEngine(primary, fallback)

    result = asyncio.run(router.recognize([_page()], OcrOptions(min_confidence=0.7)))

    assert result.pages[0].engine == "yandex"
    reason = result.pages[0].fallback_reason
    assert reason is not None
    assert reason.startswith("low_quality")


def test_router_falls_back_per_page() -> None:
    primary = FakeEngine("paddleocr", error_pages={2})
    fallback = FakeEngine("yandex")
    router = FallbackOcrEngine(
        primary,
        fallback,
        FallbackPolicy(fallback_low_quality=False),
    )

    result = asyncio.run(router.recognize([_page(1), _page(2)], OcrOptions()))

    assert [page.engine for page in result.pages] == ["paddleocr", "yandex"]
    assert primary.calls == [1, 2]
    assert fallback.calls == [2]


def test_router_keeps_primary_if_fallback_is_empty() -> None:
    primary = FakeEngine("paddleocr", confidence=0.2)
    fallback = FakeEngine("yandex", text="")
    router = FallbackOcrEngine(primary, fallback)

    result = asyncio.run(router.recognize([_page()], OcrOptions(min_confidence=0.7)))

    assert result.pages[0].engine == "paddleocr"


def test_yandex_parser_maps_lines_and_confidence() -> None:
    payload = {
        "result": {
            "textAnnotation": {
                "blocks": [
                    {
                        "lines": [
                            {
                                "text": "Пункт 4.2.1",
                                "boundingBox": {
                                    "vertices": [
                                        {"x": 10, "y": 20},
                                        {"x": 100, "y": 20},
                                        {"x": 100, "y": 40},
                                        {"x": 10, "y": 40},
                                    ]
                                },
                                "confidence": 0.93,
                            }
                        ]
                    }
                ]
            }
        }
    }

    page = YandexOcrEngine._parse_response(_page(), payload)

    assert page.engine == "yandex"
    assert page.lines[0].text == "Пункт 4.2.1"
    assert page.lines[0].bbox == BBox(10, 20, 100, 40)
    assert page.lines[0].confidence == 0.93


def test_paddle_parser_maps_boxes_and_scores() -> None:
    item = {
        "rec_texts": ["Пункт 4.2.1"],
        "rec_scores": [0.91],
        "rec_boxes": [[10, 20, 100, 40]],
    }

    page = PaddleOcrEngine._parse_result(_page(), item)

    assert page.engine == "paddleocr"
    assert page.lines[0].text == "Пункт 4.2.1"
    assert page.lines[0].bbox == BBox(10, 20, 100, 40)
    assert page.lines[0].confidence == 0.91
