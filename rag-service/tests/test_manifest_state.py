from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag_indexer.manifest import (
    ManifestError,
    latest_manifest,
    load_manifest,
    select_records,
)
from rag_indexer.state import IndexState, StateError


def _record(sha: str, status: str = "downloaded") -> dict[str, object]:
    return {
        "sha256": sha,
        "stored_path": f"blobs/{sha}",
        "mime": "text/plain",
        "status": status,
        "title": f"Документ {sha}",
        "doc_type": "ГОСТ",
    }


def test_load_and_filter_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(_record("a")),
                json.dumps(_record("b", "verified")),
                json.dumps(_record("c", "rejected")),
                "",
            ]
        ),
        encoding="utf-8",
    )

    records = load_manifest(path)
    selected = select_records(records, {"downloaded", "verified"})

    assert [record.sha256 for record in selected] == ["a", "b"]
    assert selected[0].metadata()["doc_type"] == "ГОСТ"


def test_manifest_deduplicates_by_sha(tmp_path: Path) -> None:
    path = tmp_path / "manifest.jsonl"
    path.write_text(
        json.dumps(_record("a")) + "\n" + json.dumps(_record("a", "verified")),
        encoding="utf-8",
    )

    records = select_records(load_manifest(path), {"verified"})

    assert len(records) == 1
    assert records[0].status == "verified"


def test_manifest_rejects_invalid_record(tmp_path: Path) -> None:
    path = tmp_path / "manifest.jsonl"
    path.write_text('{"sha256": "a"}\n', encoding="utf-8")

    with pytest.raises(ManifestError):
        load_manifest(path)


def test_latest_manifest(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "2026-01-01.jsonl").write_text("", encoding="utf-8")
    (manifests / "2026-02-01.jsonl").write_text("", encoding="utf-8")

    assert latest_manifest(tmp_path).name == "2026-02-01.jsonl"


def test_state_roundtrip_and_missing(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = IndexState(pipeline_version="1")
    state.mark_indexed("a", chunks=3, title="A", indexed_at="2026-01-01")
    state.mark_failed("b", "error")
    state.save(path)

    loaded = IndexState.load(path, "1")

    assert loaded.is_indexed("a") is True
    assert loaded.is_indexed("b") is False
    assert loaded.missing({"a"}) == []
    assert loaded.missing(set()) == ["a"]


def test_state_version_mismatch_resets(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = IndexState(pipeline_version="1")
    state.mark_indexed("a", chunks=3, title="A", indexed_at="2026-01-01")
    state.save(path)

    loaded = IndexState.load(path, "2")

    assert loaded.documents == {}


def test_state_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(StateError):
        IndexState.load(path, "1")
