from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from scripts.requirements.check import (
    check_generated,
    parse_document,
    render_matrix,
    write_generated,
)


def _requirement() -> dict[str, Any]:
    return {
        "id": "FR-001",
        "type": "functional",
        "title": "Test requirement",
        "description": "Test requirement description.",
        "priority": "must",
        "approval": "approved",
        "source": ["docs/raw_specification.md#1"],
        "acceptance": ["Acceptance criterion."],
        "design": ["docs/implementation_plan.md#1"],
        "implementation": ["src/Configuration/Test"],
        "tests": ["TEST-FR-001-01"],
        "test_files": ["tests/test_placeholder.py"],
        "status": "planned",
    }


def _document(requirement: dict[str, Any]) -> dict[str, Any]:
    return {"meta": {"version": 1}, "requirements": [requirement]}


def _prepare_root(root: Path) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "docs/implementation_plan.md").write_text("plan\n", encoding="utf-8")


def test_valid_planned_requirement_passes(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    requirements, errors = parse_document(_document(_requirement()), tmp_path)
    assert errors == []
    assert [item.id for item in requirements] == ["FR-001"]


def test_duplicate_requirement_id_is_rejected(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    requirement = _requirement()
    document = {"meta": {"version": 1}, "requirements": [requirement, deepcopy(requirement)]}
    _, errors = parse_document(document, tmp_path)
    assert any("duplicate requirement id" in error for error in errors)


def test_type_prefix_must_match(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    requirement = _requirement()
    requirement["id"] = "NFR-001"
    _, errors = parse_document(_document(requirement), tmp_path)
    assert any("id does not match type" in error for error in errors)


def test_test_id_must_belong_to_requirement(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    requirement = _requirement()
    requirement["tests"] = ["TEST-FR-002-01"]
    _, errors = parse_document(_document(requirement), tmp_path)
    assert any("test id does not belong to requirement" in error for error in errors)


def test_implemented_requirement_requires_existing_artifacts(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    requirement = _requirement()
    requirement["status"] = "implemented"
    _, errors = parse_document(_document(requirement), tmp_path)
    assert any("implementation path does not exist" in error for error in errors)
    assert any("test file path does not exist" in error for error in errors)


def test_implemented_requirement_passes_when_artifacts_exist(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    (tmp_path / "src/Configuration/Test").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_placeholder.py").write_text(
        "def test_placeholder() -> None:\n    pass\n"
    )
    requirement = _requirement()
    requirement["status"] = "implemented"
    _, errors = parse_document(_document(requirement), tmp_path)
    assert errors == []


def test_generated_documents_are_checked(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    requirements, errors = parse_document(_document(_requirement()), tmp_path)
    assert errors == []
    write_generated(tmp_path, requirements)
    assert check_generated(tmp_path, requirements) == []
    matrix = tmp_path / "docs/requirements/traceability_matrix.md"
    matrix.write_text("stale\n", encoding="utf-8")
    assert check_generated(tmp_path, requirements) == [
        "generated document is stale: docs/requirements/traceability_matrix.md"
    ]


def test_matrix_contains_requirement_id(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    requirements, errors = parse_document(_document(_requirement()), tmp_path)
    assert errors == []
    assert "FR-001" in render_matrix(requirements)
