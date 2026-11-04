from __future__ import annotations

import base64
from typing import Any

import httpx

from rag_indexer.ocr.base import BaseOcrEngine
from rag_indexer.ocr.models import (
    BBox,
    OcrEngineError,
    OcrLine,
    OcrOptions,
    OcrPage,
    PageImage,
)


def _bbox_from_vertices(value: Any) -> BBox | None:
    if not isinstance(value, dict):
        return None
    vertices = value.get("vertices")
    if not isinstance(vertices, list) or not vertices:
        return None
    xs: list[int] = []
    ys: list[int] = []
    for vertex in vertices:
        if not isinstance(vertex, dict):
            continue
        try:
            xs.append(int(vertex.get("x", 0)))
            ys.append(int(vertex.get("y", 0)))
        except (TypeError, ValueError):
            continue
    if not xs or not ys:
        return None
    return BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


class YandexOcrEngine(BaseOcrEngine):
    name = "yandex"

    def __init__(
        self,
        *,
        iam_token: str,
        folder_id: str,
        endpoint: str = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._iam_token = iam_token
        self._folder_id = folder_id
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_seconds)
        return self._client

    async def recognize_page(
        self,
        page: PageImage,
        options: OcrOptions,
    ) -> OcrPage:
        payload = {
            "mimeType": page.mime_type,
            "languageCodes": list(options.languages),
            "model": options.model,
            "content": base64.b64encode(page.path.read_bytes()).decode("ascii"),
        }
        headers = {
            "Authorization": f"Bearer {self._iam_token}",
            "x-folder-id": self._folder_id,
            "Content-Type": "application/json",
        }
        try:
            response = await self._get_client().post(
                self._endpoint,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise OcrEngineError(f"yandex ocr failed for page {page.page_number}") from error
        return self._parse_response(page, response.json())

    @staticmethod
    def _parse_response(page: PageImage, payload: Any) -> OcrPage:
        result = payload.get("result") if isinstance(payload, dict) else None
        annotation = result.get("textAnnotation") if isinstance(result, dict) else None
        blocks = annotation.get("blocks", []) if isinstance(annotation, dict) else []
        lines: list[OcrLine] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            for line in block.get("lines", []):
                if not isinstance(line, dict):
                    continue
                text = str(line.get("text", "")).strip()
                if not text:
                    continue
                try:
                    confidence = float(line.get("confidence", 0.0))
                except (TypeError, ValueError):
                    confidence = 0.0
                lines.append(
                    OcrLine(
                        text=text,
                        bbox=_bbox_from_vertices(line.get("boundingBox")),
                        confidence=max(0.0, min(1.0, confidence)),
                        page_number=page.page_number,
                    )
                )
        if not lines and isinstance(annotation, dict):
            full_text = str(annotation.get("fullText", "")).strip()
            if full_text:
                lines = [
                    OcrLine(
                        text=part.strip(),
                        bbox=None,
                        confidence=0.0,
                        page_number=page.page_number,
                    )
                    for part in full_text.splitlines()
                    if part.strip()
                ]
        return OcrPage(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            lines=lines,
            engine=YandexOcrEngine.name,
        )

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
