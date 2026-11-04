from __future__ import annotations

import asyncio
from typing import Any

from rag_indexer.ocr.base import BaseOcrEngine
from rag_indexer.ocr.models import (
    BBox,
    OcrEngineError,
    OcrLine,
    OcrOptions,
    OcrPage,
    PageImage,
)

BOX_COORDS = 4
POINT_COORDS = 2


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        return list(value.tolist())
    return list(value)


def _to_bbox(value: Any) -> BBox | None:
    points = _as_list(value)
    if not points:
        return None
    if len(points) == BOX_COORDS and all(
        isinstance(item, (int, float)) for item in points
    ):
        x0, y0, x1, y1 = (int(item) for item in points)
        return BBox(
            x0=min(x0, x1),
            y0=min(y0, y1),
            x1=max(x0, x1),
            y1=max(y0, y1),
        )
    xs: list[int] = []
    ys: list[int] = []
    for point in points:
        pair = _as_list(point)
        if len(pair) >= POINT_COORDS:
            xs.append(int(pair[0]))
            ys.append(int(pair[1]))
    if not xs or not ys:
        return None
    return BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


class PaddleOcrEngine(BaseOcrEngine):
    name = "paddleocr"

    def __init__(
        self,
        *,
        detection_model: str = "PP-OCRv5_mobile_det",
        recognition_model: str = "eslav_PP-OCRv5_mobile_rec",
        detection_limit_side_len: int = 960,
        detection_limit_type: str = "max",
        enable_mkldnn: bool = False,
    ) -> None:
        self._detection_model = detection_model
        self._recognition_model = recognition_model
        self._detection_limit_side_len = detection_limit_side_len
        self._detection_limit_type = detection_limit_type
        self._enable_mkldnn = enable_mkldnn
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from paddleocr import PaddleOCR
        except ImportError as error:
            raise OcrEngineError(
                "paddleocr is not installed; install the 'ocr-paddle' extra"
            ) from error
        self._model = PaddleOCR(
            text_detection_model_name=self._detection_model,
            text_recognition_model_name=self._recognition_model,
            text_det_limit_side_len=self._detection_limit_side_len,
            text_det_limit_type=self._detection_limit_type,
            enable_mkldnn=self._enable_mkldnn,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        return self._model

    async def recognize_page(
        self,
        page: PageImage,
        _options: OcrOptions,
    ) -> OcrPage:
        return await asyncio.to_thread(self._recognize_page_sync, page)

    def _recognize_page_sync(self, page: PageImage) -> OcrPage:
        try:
            results = self._get_model().predict(str(page.path))
        except Exception as error:
            raise OcrEngineError(f"paddleocr failed for page {page.page_number}") from error
        if not results:
            return OcrPage(
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                lines=[],
                engine=self.name,
            )
        return self._parse_result(page, results[0])

    @staticmethod
    def _parse_result(page: PageImage, item: Any) -> OcrPage:
        texts = _as_list(item.get("rec_texts", []))
        scores = _as_list(item.get("rec_scores", []))
        boxes = _as_list(item.get("rec_boxes", []))
        if len(boxes) != len(texts):
            boxes = _as_list(item.get("rec_polys", []))
        lines: list[OcrLine] = []
        for index, text in enumerate(texts):
            normalized = str(text).strip()
            if not normalized:
                continue
            score = float(scores[index]) if index < len(scores) else 0.0
            bbox = _to_bbox(boxes[index]) if index < len(boxes) else None
            lines.append(
                OcrLine(
                    text=normalized,
                    bbox=bbox,
                    confidence=max(0.0, min(1.0, score)),
                    page_number=page.page_number,
                )
            )
        return OcrPage(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            lines=lines,
            engine=PaddleOcrEngine.name,
        )
