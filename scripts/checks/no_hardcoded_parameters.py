from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

CODE_SUFFIXES = frozenset({".py", ".bsl", ".os"})
DEFAULT_ROOTS = ("src", "rag-service/src")
EXCLUDED_DIRECTORIES = frozenset({".git", ".venv", "__pycache__", "node_modules", "tests"})
PARAMETER_NAMES = (
    r"timeout(?:_seconds)?|max_retries|top_k|chunk_size(?:_chars)?|"
    r"chunk_overlap(?:_chars)?|batch_size|max_depth|max_requests(?:_per_task)?|"
    r"max_tokens|max_output_tokens|temperature(?:_structured|_text)?|limit|ttl|"
    r"port|workers|graceful_shutdown(?:_seconds)?|embedding(?:_batch_size|_dimension)?|"
    r"index_sync_interval(?:_minutes)?|search_min_score|token_refresh_skew(?:_seconds)?|"
    r"request_timeout(?:_seconds)?|connect_timeout(?:_seconds)?|read_timeout(?:_seconds)?|"
    r"retry_backoff(?:_seconds)?|retry_status_codes?|interval(?:_seconds)?|"
    r"lock_timeout(?:_seconds)?|stale_task(?:_seconds)?|page_size|"
    r"response_time(?:_seconds)?|refresh(?:_seconds)?|priority|cost|score|threshold"
)
PYTHON_PARAMETER = re.compile(
    rf"\b(?:{PARAMETER_NAMES})\s*(?:=|:)\s*-?\d",
    re.IGNORECASE,
)
PYTHON_SLEEP = re.compile(r"\bsleep\(\s*\d")
PYTHON_RANGE = re.compile(r"\brange\(\s*\d")
BSL_PARAMETER = re.compile(
    r"\b(?:Таймаут|МаксимумПопыток|МаксимальнаяГлубина|МаксимумЗапросов|"
    r"КоличествоЗапросов|РазмерПакета|Температура|ВерхняяГраница|Порт|"
    r"КоличествоВоркеров|РазмерСтраницы|Интервал|Приоритет)\b"
    r"\s*=\s*-?\d",
    re.IGNORECASE,
)


def iter_code_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file():
            if path.suffix in CODE_SUFFIXES:
                yield path
            continue
        if not path.is_dir():
            continue
        for candidate in sorted(path.rglob("*")):
            if not candidate.is_file():
                continue
            if candidate.suffix not in CODE_SUFFIXES:
                continue
            if any(part in EXCLUDED_DIRECTORIES for part in candidate.parts):
                continue
            yield candidate


def scan_file(path: Path) -> list[str]:
    violations: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        patterns = (
            (BSL_PARAMETER,)
            if path.suffix in {".bsl", ".os"}
            else (
                PYTHON_PARAMETER,
                PYTHON_SLEEP,
                PYTHON_RANGE,
            )
        )
        for pattern in patterns:
            if pattern.search(line):
                message = f"{path}:{line_number}: hardcoded numeric parameter: {line.strip()}"
                violations.append(message)
    return violations


def scan_paths(paths: Iterable[Path]) -> list[str]:
    violations: list[str] = []
    for path in iter_code_files(paths):
        violations.extend(scan_file(path))
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject hardcoded numeric parameters in code")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("paths", nargs="*", type=Path)
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    paths = arguments.paths or [root / item for item in DEFAULT_ROOTS]
    try:
        violations = scan_paths(paths)
    except OSError as error:
        print(f"numeric parameter check failed: {error}", file=sys.stderr)
        return 1
    if violations:
        for violation in violations:
            print(f"numeric parameter check failed: {violation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
