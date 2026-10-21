from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from scripts.config.validate import DuplicateKeyError, validate_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def _valid_data() -> dict[str, Any]:
    data = yaml.safe_load((REPO_ROOT / "config/parameters.yaml").read_text(encoding="utf-8"))
    return cast(dict[str, Any], data)


def _prepare(tmp_path: Path, data: dict[str, Any]) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / "config/parameters.schema.json",
        config_dir / "parameters.schema.json",
    )
    (config_dir / "parameters.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return tmp_path


def test_repository_config_is_valid() -> None:
    assert validate_config(REPO_ROOT) == []


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    data = _valid_data()
    data["unknown_parameter"] = 1
    root = _prepare(tmp_path, data)
    errors = validate_config(root)
    assert any("Additional properties are not allowed" in error for error in errors)


def test_duplicate_key_is_rejected(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / "config/parameters.schema.json",
        config_dir / "parameters.schema.json",
    )
    raw = (REPO_ROOT / "config/parameters.yaml").read_text(encoding="utf-8")
    raw = raw.replace("  port: 8080\n", "  port: 8080\n  port: 8081\n", 1)
    (config_dir / "parameters.yaml").write_text(raw, encoding="utf-8")
    with pytest.raises(DuplicateKeyError):
        validate_config(tmp_path)


def test_chunk_overlap_must_be_less_than_chunk_size(tmp_path: Path) -> None:
    data = _valid_data()
    rag = cast(dict[str, Any], data["rag"])
    rag["chunk_overlap_chars"] = rag["chunk_size_chars"]
    root = _prepare(tmp_path, data)
    errors = validate_config(root)
    assert any("chunk_overlap_chars must be less" in error for error in errors)


def test_negative_timeout_is_rejected(tmp_path: Path) -> None:
    data = _valid_data()
    llm = cast(dict[str, Any], data["llm"])
    llm["timeout_seconds"] = -1
    root = _prepare(tmp_path, data)
    errors = validate_config(root)
    assert any("timeout_seconds" in error for error in errors)


def test_retry_backoff_must_cover_retries(tmp_path: Path) -> None:
    data = _valid_data()
    http = cast(dict[str, Any], data["http"])
    http["max_retries"] = 5
    http["retry_backoff_seconds"] = [1]
    root = _prepare(tmp_path, data)
    errors = validate_config(root)
    assert any("retry_backoff_seconds must contain at least" in error for error in errors)
