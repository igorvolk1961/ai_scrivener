from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from rag_indexer.cache import CHUNKER_VERSION, EXTRACTOR_VERSION, DocumentCache
from rag_indexer.chunking import Chunk, ClauseAwareChunker
from rag_indexer.client import RagClient
from rag_indexer.extraction import Block, DocumentExtractor, ExtractedDocument
from rag_indexer.manifest import CorpusRecord
from rag_indexer.ocr import BBox
from rag_indexer.pipeline import IndexPipeline
from rag_indexer.state import IndexState


class CountingExtractor(DocumentExtractor):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def extract(self, path: Path, ocr_engine: Any = None, **kwargs: Any) -> ExtractedDocument:
        self.calls += 1
        return await super().extract(path, ocr_engine, **kwargs)


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    async def index_chunks(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {"indexed_chunks": len(payload["chunks"])}

    async def delete(self, source_type: str, source_id: str) -> dict[str, Any]:
        return {"deleted": True}


def _document() -> ExtractedDocument:
    return ExtractedDocument(
        source_path=Path("doc.txt"),
        title="Документ",
        page_count=1,
        blocks=[
            Block(
                text="1.1 Пункт.",
                page_start=1,
                page_end=1,
                kind="paragraph",
                engine="test",
                confidence=0.9,
                bbox=BBox(1, 2, 3, 4),
                metadata={"x": 1},
            )
        ],
        metadata={"engines": ["test"]},
    )


def _chunks() -> list[Chunk]:
    return [
        Chunk(
            index=0,
            text="1.1 Пункт.",
            embedding_text="Документ: Документ\nТекст: 1.1 Пункт.",
            section_path=["1"],
            section_text="1",
            clause="1.1",
            page_start=1,
            page_end=1,
            kind="paragraph",
            parent_id="doc:section:0",
            metadata={"section_index": 0},
            char_start=0,
            char_end=10,
        )
    ]


def test_cache_roundtrip_document_and_chunks(tmp_path: Path) -> None:
    cache = DocumentCache(tmp_path)
    cache.save_document("sha", _document())
    cache.save_chunks("sha", _chunks())

    document = cache.load_document("sha")
    chunks = cache.load_chunks("sha")

    assert document is not None
    assert document.blocks[0].bbox == BBox(1, 2, 3, 4)
    assert document.metadata["engines"] == ["test"]
    assert chunks is not None
    assert chunks[0].clause == "1.1"
    assert chunks[0].char_start == 0


def test_cache_is_versioned(tmp_path: Path) -> None:
    cache = DocumentCache(tmp_path)
    cache.save_document("sha", _document())

    other = DocumentCache(
        tmp_path,
        extractor_version="2",
        chunker_version="2",
    )

    assert other.load_document("sha") is None
    assert EXTRACTOR_VERSION == "1"
    assert CHUNKER_VERSION == "1"


def test_pipeline_uses_document_and_chunk_cache(tmp_path: Path) -> None:
    (tmp_path / "doc.txt").write_text(
        "1 Общие положения\n\n1.1 Настоящая инструкция применяется.",
        encoding="utf-8",
    )
    extractor = CountingExtractor()
    cache = DocumentCache(tmp_path / "cache")
    client = FakeClient()
    pipeline = IndexPipeline(
        extractor=extractor,
        chunker=ClauseAwareChunker(),
        client=cast(RagClient, client),
        state=IndexState(pipeline_version="1"),
        cache=cache,
    )
    record = CorpusRecord(
        sha256="abc",
        stored_path="doc.txt",
        mime="text/plain",
        status="downloaded",
        title="Инструкция",
    )

    asyncio.run(pipeline.run([record], tmp_path, full=True))
    asyncio.run(pipeline.run([record], tmp_path, full=True))

    assert extractor.calls == 1
    assert client.calls == 2
