from __future__ import annotations

from dataclasses import dataclass

from rag_indexer.ocr.base import BaseOcrEngine
from rag_indexer.ocr.models import (
    OcrDocument,
    OcrEngineError,
    OcrOptions,
    OcrPage,
    PageImage,
)


@dataclass(frozen=True)
class FallbackPolicy:
    min_confidence: float = 0.7
    min_chars: int = 20
    fallback_on_error: bool = True
    fallback_low_quality: bool = True
    prefer_fallback_if_better: bool = False


def _quality(page: OcrPage) -> tuple[float, int]:
    return (page.average_confidence, len(page.text))


class FallbackOcrEngine(BaseOcrEngine):
    name = "fallback"

    def __init__(
        self,
        primary: BaseOcrEngine,
        fallback: BaseOcrEngine,
        policy: FallbackPolicy | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._policy = policy or FallbackPolicy()

    async def recognize(
        self,
        pages: list[PageImage],
        options: OcrOptions,
    ) -> OcrDocument:
        recognized: list[OcrPage] = []
        fallback_count = 0
        for page in pages:
            result = await self._recognize_page(page, options)
            if result.fallback_reason is not None:
                fallback_count += 1
            recognized.append(result)
        return OcrDocument(
            pages=recognized,
            metadata={
                "primary": self._primary.name,
                "fallback": self._fallback.name,
                "pages_with_fallback": fallback_count,
            },
        )

    async def _recognize_page(
        self,
        page: PageImage,
        options: OcrOptions,
    ) -> OcrPage:
        primary_page: OcrPage | None = None
        primary_error: OcrEngineError | None = None
        try:
            primary_page = await self._primary.recognize_page(page, options)
        except OcrEngineError as error:
            primary_error = error
            if not self._policy.fallback_on_error:
                raise

        needs_fallback = primary_page is None or (
            self._policy.fallback_low_quality and self._is_low_quality(primary_page, options)
        )
        if not needs_fallback:
            if primary_page is None:
                raise OcrEngineError(f"primary OCR returned no page {page.page_number}")
            if self._policy.prefer_fallback_if_better:
                fallback_page = await self._safe_fallback(page, options)
                if fallback_page is not None and _quality(fallback_page) > _quality(primary_page):
                    fallback_page.fallback_reason = "better_quality"
                    return fallback_page
            return primary_page

        fallback_page = await self._safe_fallback(page, options)
        if fallback_page is not None and not fallback_page.lines and primary_page is not None:
            return primary_page
        if fallback_page is not None:
            if primary_error is not None:
                fallback_page.fallback_reason = f"primary_error: {primary_error}"
            elif primary_page is not None:
                fallback_page.fallback_reason = (
                    "low_quality: "
                    f"confidence={primary_page.average_confidence:.3f}, "
                    f"chars={len(primary_page.text)}"
                )
            return fallback_page
        if primary_page is not None:
            return primary_page
        raise OcrEngineError(
            f"both OCR engines failed for page {page.page_number}"
        ) from primary_error

    async def _safe_fallback(
        self,
        page: PageImage,
        options: OcrOptions,
    ) -> OcrPage | None:
        try:
            return await self._fallback.recognize_page(page, options)
        except OcrEngineError:
            return None

    def _is_low_quality(self, page: OcrPage, options: OcrOptions) -> bool:
        threshold = max(self._policy.min_confidence, options.min_confidence)
        min_chars = max(self._policy.min_chars, options.min_chars)
        if not page.lines:
            return True
        if len(page.text) < min_chars:
            return True
        return page.average_confidence < threshold

    async def close(self) -> None:
        await self._primary.close()
        await self._fallback.close()
