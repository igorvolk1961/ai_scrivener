from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_HOOKS = {
    "ruff",
    "ruff-format",
    "mypy",
    "mypy-rag",
    "yamllint",
    "config-schema",
    "requirements-traceability",
    "no-unapproved-stubs",
    "no-hardcoded-parameters",
    "bsl-lint",
    "pytest",
    "pytest-rag",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], data)


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def test_precommit_has_required_hooks() -> None:
    config = _load_yaml(REPO_ROOT / ".pre-commit-config.yaml")
    hooks = {hook["id"] for repo in config["repos"] for hook in repo.get("hooks", [])}
    assert hooks >= REQUIRED_HOOKS


def test_precommit_blocks_private_keys() -> None:
    config = _load_yaml(REPO_ROOT / ".pre-commit-config.yaml")
    hooks = {hook["id"] for repo in config["repos"] for hook in repo.get("hooks", [])}
    assert "detect-private-key" in hooks


def test_pyproject_enables_ruff_and_mypy() -> None:
    data = _load_toml(REPO_ROOT / "pyproject.toml")
    assert data["tool"]["ruff"]["line-length"] == 100
    assert data["tool"]["mypy"]["strict"] is True
    assert data["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
