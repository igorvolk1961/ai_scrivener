from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

REQUIREMENTS_PATH = Path("docs/requirements/requirements.yaml")
FUNCTIONAL_PATH = Path("docs/requirements/functional_requirements.md")
NONFUNCTIONAL_PATH = Path("docs/requirements/nonfunctional_requirements.md")
MATRIX_PATH = Path("docs/requirements/traceability_matrix.md")

ID_PATTERN = re.compile(r"^(FR|NFR)-\d{3}$")
TEST_PATTERN = re.compile(r"^TEST-(FR|NFR)-\d{3}-\d{2}$")
PRIORITIES = frozenset({"must", "should", "could"})
APPROVALS = frozenset({"approved", "proposed"})
STATUSES = frozenset({"planned", "in_progress", "implemented", "verified"})
TYPE_PREFIXES = {"functional": "FR", "nonfunctional": "NFR"}
REQUIRED_FIELDS = (
    "id",
    "type",
    "title",
    "description",
    "priority",
    "approval",
    "source",
    "acceptance",
    "design",
    "implementation",
    "tests",
    "test_files",
    "status",
)
ALLOWED_FIELDS = frozenset(REQUIRED_FIELDS)
DESIGN_PREFIXES = ("docs/", "plans/", "guides/")
IMPLEMENTATION_PREFIXES = (
    "src/",
    "src",
    "rag-service/",
    "rag-service",
    "config/",
    "config",
    "scripts/",
    "scripts",
    "tests/",
    "tests",
    "docs/",
    "docs",
    "plans/",
    "plans",
    "guides/",
    "guides",
    "pyproject.toml",
    "Makefile",
    ".pre-commit-config.yaml",
)
TEST_FILE_PREFIXES = ("tests/", "rag-service/tests/")


@dataclass(frozen=True)
class Requirement:
    id: str
    type: str
    title: str
    description: str
    priority: str
    approval: str
    source: tuple[str, ...]
    acceptance: tuple[str, ...]
    design: tuple[str, ...]
    implementation: tuple[str, ...]
    tests: tuple[str, ...]
    test_files: tuple[str, ...]
    status: str


class RequirementsError(ValueError):
    pass


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RequirementsError(f"{field} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise RequirementsError(f"{field} must be a non-empty list")
    result: list[str] = []
    for item in value:
        result.append(_string(item, field))
    return tuple(result)


def parse_requirement(data: dict[str, Any]) -> Requirement:
    unknown = set(data) - ALLOWED_FIELDS
    missing = set(REQUIRED_FIELDS) - set(data)
    if unknown:
        raise RequirementsError(f"unknown fields: {sorted(unknown)}")
    if missing:
        raise RequirementsError(f"missing fields: {sorted(missing)}")
    return Requirement(
        id=_string(data["id"], "id"),
        type=_string(data["type"], "type"),
        title=_string(data["title"], "title"),
        description=_string(data["description"], "description"),
        priority=_string(data["priority"], "priority"),
        approval=_string(data["approval"], "approval"),
        source=_string_list(data["source"], "source"),
        acceptance=_string_list(data["acceptance"], "acceptance"),
        design=_string_list(data["design"], "design"),
        implementation=_string_list(data["implementation"], "implementation"),
        tests=_string_list(data["tests"], "tests"),
        test_files=_string_list(data["test_files"], "test_files"),
        status=_string(data["status"], "status"),
    )


def _path_for_ref(ref: str) -> Path:
    return Path(ref.split("#", 1)[0])


def _check_existing_paths(
    root: Path,
    refs: tuple[str, ...],
    label: str,
    errors: list[str],
    must_exist: bool,
) -> None:
    for ref in refs:
        path = _path_for_ref(ref)
        if not str(path).startswith(DESIGN_PREFIXES) and label == "design":
            prefixes = ", ".join(DESIGN_PREFIXES)
            errors.append(f"{label} reference must be under one of {prefixes}: {ref}")
        if must_exist and not (root / path).exists():
            errors.append(f"{label} path does not exist: {ref}")


def _check_prefix(
    refs: tuple[str, ...],
    allowed_prefixes: tuple[str, ...],
    label: str,
    errors: list[str],
) -> None:
    for ref in refs:
        path = str(_path_for_ref(ref))
        if not path.startswith(allowed_prefixes):
            errors.append(f"{label} reference has unsupported prefix: {ref}")


def validate_requirement(requirement: Requirement, root: Path) -> list[str]:
    errors: list[str] = []
    if not ID_PATTERN.fullmatch(requirement.id):
        errors.append(f"invalid requirement id: {requirement.id}")
    expected_prefix = TYPE_PREFIXES.get(requirement.type)
    if expected_prefix is None:
        errors.append(f"{requirement.id}: invalid type: {requirement.type}")
    elif not requirement.id.startswith(f"{expected_prefix}-"):
        errors.append(f"{requirement.id}: id does not match type {requirement.type}")
    if requirement.priority not in PRIORITIES:
        errors.append(f"{requirement.id}: invalid priority: {requirement.priority}")
    if requirement.approval not in APPROVALS:
        errors.append(f"{requirement.id}: invalid approval: {requirement.approval}")
    if requirement.status not in STATUSES:
        errors.append(f"{requirement.id}: invalid status: {requirement.status}")
    if not requirement.source:
        errors.append(f"{requirement.id}: source is empty")
    if not requirement.acceptance:
        errors.append(f"{requirement.id}: acceptance criteria are empty")
    if not requirement.design:
        errors.append(f"{requirement.id}: design references are empty")
    if not requirement.implementation:
        errors.append(f"{requirement.id}: implementation references are empty")
    if not requirement.tests:
        errors.append(f"{requirement.id}: test references are empty")
    if not requirement.test_files:
        errors.append(f"{requirement.id}: test file references are empty")
    seen_tests: set[str] = set()
    for test_id in requirement.tests:
        if not TEST_PATTERN.fullmatch(test_id):
            errors.append(f"{requirement.id}: invalid test id: {test_id}")
        if not test_id.startswith(f"TEST-{requirement.id}-"):
            errors.append(f"{requirement.id}: test id does not belong to requirement: {test_id}")
        if test_id in seen_tests:
            errors.append(f"{requirement.id}: duplicate test id: {test_id}")
        seen_tests.add(test_id)
    _check_prefix(requirement.design, DESIGN_PREFIXES, "design", errors)
    _check_prefix(requirement.implementation, IMPLEMENTATION_PREFIXES, "implementation", errors)
    _check_prefix(requirement.test_files, TEST_FILE_PREFIXES, "test file", errors)
    _check_existing_paths(root, requirement.design, "design", errors, must_exist=True)
    terminal = requirement.status in {"implemented", "verified"}
    _check_existing_paths(
        root,
        requirement.implementation,
        "implementation",
        errors,
        must_exist=terminal,
    )
    _check_existing_paths(
        root,
        requirement.test_files,
        "test file",
        errors,
        must_exist=terminal,
    )
    return errors


def load_document(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise RequirementsError(f"{path}: top-level YAML must be a mapping")
    return cast(dict[str, Any], data)


def parse_document(document: dict[str, Any], root: Path) -> tuple[list[Requirement], list[str]]:
    errors: list[str] = []
    meta = document.get("meta")
    if not isinstance(meta, dict):
        errors.append("meta must be a mapping")
    else:
        if meta.get("version") != 1:
            errors.append("meta.version must be 1")
    raw_requirements = document.get("requirements")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        errors.append("requirements must be a non-empty list")
        return [], errors
    requirements: list[Requirement] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_requirements):
        if not isinstance(raw, dict):
            errors.append(f"requirements[{index}] must be a mapping")
            continue
        try:
            requirement = parse_requirement(cast(dict[str, Any], raw))
        except RequirementsError as error:
            errors.append(f"requirements[{index}]: {error}")
            continue
        if requirement.id in seen_ids:
            errors.append(f"duplicate requirement id: {requirement.id}")
        seen_ids.add(requirement.id)
        errors.extend(validate_requirement(requirement, root))
        requirements.append(requirement)
    return requirements, errors


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _render_list(values: tuple[str, ...]) -> str:
    return "<br>".join(f"`{_escape(value)}`" for value in values)


def _render_requirement(requirement: Requirement) -> str:
    acceptance = "\n".join(f"- {item}" for item in requirement.acceptance)
    source = ", ".join(f"`{item}`" for item in requirement.source)
    design = ", ".join(f"`{item}`" for item in requirement.design)
    return (
        f"### {requirement.id} — {requirement.title}\n\n"
        f"**Приоритет:** {requirement.priority}\n\n"
        f"**Согласование:** {requirement.approval}\n\n"
        f"**Статус:** {requirement.status}\n\n"
        f"{requirement.description}\n\n"
        f"**Источники:** {source}\n\n"
        f"**Проектирование:** {design}\n\n"
        f"**Критерии приёмки:**\n\n{acceptance}\n"
    )


def render_requirements(requirements: list[Requirement], requirement_type: str) -> str:
    title = (
        "Функциональные требования"
        if requirement_type == "functional"
        else ("Нефункциональные требования")
    )
    selected = [item for item in requirements if item.type == requirement_type]
    chunks = [
        "<!-- AUTOGENERATED: edit docs/requirements/requirements.yaml and run "
        "`make requirements`. -->\n",
        f"# {title}\n\n",
        "Источник истины: `docs/requirements/requirements.yaml`. "
        "Документ генерируется, вручную не редактируется.\n\n",
        f"Всего требований: {len(selected)}.\n",
    ]
    for priority in ("must", "should", "could"):
        group = [item for item in selected if item.priority == priority]
        if not group:
            continue
        chunks.append(f"\n## {priority}\n\n")
        for requirement in group:
            chunks.append(_render_requirement(requirement))
            chunks.append("\n")
    return "".join(chunks).rstrip() + "\n"


def render_matrix(requirements: list[Requirement]) -> str:
    lines = [
        "<!-- AUTOGENERATED: edit docs/requirements/requirements.yaml and run "
        "`make requirements`. -->\n",
        "# Матрица трассируемости требований\n\n",
        "Источник истины: `docs/requirements/requirements.yaml`.\n\n",
        "| ID | Тип | Требование | Приоритет | Согласование | Источник | "
        "Проектирование | Реализация | Проверка | Статус |\n",
        "|---|---|---|---|---|---|---|---|---|---|\n",
    ]
    for requirement in requirements:
        lines.append(
            f"| {requirement.id} | {requirement.type} | {_escape(requirement.title)} | "
            f"{requirement.priority} | {requirement.approval} | "
            f"{_render_list(requirement.source)} | {_render_list(requirement.design)} | "
            f"{_render_list(requirement.implementation)} | "
            f"{_render_list(requirement.tests)}<br>{_render_list(requirement.test_files)} | "
            f"{requirement.status} |\n"
        )
    return "".join(lines).rstrip() + "\n"


def generated_documents(requirements: list[Requirement]) -> dict[Path, str]:
    return {
        FUNCTIONAL_PATH: render_requirements(requirements, "functional"),
        NONFUNCTIONAL_PATH: render_requirements(requirements, "nonfunctional"),
        MATRIX_PATH: render_matrix(requirements),
    }


def write_generated(root: Path, requirements: list[Requirement]) -> None:
    for relative_path, content in generated_documents(requirements).items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def check_generated(root: Path, requirements: list[Requirement]) -> list[str]:
    errors: list[str] = []
    for relative_path, expected in generated_documents(requirements).items():
        path = root / relative_path
        if not path.exists():
            errors.append(f"generated document is missing: {relative_path}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(f"generated document is stale: {relative_path}")
    return errors


def run(root: Path, write: bool) -> list[str]:
    document = load_document(root / REQUIREMENTS_PATH)
    requirements, errors = parse_document(document, root)
    if errors:
        return errors
    if write:
        write_generated(root, requirements)
        return []
    return check_generated(root, requirements)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate requirements traceability")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.write and arguments.check:
        print("use either --write or --check", file=sys.stderr)
        return 2
    root = arguments.root.resolve()
    try:
        errors = run(root, write=arguments.write)
    except (RequirementsError, OSError, yaml.YAMLError) as error:
        print(f"requirements validation failed: {error}", file=sys.stderr)
        return 1
    if errors:
        for message in errors:
            print(f"requirements validation failed: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
