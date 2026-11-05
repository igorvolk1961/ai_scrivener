from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from rag_indexer.cache import DocumentCache
from rag_indexer.client import RagClient
from rag_indexer.extraction import DocumentExtractor, ExtractionOptions
from rag_indexer.manifest import (
    ManifestError,
    latest_manifest,
    load_manifest,
    select_records,
)
from rag_indexer.ocr import (
    FallbackOcrEngine,
    FallbackPolicy,
    OcrEngine,
    PaddleOcrEngine,
    YandexOcrEngine,
)
from rag_indexer.pipeline import PIPELINE_VERSION, IndexPipeline
from rag_indexer.state import IndexState, StateError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag_indexer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("index", "validate"):
        command = subparsers.add_parser(name)
        _add_common_arguments(command)
        if name == "index":
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--full", action="store_true")
            command.add_argument("--delete-missing", action="store_true")
    stats = subparsers.add_parser("stats")
    stats.add_argument(
        "--state",
        type=Path,
        default=Path(".rag-index-state.json"),
    )
    stats.add_argument("--pipeline-version", default=PIPELINE_VERSION)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--rag-url", default=os.environ.get("RAG_URL", "http://127.0.0.1:8080"))
    cleanup.add_argument("--token", default=os.environ.get("RAG_SERVICE_TOKEN", ""))
    cleanup.add_argument("--older-than-hours", type=float, default=24)
    cleanup.add_argument("--source-type")
    cache_cleanup = subparsers.add_parser("cache-cleanup")
    cache_cleanup.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".rag-index-cache"),
    )
    cache_cleanup.add_argument("--keep-versions", type=int, default=2)
    collection_create = subparsers.add_parser("collection-create")
    collection_create.add_argument("--rag-url", default=os.environ.get("RAG_URL", "http://127.0.0.1:8080"))
    collection_create.add_argument("--token", default=os.environ.get("RAG_SERVICE_TOKEN", ""))
    collection_create.add_argument("--name", required=True)
    alias_switch = subparsers.add_parser("alias-switch")
    alias_switch.add_argument("--rag-url", default=os.environ.get("RAG_URL", "http://127.0.0.1:8080"))
    alias_switch.add_argument("--token", default=os.environ.get("RAG_SERVICE_TOKEN", ""))
    alias_switch.add_argument("--alias", required=True)
    alias_switch.add_argument("--collection", required=True)
    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path(os.environ.get("RAG_CORPUS_DIR", ".")),
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--statuses", default="downloaded,verified")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--state",
        type=Path,
        default=Path(".rag-index-state.json"),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".rag-index-cache"),
    )
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--ocr-version", default="")
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--target-collection")
    parser.add_argument("--chunk-batch-size", type=int, default=0)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--pipeline-version", default=PIPELINE_VERSION)
    parser.add_argument("--render-dpi", type=int, default=150)
    parser.add_argument("--rag-url", default=os.environ.get("RAG_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--token", default=os.environ.get("RAG_SERVICE_TOKEN", ""))
    parser.add_argument("--ocr", choices=("none", "paddle", "yandex"), default="paddle")
    parser.add_argument("--fallback-yandex", action="store_true")
    parser.add_argument(
        "--yandex-iam-token",
        default=os.environ.get("YANDEX_OCR_IAM_TOKEN", ""),
    )
    parser.add_argument(
        "--yandex-folder-id",
        default=os.environ.get("YANDEX_OCR_FOLDER_ID", ""),
    )
    parser.add_argument(
        "--yandex-endpoint",
        default="https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "stats":
        return _stats(args)
    if args.command == "cache-cleanup":
        return _cache_cleanup(args)
    if args.command in {"collection-create", "alias-switch"}:
        try:
            return asyncio.run(_collection_command(args))
        except (RuntimeError, OSError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
    try:
        if args.command == "cleanup":
            return asyncio.run(_cleanup(args))
        return asyncio.run(_run(args))
    except (ManifestError, StateError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _stats(args: argparse.Namespace) -> int:
    state = IndexState.load(args.state, args.pipeline_version)
    indexed = [doc for doc in state.documents.values() if doc.status == "indexed"]
    failed = [doc for doc in state.documents.values() if doc.status == "failed"]
    print(f"documents: {len(state.documents)}")
    print(f"indexed: {len(indexed)}")
    print(f"failed: {len(failed)}")
    print(f"chunks: {sum(doc.chunks for doc in indexed)}")
    return 0


async def _run(args: argparse.Namespace) -> int:
    corpus_dir = args.corpus_dir.expanduser().resolve()
    manifest_path = args.manifest or latest_manifest(corpus_dir)
    records = select_records(
        load_manifest(manifest_path),
        _statuses(args.statuses),
    )
    if args.limit is not None:
        if args.command == "index" and args.delete_missing:
            raise RuntimeError("--limit cannot be combined with --delete-missing")
        records = records[: args.limit]
    if not records:
        print("no records selected")
        return 0

    state = IndexState.load(args.state, args.pipeline_version)
    ocr_engine = _ocr_engine(args)
    client = None
    if args.command == "index" and not args.dry_run:
        if not args.token:
            raise RuntimeError("RAG service token is required for indexing")
        client = RagClient(args.rag_url, args.token)
    cache = (
        None
        if args.no_cache
        else DocumentCache(
            args.cache_dir,
            ocr_version=_ocr_version(args),
        )
    )
    pipeline = IndexPipeline(
        extractor=DocumentExtractor(ExtractionOptions(render_dpi=args.render_dpi)),
        chunker=None,
        client=client,
        state=state,
        cache=cache,
        chunk_batch_size=args.chunk_batch_size,
        export_dir=args.export_dir,
        target_collection=args.target_collection,
    )
    try:
        report = await pipeline.run(
            records,
            corpus_dir,
            ocr_engine=ocr_engine,
            dry_run=args.command == "validate" or args.dry_run,
            full=getattr(args, "full", False),
            delete_missing=getattr(args, "delete_missing", False),
        )
    finally:
        if ocr_engine is not None:
            await ocr_engine.close()
        if client is not None:
            await client.close()
    if args.command == "index" and not args.dry_run:
        state.save(args.state)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(
        "processed={processed} indexed={indexed} skipped={skipped} "
        "failed={failed} deleted={deleted} chunks={chunks}".format(**vars(report))
    )
    for sha, error in report.errors:
        print(f"  {sha}: {error}", file=sys.stderr)
    return 0 if report.failed == 0 else 1


async def _collection_command(args: argparse.Namespace) -> int:
    if not args.token:
        raise RuntimeError("RAG service token is required")
    client = RagClient(args.rag_url, args.token)
    try:
        if args.command == "collection-create":
            result = await client.create_collection(args.name)
        else:
            result = await client.switch_alias(args.alias, args.collection)
    finally:
        await client.close()
    print(result)
    return 0


def _cache_cleanup(args: argparse.Namespace) -> int:
    removed = DocumentCache(args.cache_dir).cleanup(args.keep_versions)
    print(f"removed_versions={removed}")
    return 0


async def _cleanup(args: argparse.Namespace) -> int:
    if not args.token:
        raise RuntimeError("RAG service token is required for cleanup")
    client = RagClient(args.rag_url, args.token)
    try:
        result = await client.cleanup(
            args.older_than_hours,
            args.source_type,
        )
    finally:
        await client.close()
    print(f"deleted={result.get('deleted', 0)}")
    return 0


def _statuses(value: str) -> set[str]:
    if value.strip().lower() == "all":
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _ocr_version(args: argparse.Namespace) -> str:
    if args.ocr_version:
        return str(args.ocr_version)
    if args.ocr == "none":
        return "none"
    if args.ocr == "yandex":
        return "yandex"
    if args.fallback_yandex:
        return "paddle-v5+yandex"
    return "paddle-v5"


def _ocr_engine(args: argparse.Namespace) -> OcrEngine | None:
    if args.ocr == "none":
        return None
    if args.ocr == "yandex":
        return _yandex_engine(args)
    paddle = PaddleOcrEngine()
    if args.fallback_yandex:
        return FallbackOcrEngine(paddle, _yandex_engine(args), FallbackPolicy())
    return paddle


def _yandex_engine(args: argparse.Namespace) -> YandexOcrEngine:
    if not args.yandex_iam_token or not args.yandex_folder_id:
        raise RuntimeError(
            "Yandex OCR requires --yandex-iam-token and --yandex-folder-id"
        )
    return YandexOcrEngine(
        iam_token=args.yandex_iam_token,
        folder_id=args.yandex_folder_id,
        endpoint=args.yandex_endpoint,
    )
