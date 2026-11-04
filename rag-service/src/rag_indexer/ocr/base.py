from __future__ import annotations

from rag_indexer.ocr.models import (
    OcrDocument,
    OcrEngineError,
    OcrOptions,
    OcrPage,
    PageImage,
)


class BaseOcrEngine:
    name = "base"

    async def recognize(
        self,
        pages: list[PageImage],
        options: OcrOptions,
    ) -> OcrDocument:
        recognized = [await self.recognize_page(page, options) for page in pages]
        return OcrDocument(
            pages=recognized,
            metadata={"engine": self.name},
        )

    async def recognize_page(
        self,
        page: PageImage,
        options: OcrOptions,
    ) -> OcrPage:
        raise OcrEngineError(f"{self.name} does not implement recognize_page")

    async def close(self) -> None:
        return None
