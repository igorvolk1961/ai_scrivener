from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    ) -> None:
        self._extractor = extractor or DocumentExtractor()
        self._chunker = chunker or ClauseAwareChunker()
        self._client = client
        self._state = state or IndexState(pipeline_version=PIPELINE_VERSION)

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
                document = await self._extractor.extract(
                    source_path,
                    ocr_engine,
                    mime=record.mime,
                    original_name=record.original_name,
                )
                chunks = self._chunker.chunk(document, source_id=record.sha256)
                if not chunks:
                    raise PipelineError("no chunks produced")
                report.chunks += len(chunks)
                if dry_run:
                    continue
                if client is None:
                    raise PipelineError("RAG client is required for indexing")
                await client.index_chunks(build_payload(record, document, chunks))
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


def build_payload(
    record: CorpusRecord,
    document: ExtractedDocument,
    chunks: list[Chunk],
) -> dict[str, Any]:
    metadata = record.metadata()
    metadata["extraction"] = document.metadata
    return {
        "source_type": SOURCE_TYPE,
        "document": {
            "source_id": record.sha256,
            "version": record.version,
            "title": record.title or document.title,
            "metadata": metadata,
        },
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
