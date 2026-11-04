from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag_indexer.extraction.boilerplate import BoilerplateFilter, BoilerplateOptions
from rag_indexer.extraction.headers import clean_block_headers
from rag_indexer.extraction.merger import LineToParagraphMerger, MergerOptions
from rag_indexer.extraction.models import ExtractedDocument, ExtractionError
from rag_indexer.extraction.tables import (
    PdfTable,
    extract_pdf_tables,
    merge_table_blocks,
)
from rag_indexer.ocr.models import (
    OcrDocument,
    OcrEngine,
    OcrLine,
    OcrOptions,
    OcrPage,
    PageImage,
)
from rag_indexer.pdf.text_layer import (
    PageTextLayer,
    TextLayerOptions,
    TextLayerReport,
    detect_pdf_text_layer,
)


@dataclass(frozen=True)
class ExtractionOptions:
    render_dpi: int = 150
    text_layer: TextLayerOptions = field(default_factory=TextLayerOptions)
    ocr: OcrOptions = field(default_factory=OcrOptions)
    merger: MergerOptions = field(default_factory=MergerOptions)
    boilerplate: BoilerplateOptions = field(default_factory=BoilerplateOptions)
    extract_tables: bool = True


def _load_pdfium() -> Any:
    try:
        import pypdfium2 as pdfium
    except ImportError as error:
        raise ExtractionError(
            "pypdfium2 is required for PDF extraction; install the 'indexer' extra"
        ) from error
    return pdfium


def _page_sizes(path: Path) -> dict[int, tuple[int, int]]:
    pdfium = _load_pdfium()
    document = pdfium.PdfDocument(str(path))
    try:
        sizes: dict[int, tuple[int, int]] = {}
        for index in range(len(document)):
            width, height = document[index].get_size()
            sizes[index + 1] = (int(width), int(height))
        return sizes
    finally:
        document.close()


def _render_pages(
    path: Path,
    page_numbers: list[int],
    dpi: int,
    output_dir: Path,
) -> list[PageImage]:
    pdfium = _load_pdfium()
    document = pdfium.PdfDocument(str(path))
    try:
        images: list[PageImage] = []
        scale = dpi / 72
        for page_number in page_numbers:
            page = document[page_number - 1]
            image = page.render(scale=scale).to_pil()
            image_path = output_dir / f"page-{page_number}.png"
            image.save(image_path)
            images.append(
                PageImage(
                    page_number=page_number,
                    path=image_path,
                    width=image.width,
                    height=image.height,
                )
            )
        return images
    finally:
        document.close()


class PdfExtractor:
    def __init__(self, options: ExtractionOptions | None = None) -> None:
        self._options = options or ExtractionOptions()
        self._merger = LineToParagraphMerger(self._options.merger)

    async def extract(
        self,
        path: Path,
        ocr_engine: OcrEngine | None = None,
    ) -> ExtractedDocument:
        path = Path(path)
        report = await asyncio.to_thread(
            detect_pdf_text_layer,
            path,
            self._options.text_layer,
        )
        page_sizes = await asyncio.to_thread(_page_sizes, path)
        scanned_pages = [page.page_number for page in report.scanned_pages]
        if scanned_pages and ocr_engine is None:
            raise ExtractionError(
                f"{path} has {len(scanned_pages)} pages without a text layer; "
                "an OCR engine is required"
            )

        ocr_document: OcrDocument | None = None
        if scanned_pages:
            with tempfile.TemporaryDirectory(prefix="rag-ocr-") as temp_dir:
                images = await asyncio.to_thread(
                    _render_pages,
                    path,
                    scanned_pages,
                    self._options.render_dpi,
                    Path(temp_dir),
                )
                if ocr_engine is None:
                    raise ExtractionError("OCR engine became unavailable")
                ocr_document = await ocr_engine.recognize(images, self._options.ocr)

        tables: list[PdfTable] = []
        if self._options.extract_tables:
            textual_pages = {
                page.page_number for page in report.textual_pages
            }
            tables = await asyncio.to_thread(
                extract_pdf_tables,
                path,
                textual_pages,
            )

        return self.build_document(
            path,
            report,
            page_sizes,
            ocr_document,
            self._options,
            self._merger,
            tables,
        )

    @staticmethod
    def build_document(
        path: Path,
        report: TextLayerReport,
        page_sizes: Mapping[int, tuple[int, int]],
        ocr_document: OcrDocument | None,
        options: ExtractionOptions,
        merger: LineToParagraphMerger,
        tables: list[PdfTable] | None = None,
    ) -> ExtractedDocument:
        ocr_pages = {
            page.page_number: page
            for page in (ocr_document.pages if ocr_document else [])
        }
        pages: list[OcrPage] = []
        for page in report.pages:
            width, height = page_sizes.get(page.page_number, (0, 0))
            if page.is_textual:
                pages.append(_text_layer_page(page, width, height))
                continue
            recognized = ocr_pages.get(page.page_number)
            if recognized is None:
                raise ExtractionError(
                    f"OCR did not return page {page.page_number} for {path}"
                )
            pages.append(recognized)
        boilerplate = BoilerplateFilter(options.boilerplate).apply(pages)
        blocks = merger.merge_document(
            OcrDocument(pages=boilerplate.pages),
            {number: size[0] for number, size in page_sizes.items()},
        )
        blocks = clean_block_headers(blocks)
        blocks = merge_table_blocks(blocks, tables or [])
        engines = sorted({page.engine for page in boilerplate.pages})
        return ExtractedDocument(
            source_path=path,
            title=path.stem,
            page_count=len(report.pages),
            blocks=blocks,
            metadata={
                "text_layer_coverage": report.coverage,
                "textual_pages": [page.page_number for page in report.textual_pages],
                "ocr_pages": [page.page_number for page in report.scanned_pages],
                "engines": engines,
                "render_dpi": options.render_dpi,
                "boilerplate_removed": len(boilerplate.removed),
                "boilerplate_repeated": boilerplate.repeated_texts[:10],
                "tables_extracted": len(tables or []),
            },
        )


def _text_layer_page(page: PageTextLayer, width: int, height: int) -> OcrPage:
    lines = [
        OcrLine(
            text=line.strip(),
            bbox=None,
            confidence=1.0,
            page_number=page.page_number,
        )
        for line in page.text.splitlines()
        if line.strip()
    ]
    return OcrPage(
        page_number=page.page_number,
        width=width,
        height=height,
        lines=lines,
        engine="text_layer",
    )
