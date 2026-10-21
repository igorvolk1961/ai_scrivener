from __future__ import annotations

from pathlib import Path

from scripts.checks.no_hardcoded_parameters import scan_paths


def test_parameter_loaded_from_config_is_allowed(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text(
        "timeout_seconds = settings.timeout_seconds\ntop_k = settings.top_k\n",
        encoding="utf-8",
    )
    assert scan_paths([source]) == []


def test_numeric_timeout_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("timeout_seconds = 30\n", encoding="utf-8")
    assert len(scan_paths([source])) == 1


def test_numeric_port_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("port = 8080\n", encoding="utf-8")
    assert len(scan_paths([source])) == 1


def test_numeric_sleep_and_range_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("sleep(5)\nfor item in range(10):\n    print(item)\n", encoding="utf-8")
    assert len(scan_paths([source])) == 2


def test_bsl_numeric_parameter_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "module.bsl"
    source.write_text("Таймаут = 30;\n", encoding="utf-8")
    assert len(scan_paths([source])) == 1
