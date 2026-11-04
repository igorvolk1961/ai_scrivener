from __future__ import annotations

import json
from pathlib import Path

from rag_indexer.cli import main
from rag_indexer.state import IndexState


def _prepare(tmp_path: Path) -> Path:
    (tmp_path / "doc.txt").write_text(
        "1 Общие положения\n\n1.1 Настоящая инструкция применяется.",
        encoding="utf-8",
    )
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    record = {
        "sha256": "abc",
        "stored_path": "doc.txt",
        "mime": "text/plain",
        "status": "downloaded",
        "title": "Инструкция",
        "doc_type": "Инструкция",
    }
    (manifests / "2026-01-01.jsonl").write_text(
        json.dumps(record) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_cli_validate_dry_runs_without_state(tmp_path: Path) -> None:
    corpus = _prepare(tmp_path)
    state_path = tmp_path / "state.json"

    code = main(
        [
            "validate",
            "--corpus-dir",
            str(corpus),
            "--state",
            str(state_path),
            "--ocr",
            "none",
        ]
    )

    assert code == 0
    assert not state_path.exists()


def test_cli_index_dry_run_does_not_require_token(tmp_path: Path) -> None:
    corpus = _prepare(tmp_path)
    state_path = tmp_path / "state.json"

    code = main(
        [
            "index",
            "--corpus-dir",
            str(corpus),
            "--state",
            str(state_path),
            "--ocr",
            "none",
            "--dry-run",
        ]
    )

    assert code == 0
    assert not state_path.exists()


def test_cli_index_requires_token(tmp_path: Path) -> None:
    corpus = _prepare(tmp_path)

    code = main(
        [
            "index",
            "--corpus-dir",
            str(corpus),
            "--state",
            str(tmp_path / "state.json"),
            "--ocr",
            "none",
        ]
    )

    assert code == 1


def test_cli_rejects_limit_with_delete_missing(tmp_path: Path) -> None:
    corpus = _prepare(tmp_path)

    code = main(
        [
            "index",
            "--corpus-dir",
            str(corpus),
            "--state",
            str(tmp_path / "state.json"),
            "--ocr",
            "none",
            "--dry-run",
            "--limit",
            "1",
            "--delete-missing",
        ]
    )

    assert code == 1


def test_cli_cleanup_requires_token() -> None:
    assert main(["cleanup"]) == 1


def test_cli_stats(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = IndexState(pipeline_version="1")
    state.mark_indexed("a", chunks=3, title="A", indexed_at="2026-01-01")
    state.mark_failed("b", "error")
    state.save(state_path)

    code = main(["stats", "--state", str(state_path)])

    assert code == 0
