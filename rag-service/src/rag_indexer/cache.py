from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rag_indexer.chunking import Chunk
from rag_indexer.extraction import Block, ExtractedDocument
from rag_indexer.ocr import BBox

EXTRACTOR_VERSION = "1"
CHUNKER_VERSION = "1"


class DocumentCache:
    def __init__(
        self,
        cache_dir: Path,
        *,
        extractor_version: str = EXTRACTOR_VERSION,
        chunker_version: str = CHUNKER_VERSION,
    ) -> None:
        self._cache_dir = cache_dir
        self._extractor_dir = cache_dir / "extracted" / extractor_version
        self._chunker_dir = cache_dir / "chunks" / chunker_version

    def load_document(self, sha256: str) -> ExtractedDocument | None:
        payload = _read_json(self._extractor_dir / f"{_key(sha256)}.json")
        if payload is None:
            return None
        try:
            return _document_from_dict(payload)
        except (KeyError, TypeError, ValueError):
            return None

    def save_document(self, sha256: str, document: ExtractedDocument) -> None:
        _write_json(
            self._extractor_dir / f"{_key(sha256)}.json",
            _document_to_dict(document),
        )

    def load_chunks(self, sha256: str) -> list[Chunk] | None:
        payload = _read_json(self._chunker_dir / f"{_key(sha256)}.json")
        if payload is None:
            return None
        try:
            return [_chunk_from_dict(item) for item in payload["chunks"]]
        except (KeyError, TypeError, ValueError):
            return None

    def save_chunks(self, sha256: str, chunks: list[Chunk]) -> None:
        _write_json(
            self._chunker_dir / f"{_key(sha256)}.json",
            {"chunks": [_chunk_to_dict(chunk) for chunk in chunks]},
        )


def _key(sha256: str) -> str:
    if sha256.isalnum():
        return sha256
    return hashlib.sha256(sha256.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _bbox_to_dict(bbox: BBox | None) -> dict[str, int] | None:
    if bbox is None:
        return None
    return {
        "x0": bbox.x0,
        "y0": bbox.y0,
        "x1": bbox.x1,
        "y1": bbox.y1,
    }


def _bbox_from_dict(payload: Any) -> BBox | None:
    if not isinstance(payload, dict):
        return None
    return BBox(
        x0=int(payload["x0"]),
        y0=int(payload["y0"]),
        x1=int(payload["x1"]),
        y1=int(payload["y1"]),
    )


def _block_to_dict(block: Block) -> dict[str, Any]:
    return {
        "text": block.text,
        "page_start": block.page_start,
        "page_end": block.page_end,
        "kind": block.kind,
        "engine": block.engine,
        "confidence": block.confidence,
        "bbox": _bbox_to_dict(block.bbox),
        "metadata": block.metadata,
    }


def _block_from_dict(payload: dict[str, Any]) -> Block:
    return Block(
        text=str(payload["text"]),
        page_start=int(payload["page_start"]),
        page_end=int(payload["page_end"]),
        kind=str(payload["kind"]),
        engine=str(payload["engine"]),
        confidence=float(payload.get("confidence", 1.0)),
        bbox=_bbox_from_dict(payload.get("bbox")),
        metadata=dict(payload.get("metadata", {})),
    )


def _document_to_dict(document: ExtractedDocument) -> dict[str, Any]:
    return {
        "source_path": str(document.source_path),
        "title": document.title,
        "page_count": document.page_count,
        "blocks": [_block_to_dict(block) for block in document.blocks],
        "metadata": document.metadata,
    }


def _document_from_dict(payload: dict[str, Any]) -> ExtractedDocument:
    return ExtractedDocument(
        source_path=Path(str(payload["source_path"])),
        title=str(payload["title"]),
        page_count=int(payload["page_count"]),
        blocks=[_block_from_dict(item) for item in payload["blocks"]],
        metadata=dict(payload.get("metadata", {})),
    )


def _chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    return {
        "index": chunk.index,
        "text": chunk.text,
        "embedding_text": chunk.embedding_text,
        "section_path": chunk.section_path,
        "section_text": chunk.section_text,
        "clause": chunk.clause,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "kind": chunk.kind,
        "parent_id": chunk.parent_id,
        "metadata": chunk.metadata,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
    }


def _chunk_from_dict(payload: dict[str, Any]) -> Chunk:
    return Chunk(
        index=int(payload["index"]),
        text=str(payload["text"]),
        embedding_text=str(payload["embedding_text"]),
        section_path=list(payload.get("section_path", [])),
        section_text=str(payload.get("section_text", "")),
        clause=str(payload.get("clause", "")),
        page_start=payload.get("page_start"),
        page_end=payload.get("page_end"),
        kind=str(payload.get("kind", "paragraph")),
        parent_id=payload.get("parent_id"),
        metadata=dict(payload.get("metadata", {})),
        char_start=payload.get("char_start"),
        char_end=payload.get("char_end"),
    )
