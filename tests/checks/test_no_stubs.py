from __future__ import annotations

from pathlib import Path

from scripts.checks.no_stubs import load_approved_todo_ids, scan_paths


def test_clean_source_has_no_violations(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text('def run() -> str:\n    return "ok"\n', encoding="utf-8")
    assert scan_paths([source]) == []


def test_todo_marker_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("# TODO: implement later\n", encoding="utf-8")
    violations = scan_paths([source])
    assert len(violations) == 1
    assert "forbidden marker" in violations[0]


def test_not_implemented_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("def run() -> None:\n    raise NotImplementedError\n", encoding="utf-8")
    violations = scan_paths([source])
    assert len(violations) == 1
    assert "NotImplementedError" in violations[0]


def test_bsl_stub_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "module.bsl"
    source.write_text("Процедура Тест()\n    // заглушка\nКонецПроцедуры\n", encoding="utf-8")
    violations = scan_paths([source])
    assert len(violations) == 1


def test_stub_without_todo_reference_is_rejected_even_with_approved_ids(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("# TODO: implement later\n", encoding="utf-8")
    violations = scan_paths([source], frozenset({"T-001"}))
    assert len(violations) == 1


def test_stub_with_unapproved_todo_reference_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("# TODO: implement later, see TODO.md#T-002\n", encoding="utf-8")
    violations = scan_paths([source], frozenset({"T-001"}))
    assert len(violations) == 1


def test_stub_with_approved_todo_reference_is_accepted(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("# TODO: implement later, see TODO.md#T-001\n", encoding="utf-8")
    violations = scan_paths([source], frozenset({"T-001"}))
    assert violations == []


def test_load_approved_todo_ids_reads_headings(tmp_path: Path) -> None:
    todo_file = tmp_path / "TODO.md"
    todo_file.write_text(
        "# TODO\n\n## Активные\n\n### T-001 — пример\n\nТекст.\n\n### T-002 — другой пример\n",
        encoding="utf-8",
    )
    assert load_approved_todo_ids(todo_file) == frozenset({"T-001", "T-002"})


def test_load_approved_todo_ids_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_approved_todo_ids(tmp_path / "TODO.md") == frozenset()
