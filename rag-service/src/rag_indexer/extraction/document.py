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
        *,
        mime: str | None = None,
        original_name: str | None = None,
    ) -> ExtractedDocument:
        path = Path(path)
        suffix = path.suffix.lower() or Path(original_name or "").suffix.lower()
        if not suffix:
            suffix = _suffix_from_mime(mime)
        if suffix == ".pdf":
            return await PdfExtractor(self._options).extract(path, ocr_engine)
        if suffix == ".docx":
            return await asyncio.to_thread(DocxExtractor().extract, path)
        if suffix in {".html", ".htm"}:
            return await asyncio.to_thread(HtmlExtractor().extract, path)
        if suffix in {".txt", ".md"}:
            return await asyncio.to_thread(TextExtractor().extract, path)
        raise ExtractionError(f"unsupported document type: {suffix or path.name}")


def _suffix_from_mime(mime: str | None) -> str:
    if not mime:
        return ""
    normalized = mime.split(";", 1)[0].strip().lower()
    return {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/html": ".html",
        "application/xhtml+xml": ".html",
        "text/plain": ".txt",
        "text/markdown": ".md",
    }.get(normalized, "")
