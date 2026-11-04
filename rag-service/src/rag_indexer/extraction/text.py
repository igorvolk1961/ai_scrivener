from __future__ import annotations

from pathlib import Path

from rag_indexer.extraction.merger import LineToParagraphMerger
from rag_indexer.extraction.models import ExtractedDocument
from rag_indexer.ocr.models import OcrDocument, OcrLine, OcrPage


class TextExtractor:
    def extract(self, path: Path) -> ExtractedDocument:
        text = _read_text(path)
        lines = [
            OcrLine(
                text=line.strip(),
                bbox=None,
                confidence=1.0,
                page_number=1,
            )
            for line in text.splitlines()
            if line.strip()
        ]
        pages = [
            OcrPage(
                page_number=1,
                width=0,
                height=0,
                lines=lines,
                engine="text",
            )
        ]
        blocks = LineToParagraphMerger().merge_document(OcrDocument(pages=pages))
        return ExtractedDocument(
            source_path=path,
            title=path.stem,
            page_count=1,
            blocks=blocks,
            metadata={"mime": "text/plain", "engines": ["text"]},
        )


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
