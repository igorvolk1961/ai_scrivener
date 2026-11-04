from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from typing import Any

from rag_indexer.cache import DocumentCache
from rag_indexer.chunking import Chunk, ClauseAwareChunker
from rag_indexer.client import RagClient
from rag_indexer.extraction import DocumentExtractor, ExtractedDocument
from rag_indexer.manifest import CorpusRecord
from rag_indexer.ocr.models import OcrEngine
from rag_indexer.state import IndexState

PIPELINE_VERSION = "1"
SOURCE_TYPE = "knowledge_material"


class PipelineError(RuntimeError):
    pass


@dataclass
class IndexReport:
    processed: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    deleted: int = 0
    chunks: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


class IndexPipeline:
    def __init__(
        self,
        *,
        extractor: DocumentExtractor | None = None,
        chunker: ClauseAwareChunker | None = None,
        client: RagClient | None = None,
        state: IndexState | None = None,
        cache: DocumentCache | None = None,
        chunk_batch_size: int = 0,
    ) -> None:
        if chunk_batch_size < 0:
            raise ValueError("chunk_batch_size must be non-negative")
        self._extractor = extractor or DocumentExtractor()
        self._chunker = chunker or ClauseAwareChunker()
        self._client = client
        self._state = state or IndexState(pipeline_version=PIPELINE_VERSION)
        self._cache = cache
        self._chunk_batch_size = chunk_batch_size

    async def run(
        self,
        records: list[CorpusRecord],
        corpus_dir: Path,
        *,
        ocr_engine: OcrEngine | None = None,
        dry_run: bool = False,
        full: bool = False,
        delete_missing: bool = False,
    ) -> IndexReport:
        client = self._client
        if not dry_run and client is None:
            raise PipelineError("RAG client is required for indexing")
        report = IndexReport()
        selected_shas = {record.sha256 for record in records}
        for record in records:
            if not full and self._state.is_indexed(record.sha256):
                report.skipped += 1
                continue
            report.processed += 1
            try:
                source_path = corpus_dir / record.stored_path
                if not source_path.exists():
                    raise PipelineError(f"file not found: {source_path}")
                document = (
                    self._cache.load_document(record.sha256)
                    if self._cache is not None
                    else None
                )
                if document is None:
                    document = await self._extractor.extract(
                        source_path,
                        ocr_engine,
                        mime=record.mime,
                        original_name=record.original_name,
                    )
                    if self._cache is not None:
                        self._cache.save_document(record.sha256, document)
                chunks = (
                    self._cache.load_chunks(record.sha256)
                    if self._cache is not None
                    else None
                )
                if chunks is None:
                    chunks = self._chunker.chunk(document, source_id=record.sha256)
                    if self._cache is not None:
                        self._cache.save_chunks(record.sha256, chunks)
                if not chunks:
                    raise PipelineError("no chunks produced")
                report.chunks += len(chunks)
                if dry_run:
                    continue
                if client is None:
                    raise PipelineError("RAG client is required for indexing")
                staged = self._chunk_batch_size > 0
                index_version = (
                    f"{record.version}:{PIPELINE_VERSION}"
                    if staged
                    else record.version
                )
                for batch_index, batch in enumerate(
                    _batches(chunks, self._chunk_batch_size)
                ):
                    await client.index_chunks(
                        build_payload(
                            record,
                            document,
                            batch,
                            version=index_version,
                            replace_existing=not staged and batch_index == 0,
                            active=not staged,
                        )
                    )
                if staged:
                    await client.activate(
                        SOURCE_TYPE,
                        record.sha256,
                        index_version,
                    )
                self._state.mark_indexed(
                    record.sha256,
                    chunks=len(chunks),
                    title=record.title or document.title,
                    indexed_at=datetime.now(UTC).isoformat(),
                )
                report.indexed += 1
            except Exception as error:
                report.failed += 1
                report.errors.append((record.sha256, str(error)))
                if not dry_run:
                    self._state.mark_failed(record.sha256, str(error))
        if delete_missing and not dry_run and client is not None:
            for sha in self._state.missing(selected_shas):
                try:
                    await client.delete(SOURCE_TYPE, sha)
                    self._state.documents.pop(sha, None)
                    report.deleted += 1
                except Exception as error:
                    report.failed += 1
                    report.errors.append((sha, str(error)))
        return report


def _batches(chunks: list[Chunk], size: int) -> list[list[Chunk]]:
    if size <= 0 or size >= len(chunks):
        return [chunks]
    return [list(batch) for batch in batched(chunks, size)]


def build_payload(
    record: CorpusRecord,
    document: ExtractedDocument,
    chunks: list[Chunk],
    *,
    version: str | None = None,
    replace_existing: bool = True,
    active: bool = True,
) -> dict[str, Any]:
    metadata = record.metadata()
    metadata["extraction"] = document.metadata
    return {
        "source_type": SOURCE_TYPE,
        "document": {
            "source_id": record.sha256,
            "version": version or record.version,
            "title": record.title or document.title,
            "metadata": metadata,
        },
        "replace_existing": replace_existing,
        "active": active,
        "chunks": [
            {
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
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        ],
    }
