from __future__ import annotations

import asyncio
from pathlib import Path

from rag_indexer.extraction.docx import DocxExtractor
from rag_indexer.extraction.html import HtmlExtractor
from rag_indexer.extraction.models import ExtractedDocument, ExtractionError
from rag_indexer.extraction.pdf import ExtractionOptions, PdfExtractor
from rag_indexer.extraction.text import TextExtractor
from rag_indexer.ocr.models import OcrEngine


class DocumentExtractor:
    def __init__(self, options: ExtractionOptions | None = None) -> None:
        self._options = options or ExtractionOptions()

    async def extract(
        self,
        path: Path,
        ocr_engine: OcrEngine | None = None,
    ) -> ExtractedDocument:
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return await PdfExtractor(self._options).extract(path, ocr_engine)
        if suffix == ".docx":
            return await asyncio.to_thread(DocxExtractor().extract, path)
        if suffix in {".html", ".htm"}:
            return await asyncio.to_thread(HtmlExtractor().extract, path)
        if suffix in {".txt", ".md"}:
            return await asyncio.to_thread(TextExtractor().extract, path)
        raise ExtractionError(f"unsupported document type: {suffix or path.name}")
