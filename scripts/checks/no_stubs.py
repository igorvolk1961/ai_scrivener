from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

CODE_SUFFIXES = frozenset({".py", ".bsl", ".os"})
DEFAULT_ROOTS = ("src", "rag-service/src", "scripts")
EXCLUDED_DIRECTORIES = frozenset({".git", ".venv", "__pycache__", "node_modules", "tests"})
FORBIDDEN_PATTERN = re.compile(
    r"\b(?:TODO|FIXME|XXX|HACK)\b|NotImplemented(?:Error)?\b|заглушк\w*|\bstub\b",
    re.IGNORECASE,
)


def _is_checker(path: Path) -> bool:
    return path.name == "no_stubs.py" and path.parent.name == "checks"


def iter_code_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file():
            if path.suffix in CODE_SUFFIXES and not _is_checker(path):
                yield path
            continue
        if not path.is_dir():
            continue
        for candidate in sorted(path.rglob("*")):
            if not candidate.is_file():
                continue
            if candidate.suffix not in CODE_SUFFIXES:
                continue
            if _is_checker(candidate):
                continue
            if any(part in EXCLUDED_DIRECTORIES for part in candidate.parts):
                continue
            yield candidate


def scan_file(path: Path) -> list[str]:
    violations: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = FORBIDDEN_PATTERN.search(line)
        if match:
            violations.append(f"{path}:{line_number}: forbidden marker: {match.group(0)}")
    return violations


def scan_paths(paths: Iterable[Path]) -> list[str]:
    violations: list[str] = []
    for path in iter_code_files(paths):
        violations.extend(scan_file(path))
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject unapproved stubs and TODO markers")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("paths", nargs="*", type=Path)
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    paths = arguments.paths or [root / item for item in DEFAULT_ROOTS]
    try:
        violations = scan_paths(paths)
    except OSError as error:
        print(f"stub check failed: {error}", file=sys.stderr)
        return 1
    if violations:
        for violation in violations:
            print(f"stub check failed: {violation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
