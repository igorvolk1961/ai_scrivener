from __future__ import annotations

from pathlib import Path

from scripts.checks.no_stubs import scan_paths


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
