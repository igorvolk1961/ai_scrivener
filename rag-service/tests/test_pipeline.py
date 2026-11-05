from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from rag_indexer.chunking import ChunkerOptions, ClauseAwareChunker
from rag_indexer.client import RagClient
from rag_indexer.extraction import DocumentExtractor
from rag_indexer.manifest import CorpusRecord
from rag_indexer.pipeline import IndexPipeline
from rag_indexer.state import IndexState


class FakeClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.deleted: list[tuple[str, str]] = []
        self.activated: list[tuple[str, str, str]] = []

    async def index_chunks(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        return {"indexed_chunks": len(payload["chunks"])}

    async def activate(
        self,
        source_type: str,
        source_id: str,
        version: str,
        target_collection: str | None = None,
    ) -> dict[str, Any]:
        self.activated.append((source_type, source_id, version))
        return {"activated": True}

    async def delete(
        self,
        source_type: str,
        source_id: str,
        target_collection: str | None = None,
    ) -> dict[str, Any]:
        self.deleted.append((source_type, source_id))
        return {"deleted": True}


def _record(sha: str = "abc123") -> CorpusRecord:
    return CorpusRecord(
        sha256=sha,
        stored_path="doc.txt",
        mime="text/plain",
        status="downloaded",
        title="Инструкция",
        doc_type="Инструкция",
    )


def _state() -> IndexState:
    return IndexState(pipeline_version="1")


def test_pipeline_indexes_document(tmp_path: Path) -> None:
    (tmp_path / "doc.txt").write_text(
        "1 Общие положения\n\n1.1 Настоящая инструкция применяется.",
        encoding="utf-8",
    )
    client = FakeClient()
    state = _state()
    pipeline = IndexPipeline(
        extractor=DocumentExtractor(),
        chunker=ClauseAwareChunker(),
        client=cast(RagClient, client),
        state=state,
        export_dir=tmp_path / "export",
    )

    report = asyncio.run(pipeline.run([_record()], tmp_path))

    assert report.indexed == 1
    assert report.chunks > 0
    assert client.payloads[0]["source_type"] == "knowledge_material"
    assert client.payloads[0]["document"]["source_id"] == "abc123"
    assert client.payloads[0]["chunks"][0]["embedding_text"].startswith("Документ:")
    assert state.is_indexed("abc123") is True
    assert report.documents[0].status == "indexed"
    assert report.documents[0].chunks > 0
    assert (tmp_path / "export" / "abc123.md").exists()


def test_pipeline_batches_chunks_and_replaces_only_first_batch(tmp_path: Path) -> None:
    (tmp_path / "doc.txt").write_text(
        "1. Первый пункт.\n\n2. Второй пункт.\n\n3. Третий пункт.",
        encoding="utf-8",
    )
    client = FakeClient()
    pipeline = IndexPipeline(
        extractor=DocumentExtractor(),
        chunker=ClauseAwareChunker(
            ChunkerOptions(target_tokens=1, max_tokens=100, min_tokens=1)
        ),
        client=cast(RagClient, client),
        state=_state(),
        chunk_batch_size=2,
    )

    report = asyncio.run(pipeline.run([_record()], tmp_path))

    assert report.indexed == 1
    assert len(client.payloads) == 2
    assert [payload["replace_existing"] for payload in client.payloads] == [False, False]
    assert [payload["active"] for payload in client.payloads] == [False, False]
    assert [len(payload["chunks"]) for payload in client.payloads] == [2, 1]
    assert client.payloads[0]["document"]["version"] == "abc123:1"
    assert client.activated == [("knowledge_material", "abc123", "abc123:1")]


def test_pipeline_dry_run_does_not_call_client_or_state(tmp_path: Path) -> None:
    (tmp_path / "doc.txt").write_text("1 Общие положения\n\nТекст.", encoding="utf-8")
    state = _state()
    pipeline = IndexPipeline(
        extractor=DocumentExtractor(),
        chunker=ClauseAwareChunker(),
        client=None,
        state=state,
    )

    report = asyncio.run(pipeline.run([_record()], tmp_path, dry_run=True))

    assert report.indexed == 0
    assert report.chunks > 0
    assert state.documents == {}


def test_pipeline_reports_missing_file(tmp_path: Path) -> None:
    state = _state()
    pipeline = IndexPipeline(
        extractor=DocumentExtractor(),
        chunker=ClauseAwareChunker(),
        client=cast(RagClient, FakeClient()),
        state=state,
    )

    report = asyncio.run(pipeline.run([_record()], tmp_path))

    assert report.failed == 1
    assert state.documents["abc123"].status == "failed"


def test_pipeline_deletes_missing_documents(tmp_path: Path) -> None:
    (tmp_path / "doc.txt").write_text("1 Общие положения\n\nТекст.", encoding="utf-8")
    state = _state()
    state.documents["old"] = state_document()
    client = FakeClient()
    pipeline = IndexPipeline(
        extractor=DocumentExtractor(),
        chunker=ClauseAwareChunker(),
        client=cast(RagClient, client),
        state=state,
    )

    report = asyncio.run(
        pipeline.run([_record()], tmp_path, delete_missing=True)
    )

    assert report.deleted == 1
    assert client.deleted == [("knowledge_material", "old")]
    assert "old" not in state.documents


def state_document() -> Any:
    from rag_indexer.state import DocumentState

    return DocumentState(
        status="indexed",
        chunks=1,
        title="old",
        indexed_at=datetime.now(UTC).isoformat(),
    )
